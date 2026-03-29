from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from openagentic_sdk.events import AssistantMessage, UserMessage
from openagentic_sdk.sessions.paths import transcript_path
from openagentic_sdk.sessions.store import FileSessionStore


class TestSessionTranscriptView(unittest.TestCase):
    def test_build_session_transcript_returns_structured_messages(self) -> None:
        from openagentic_sdk.server.session_transcript_view import build_session_transcript

        with TemporaryDirectory() as td:
            store = FileSessionStore(root_dir=Path(td))
            sid = store.create_session(metadata={"agent_name": "writer"})
            store.append_event(sid, UserMessage(text="你好"))
            store.append_event(sid, AssistantMessage(text="世界"))

            payload = build_session_transcript(store=store, session_id=sid, source="worker")

        self.assertEqual(payload["session_id"], sid)
        self.assertEqual(payload["agent_name"], "writer")
        self.assertEqual(payload["source"], "worker")
        self.assertEqual([m["role"] for m in payload["messages"]], ["user", "assistant"])
        self.assertEqual([m["text"] for m in payload["messages"]], ["你好", "世界"])

    def test_build_session_transcript_falls_back_to_events_when_transcript_file_is_missing(self) -> None:
        from openagentic_sdk.server.session_transcript_view import build_session_transcript

        with TemporaryDirectory() as td:
            root = Path(td)
            store = FileSessionStore(root_dir=root)
            sid = store.create_session(metadata={})
            store.append_event(sid, UserMessage(text="u"))
            store.append_event(sid, AssistantMessage(text="a"))
            transcript_path(root, sid).unlink()

            payload = build_session_transcript(store=store, session_id=sid, source="host", default_agent_name="host")

        self.assertEqual(payload["agent_name"], "host")
        self.assertEqual([m["text"] for m in payload["messages"]], ["u", "a"])


if __name__ == "__main__":
    unittest.main()
