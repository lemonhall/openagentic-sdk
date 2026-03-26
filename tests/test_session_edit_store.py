from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from openagentic_sdk.events import AssistantMessage, Result, ToolResult, ToolUse, UserMessage
from openagentic_sdk.sessions.store import FileSessionStore


class TestSessionEditStore(unittest.TestCase):
    def test_edit_message_text_updates_events_and_transcript_only_for_target_message(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            store = FileSessionStore(root_dir=root)
            sid = store.create_session(metadata={})

            store.append_event(sid, UserMessage(text="old user"))
            store.append_event(sid, AssistantMessage(text="old assistant"))
            store.append_event(sid, ToolUse(tool_use_id="tool_1", name="Read", input={"file_path": "a.txt"}))
            store.append_event(sid, ToolResult(tool_use_id="tool_1", output={"content": "hello"}))
            store.append_event(sid, Result(final_text="done", session_id=sid, response_id="resp_1"))

            events_before = store.read_events(sid)
            assistant_before = next(e for e in events_before if getattr(e, "type", "") == "assistant.message")
            tool_before = next(e for e in events_before if getattr(e, "type", "") == "tool.result")

            changed = store.edit_message_text(sid, seq=2, new_text="new assistant")

            self.assertTrue(changed)

            events_after = store.read_events(sid)
            assistant_after = next(e for e in events_after if getattr(e, "type", "") == "assistant.message")
            tool_after = next(e for e in events_after if getattr(e, "type", "") == "tool.result")
            result_after = next(e for e in events_after if getattr(e, "type", "") == "result")

            self.assertEqual(getattr(assistant_after, "text", None), "new assistant")
            self.assertEqual(getattr(assistant_after, "seq", None), getattr(assistant_before, "seq", None))
            self.assertEqual(getattr(assistant_after, "ts", None), getattr(assistant_before, "ts", None))

            self.assertEqual(getattr(tool_after, "output", None), getattr(tool_before, "output", None))
            self.assertEqual(getattr(result_after, "response_id", "sentinel"), None)

            tp = store.session_dir(sid) / "transcript.jsonl"
            entries = [json.loads(line) for line in tp.read_text(encoding="utf-8").splitlines() if line.strip()]
            texts = [entry.get("text") for entry in entries]
            self.assertEqual(texts, ["old user", "new assistant"])

        # Ensure no tmp files leaked after atomic rewrite.
            leaked = [p.name for p in store.session_dir(sid).iterdir() if p.name.endswith(".tmp")]
            self.assertEqual(leaked, [])

    def test_edit_message_text_rejects_non_message_events(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            store = FileSessionStore(root_dir=root)
            sid = store.create_session(metadata={})

            store.append_event(sid, UserMessage(text="one"))
            store.append_event(sid, ToolUse(tool_use_id="tool_1", name="Read", input={"file_path": "a.txt"}))

            with self.assertRaises(ValueError):
                store.edit_message_text(sid, seq=2, new_text="nope")

    def test_edit_message_text_noop_does_not_rewrite_file(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            store = FileSessionStore(root_dir=root)
            sid = store.create_session(metadata={})

            store.append_event(sid, UserMessage(text="same text"))
            fingerprint_before = store.session_fingerprint(sid)

            changed = store.edit_message_text(sid, seq=1, new_text="same text")

            self.assertFalse(changed)
            self.assertEqual(store.session_fingerprint(sid), fingerprint_before)

    def test_edit_message_text_detects_fingerprint_drift(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            store = FileSessionStore(root_dir=root)
            sid = store.create_session(metadata={})

            store.append_event(sid, UserMessage(text="one"))
            fingerprint_before = store.session_fingerprint(sid)
            store.append_event(sid, AssistantMessage(text="two"))

            with self.assertRaises(RuntimeError):
                store.edit_message_text(sid, seq=1, new_text="updated", expected_fingerprint=fingerprint_before)

            events_after = store.read_events(sid)
            texts = [getattr(e, "text", None) for e in events_after if getattr(e, "type", "") in ("user.message", "assistant.message")]
            self.assertEqual(texts, ["one", "two"])


if __name__ == "__main__":
    unittest.main()
