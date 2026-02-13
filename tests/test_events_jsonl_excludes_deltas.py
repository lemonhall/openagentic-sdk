import asyncio
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import openagentic_sdk
from openagentic_sdk.options import OpenAgenticOptions
from openagentic_sdk.permissions.gate import PermissionGate
from openagentic_sdk.sessions.store import FileSessionStore


class _StreamingProvider:
    name = "streaming-fixture"

    async def stream(self, *, model, messages, tools=(), api_key=None):  # noqa: ANN001
        _ = (model, messages, tools, api_key)
        for _i in range(50):
            yield {"type": "text_delta", "delta": "x"}
            await asyncio.sleep(0)
        yield {"type": "done"}


class TestEventsJsonlExcludesDeltas(unittest.IsolatedAsyncioTestCase):
    async def test_assistant_deltas_are_not_persisted(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            store = FileSessionStore(root_dir=root)
            options = OpenAgenticOptions(
                provider=_StreamingProvider(),
                model="m",
                api_key="x",
                cwd=str(root),
                project_dir=str(root),
                session_store=store,
                permission_gate=PermissionGate(permission_mode="bypass"),
                include_partial_messages=True,
                max_steps=5,
            )

            r = await openagentic_sdk.run(prompt="hi", options=options)
            self.assertTrue(r.session_id)

            events_path = root / "sessions" / r.session_id / "events.jsonl"
            text = events_path.read_text(encoding="utf-8", errors="replace")
            self.assertNotIn('"type":"assistant.delta"', text)


if __name__ == "__main__":
    unittest.main()

