from __future__ import annotations

import json
import re
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from ..events import AssistantDelta, Event, SessionCheckpoint, SessionRedo, SessionSetHead, SessionUndo
from ..serialization import event_to_dict, loads_event
from .paths import events_path, meta_path, session_dir, transcript_path
from .errors import CorruptSessionLogError


@dataclass(frozen=True, slots=True)
class FileSessionStore:
    root_dir: Path
    _seq: dict[str, int] = field(default_factory=dict, init=False, repr=False, compare=False)
    _locks: dict[str, threading.Lock] = field(default_factory=dict, init=False, repr=False, compare=False)
    _locks_guard: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False, compare=False)

    def _session_lock(self, session_id: str) -> threading.Lock:
        with self._locks_guard:
            lock = self._locks.get(session_id)
            if lock is None:
                lock = threading.Lock()
                self._locks[session_id] = lock
            return lock

    def create_session(self, *, metadata: Optional[dict[str, Any]] = None) -> str:
        session_id = uuid.uuid4().hex
        directory = self.session_dir(session_id)
        directory.mkdir(parents=True, exist_ok=False)

        meta = {
            "session_id": session_id,
            "created_at": time.time(),
            "metadata": metadata or {},
        }
        meta_file = meta_path(self.root_dir, session_id)
        meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        return session_id

    def session_dir(self, session_id: str) -> Path:
        # Security: prevent path traversal (session_id becomes a path component).
        sid = str(session_id or "").strip()
        if not re.fullmatch(r"[0-9a-f]{32}", sid):
            raise ValueError("invalid session_id")
        return session_dir(self.root_dir, sid)

    def read_metadata(self, session_id: str) -> dict[str, Any]:
        try:
            d = self.session_dir(session_id)
        except ValueError:
            return {}
        p = d / "meta.json"
        if not p.exists():
            return {}
        try:
            obj = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except Exception:  # noqa: BLE001
            return {}
        if not isinstance(obj, dict):
            return {}
        md = obj.get("metadata")
        return dict(md) if isinstance(md, dict) else {}

    def read_meta_record(self, session_id: str) -> dict[str, Any]:
        """Read the raw meta.json record for server APIs.

        Back-compat: older records may omit fields.
        """

        try:
            d = self.session_dir(session_id)
        except ValueError:
            return {}
        p = d / "meta.json"
        if not p.exists():
            return {}
        try:
            obj = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except Exception:  # noqa: BLE001
            return {}
        return obj if isinstance(obj, dict) else {}

    def update_metadata(self, session_id: str, *, patch: dict[str, Any]) -> dict[str, Any]:
        """Merge `patch` into the stored metadata dict and persist."""

        if not isinstance(patch, dict):
            raise ValueError("patch must be a dict")
        rec = self.read_meta_record(session_id)
        if not rec:
            raise FileNotFoundError(session_id)
        md = rec.get("metadata")
        md2: dict[str, Any] = dict(md) if isinstance(md, dict) else {}
        md2.update(patch)
        rec["metadata"] = md2
        p = self.session_dir(session_id) / "meta.json"
        p.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return md2

    def delete_session(self, session_id: str) -> None:
        d = self.session_dir(session_id)
        if not d.exists():
            raise FileNotFoundError(session_id)
        shutil.rmtree(d)

    def fork_session(self, parent_session_id: str, *, head_seq: int | None = None, metadata: dict[str, Any] | None = None) -> str:
        """Fork a session by copying events up to `head_seq`.

        The new session is append-only and gets its own `system.init` event.
        """

        parent_events = self.read_events(parent_session_id)
        if head_seq is None:
            # Default to the last applied seq in the parent log.
            head_seq = self._infer_next_seq(parent_session_id)
        if not isinstance(head_seq, int) or head_seq <= 0:
            raise ValueError("head_seq must be a positive int")

        md = {"parent_session_id": parent_session_id, "parent_head_seq": head_seq}
        if metadata:
            md.update(dict(metadata))
        new_id = self.create_session(metadata=md)

        for e in parent_events:
            # Skip initialization/result events; the new session will create its own.
            if getattr(e, "type", "") in ("system.init", "result"):
                continue
            # Skip session control events; the fork materializes at a specific head.
            if getattr(e, "type", "").startswith("session."):
                continue
            seq = getattr(e, "seq", None)
            if isinstance(seq, int) and seq > head_seq:
                continue
            self.append_event(new_id, e)

        return new_id

    def append_event(self, session_id: str, event: Event) -> None:
        # Never persist streaming deltas; they can balloon session files to GBs.
        if isinstance(event, AssistantDelta):
            return
        # Validate session id before path usage.
        _ = self.session_dir(session_id)
        with self._session_lock(session_id):
            path = events_path(self.root_dir, session_id)
            path.parent.mkdir(parents=True, exist_ok=True)

            seq = self._seq.get(session_id)
            if seq is None:
                seq = self._infer_next_seq(session_id)
            seq += 1
            self._seq[session_id] = seq

            obj = event_to_dict(event)
            obj["seq"] = seq
            obj["ts"] = time.time()

            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
                f.write("\n")

            # Best-effort transcript for UI and diffing. This intentionally excludes
            # tool inputs/outputs to reduce accidental leakage.
            et = obj.get("type")
            if et in ("user.message", "assistant.message"):
                role = "user" if et == "user.message" else "assistant"
                entry = {
                    "seq": seq,
                    "ts": obj.get("ts"),
                    "role": role,
                    "text": obj.get("text") if isinstance(obj.get("text"), str) else "",
                }
                tp = transcript_path(self.root_dir, session_id)
                with tp.open("a", encoding="utf-8") as tf:
                    tf.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")))
                    tf.write("\n")

    def read_events(self, session_id: str) -> list[Event]:
        try:
            _ = self.session_dir(session_id)
        except ValueError:
            return []
        path = events_path(self.root_dir, session_id)
        if not path.exists():
            return []
        out: list[Event] = []
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            raise CorruptSessionLogError(session_id=session_id, path=path, reason=str(e)) from e
        for i, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                out.append(loads_event(line))
            except Exception as e:  # noqa: BLE001
                raise CorruptSessionLogError(session_id=session_id, path=path, line=i, reason=str(e)) from e
        return out

    def append_events(self, session_id: str, events: Iterable[Event]) -> None:
        for e in events:
            self.append_event(session_id, e)

    # Session timeline helpers (append-only).

    def checkpoint(self, session_id: str, *, label: str) -> None:
        # Capture the current last seq as the checkpoint head.
        head = self._infer_next_seq(session_id)
        self.append_event(session_id, SessionCheckpoint(label=label, head_seq=head))

    def set_head(self, session_id: str, *, head_seq: int, reason: str | None = None) -> None:
        if not isinstance(head_seq, int) or head_seq <= 0:
            raise ValueError("head_seq must be a positive int")
        self.append_event(session_id, SessionSetHead(head_seq=head_seq, reason=reason))

    def undo(self, session_id: str) -> None:
        self.append_event(session_id, SessionUndo())

    def redo(self, session_id: str) -> None:
        self.append_event(session_id, SessionRedo())

    def _infer_next_seq(self, session_id: str) -> int:
        try:
            _ = self.session_dir(session_id)
        except ValueError:
            return 0
        path = events_path(self.root_dir, session_id)
        if not path.exists():
            return 0
        last_seq: int | None = None
        # Read from the end in a simple, safe way (small files expected for v0.1).
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            raise CorruptSessionLogError(session_id=session_id, path=path, reason=str(e)) from e
        lines = text.splitlines()
        for idx, line in enumerate(reversed(lines), start=1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                # If the last non-empty line is corrupt, fail fast instead of silently
                # falling back to a guessed sequence.
                bad_line_no = max(1, len(lines) - idx + 1)
                raise CorruptSessionLogError(session_id=session_id, path=path, line=bad_line_no, reason="invalid JSON") from None
            if not isinstance(obj, dict):
                bad_line_no = max(1, len(lines) - idx + 1)
                raise CorruptSessionLogError(session_id=session_id, path=path, line=bad_line_no, reason="event must be a JSON object")
            seq = obj.get("seq")
            if isinstance(seq, int):
                last_seq = seq
                break
        if last_seq is not None:
            return last_seq
        # Back-compat: older logs without seq fields.
        return len([ln for ln in lines if ln.strip()])
