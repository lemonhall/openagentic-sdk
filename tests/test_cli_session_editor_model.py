from __future__ import annotations

import unittest

from openagentic_cli.session_editor import SessionEditorItem, SessionEditorModel


class TestCliSessionEditorModel(unittest.TestCase):
    def test_open_fails_without_session(self) -> None:
        opened = SessionEditorModel.open(session_id=None, busy=False, items=[])
        self.assertFalse(opened.opened)
        self.assertEqual(opened.reason, "no_session")
        self.assertIsNone(opened.model)

    def test_open_fails_while_busy(self) -> None:
        opened = SessionEditorModel.open(
            session_id="abc",
            busy=True,
            items=[SessionEditorItem(seq=1, role="user", text="hello", editable=True)],
        )
        self.assertFalse(opened.opened)
        self.assertEqual(opened.reason, "busy")
        self.assertIsNone(opened.model)

    def test_dirty_state_requires_explicit_save_request(self) -> None:
        opened = SessionEditorModel.open(
            session_id="abc",
            busy=False,
            items=[SessionEditorItem(seq=1, role="user", text="hello", editable=True)],
        )
        self.assertTrue(opened.opened)
        model = opened.model
        assert model is not None

        self.assertIsNone(model.request_save())
        model.set_draft_text("edited")
        self.assertTrue(model.dirty)

        request = model.request_save()
        self.assertIsNotNone(request)
        assert request is not None
        self.assertEqual(request.seq, 1)
        self.assertEqual(request.new_text, "edited")

    def test_cancel_marks_model_cancelled_without_save_request(self) -> None:
        opened = SessionEditorModel.open(
            session_id="abc",
            busy=False,
            items=[SessionEditorItem(seq=1, role="assistant", text="reply", editable=True)],
        )
        model = opened.model
        assert model is not None

        model.set_draft_text("changed")
        model.cancel()

        self.assertTrue(model.cancelled)
        self.assertIsNone(model.request_save())

    def test_read_only_item_cannot_enter_dirty_edit_state(self) -> None:
        opened = SessionEditorModel.open(
            session_id="abc",
            busy=False,
            items=[SessionEditorItem(seq=1, role="tool", text="{}", editable=False)],
        )
        model = opened.model
        assert model is not None

        self.assertFalse(model.can_edit_current)
        model.set_draft_text("mutated")
        self.assertFalse(model.dirty)
        self.assertEqual(model.draft_text, "{}")


if __name__ == "__main__":
    unittest.main()
