from __future__ import annotations

from dataclasses import dataclass

from openagentic_sdk.sessions.errors import SessionEditConflictError
from openagentic_sdk.sessions.store import FileSessionStore


@dataclass(frozen=True, slots=True)
class SessionEditorItem:
    seq: int
    role: str
    text: str
    editable: bool = True


@dataclass(frozen=True, slots=True)
class SessionEditorSaveRequest:
    seq: int
    new_text: str


@dataclass(frozen=True, slots=True)
class SessionEditorOpenResult:
    opened: bool
    reason: str | None = None
    model: SessionEditorModel | None = None


@dataclass(frozen=True, slots=True)
class SessionEditorOutcome:
    status: str
    changed: bool = False
    message: str | None = None


SESSION_EDITOR_OPEN_REQUEST = "__OA_SESSION_EDITOR_OPEN__"
SESSION_EDITOR_BUSY_REQUEST = "__OA_SESSION_EDITOR_BUSY__"


class SessionEditorModel:
    def __init__(self, *, session_id: str, items: list[SessionEditorItem]) -> None:
        if not session_id:
            raise ValueError("session_id is required")
        if not items:
            raise ValueError("items must not be empty")
        self.session_id = session_id
        self.items = list(items)
        self.selected_index = 0
        self.draft_text = self.items[0].text
        self.dirty = False
        self.cancelled = False

    @property
    def current_item(self) -> SessionEditorItem:
        return self.items[self.selected_index]

    @property
    def can_edit_current(self) -> bool:
        return bool(self.current_item.editable)

    @classmethod
    def open(
        cls,
        *,
        session_id: str | None,
        busy: bool,
        items: list[SessionEditorItem],
    ) -> SessionEditorOpenResult:
        if busy:
            return SessionEditorOpenResult(opened=False, reason="busy", model=None)
        if not session_id:
            return SessionEditorOpenResult(opened=False, reason="no_session", model=None)
        if not items:
            return SessionEditorOpenResult(opened=False, reason="empty", model=None)
        return SessionEditorOpenResult(opened=True, model=cls(session_id=session_id, items=items))

    def set_draft_text(self, text: str) -> None:
        if not self.can_edit_current or self.cancelled:
            return
        self.draft_text = text
        self.dirty = self.draft_text != self.current_item.text

    def select_relative(self, delta: int) -> bool:
        if self.cancelled or self.dirty or not self.items:
            return False
        self.selected_index = (self.selected_index + delta) % len(self.items)
        self.draft_text = self.current_item.text
        self.dirty = False
        return True

    def request_save(self) -> SessionEditorSaveRequest | None:
        if self.cancelled or not self.can_edit_current or not self.dirty:
            return None
        return SessionEditorSaveRequest(seq=self.current_item.seq, new_text=self.draft_text)

    def cancel(self) -> None:
        self.cancelled = True


def _render_message_list(model: SessionEditorModel) -> str:
    lines: list[str] = []
    for idx, item in enumerate(model.items):
        marker = ">" if idx == model.selected_index else " "
        preview = item.text.replace("\r", " ").replace("\n", " ")
        if len(preview) > 48:
            preview = preview[:45] + "..."
        lock = "" if item.editable else " [read-only]"
        lines.append(f"{marker} #{item.seq} {item.role}{lock}: {preview}")
    return "\n".join(lines)


def _status_text(model: SessionEditorModel, extra: str | None = None) -> str:
    status = extra or ""
    dirty = "dirty" if model.dirty else "clean"
    return f"Ctrl+S save | Esc cancel | Ctrl+P/N switch | {dirty}" + (f" | {status}" if status else "")


async def run_session_editor(*, store: FileSessionStore, session_id: str) -> SessionEditorOutcome:
    messages = store.list_editable_messages(session_id)
    items = [SessionEditorItem(seq=msg.seq, role=msg.role, text=msg.text, editable=True) for msg in messages]
    opened = SessionEditorModel.open(session_id=session_id, busy=False, items=items)
    if not opened.opened or opened.model is None:
        return SessionEditorOutcome(status=opened.reason or "error", changed=False)

    model = opened.model
    baseline_fingerprint = store.session_fingerprint(session_id)

    from prompt_toolkit.application import Application  # noqa: PLC0415
    from prompt_toolkit.key_binding import KeyBindings  # noqa: PLC0415
    from prompt_toolkit.layout import HSplit, Layout, VSplit  # noqa: PLC0415
    from prompt_toolkit.widgets import Frame, TextArea  # noqa: PLC0415

    list_area = TextArea(text=_render_message_list(model), read_only=True, focusable=False, scrollbar=True)
    editor = TextArea(text=model.draft_text, multiline=True, wrap_lines=True, scrollbar=True)
    footer = TextArea(text=_status_text(model), read_only=True, focusable=False, multiline=False, height=1)

    def _sync_model_from_editor() -> None:
        model.set_draft_text(editor.text)

    def _refresh(*, extra: str | None = None) -> None:
        list_area.text = _render_message_list(model)
        footer.text = _status_text(model, extra=extra)

    kb = KeyBindings()

    @kb.add("escape")  # type: ignore[misc]
    def _cancel(event) -> None:  # noqa: ANN001
        model.cancel()
        event.app.exit(result=SessionEditorOutcome(status="cancelled", changed=False))

    @kb.add("c-s")  # type: ignore[misc]
    def _save(event) -> None:  # noqa: ANN001
        _sync_model_from_editor()
        request = model.request_save()
        if request is None:
            _refresh(extra="no changes")
            return
        try:
            changed = store.edit_message_text(
                session_id,
                seq=request.seq,
                new_text=request.new_text,
                expected_fingerprint=baseline_fingerprint,
            )
        except SessionEditConflictError:
            event.app.exit(result=SessionEditorOutcome(status="conflict", changed=False, message="session changed"))
            return
        except Exception as exc:  # noqa: BLE001
            event.app.exit(result=SessionEditorOutcome(status="error", changed=False, message=str(exc)))
            return
        event.app.exit(result=SessionEditorOutcome(status="saved" if changed else "noop", changed=changed))

    @kb.add("c-p")  # type: ignore[misc]
    def _prev(event) -> None:  # noqa: ANN001
        _sync_model_from_editor()
        if not model.select_relative(-1):
            _refresh(extra="save or cancel current edit first")
            return
        editor.text = model.draft_text
        _refresh()

    @kb.add("c-n")  # type: ignore[misc]
    def _next(event) -> None:  # noqa: ANN001
        _sync_model_from_editor()
        if not model.select_relative(1):
            _refresh(extra="save or cancel current edit first")
            return
        editor.text = model.draft_text
        _refresh()

    body = HSplit(
        [
            TextArea(text="Session Editor", read_only=True, focusable=False, multiline=False, height=1),
            VSplit(
                [
                    Frame(list_area, title="Messages"),
                    Frame(editor, title=f"Edit #{model.current_item.seq}"),
                ]
            ),
            footer,
        ]
    )
    app = Application(layout=Layout(body, focused_element=editor), key_bindings=kb, full_screen=True)
    result = await app.run_async()
    return result if isinstance(result, SessionEditorOutcome) else SessionEditorOutcome(status="cancelled", changed=False)
