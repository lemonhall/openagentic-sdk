from __future__ import annotations

import asyncio
import contextlib
import io
import os
import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from openagentic_sdk.options import OpenAgenticOptions
from openagentic_sdk.permissions.gate import PermissionGate
from openagentic_sdk.providers.base import ModelOutput


class _FakeApp:
    def __init__(self) -> None:
        self.invalidate_calls = 0

    def invalidate(self) -> None:
        self.invalidate_calls += 1


class _FakeSession:
    def __init__(self) -> None:
        self.app = _FakeApp()


class _Provider:
    name = "openai-compatible"

    async def complete(self, *, model, messages, tools=(), api_key=None):  # noqa: ANN001
        _ = (model, messages, tools, api_key)
        return ModelOutput(assistant_text="ok", tool_calls=())


class _TtyStringIO(io.StringIO):
    def isatty(self) -> bool:  # pragma: no cover
        return True

    def fileno(self) -> int:  # pragma: no cover
        return 0


class _FakePromptToolkitController:
    def __init__(self) -> None:
        self.invalidate_event = asyncio.Event()
        self.invalidate_calls = 0
        self.prompt_messages: list[str] = []


def _build_fake_prompt_toolkit_modules(controller: _FakePromptToolkitController) -> dict[str, types.ModuleType]:
    prompt_toolkit = types.ModuleType("prompt_toolkit")
    prompt_toolkit_application = types.ModuleType("prompt_toolkit.application")
    prompt_toolkit_application_current = types.ModuleType("prompt_toolkit.application.current")
    prompt_toolkit_completion = types.ModuleType("prompt_toolkit.completion")
    prompt_toolkit_cursor_shapes = types.ModuleType("prompt_toolkit.cursor_shapes")
    prompt_toolkit_input = types.ModuleType("prompt_toolkit.input")
    prompt_toolkit_input_defaults = types.ModuleType("prompt_toolkit.input.defaults")
    prompt_toolkit_key_binding = types.ModuleType("prompt_toolkit.key_binding")
    prompt_toolkit_output = types.ModuleType("prompt_toolkit.output")
    prompt_toolkit_output_defaults = types.ModuleType("prompt_toolkit.output.defaults")
    prompt_toolkit_patch_stdout = types.ModuleType("prompt_toolkit.patch_stdout")

    class _PromptApp:
        def invalidate(self) -> None:
            controller.invalidate_calls += 1
            controller.invalidate_event.set()

    class PromptSession:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            _ = (args, kwargs)
            self.app = _PromptApp()

        async def prompt_async(self, **kwargs) -> str:  # noqa: ANN003
            controller.prompt_messages.append(str(kwargs.get("message") or ""))
            call_index = len(controller.prompt_messages)
            if call_index == 1:
                return "hello"
            if call_index == 2:
                await controller.invalidate_event.wait()
                return "/exit"
            raise EOFError

    class WordCompleter:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            _ = (args, kwargs)

    class KeyBindings:
        def add(self, *args, **kwargs):  # noqa: ANN002, ANN003
            _ = (args, kwargs)

            def _decorator(func):
                return func

            return _decorator

    def merge_completers(*args, **kwargs):  # noqa: ANN002, ANN003
        _ = (args, kwargs)
        return object()

    def create_app_session(*args, **kwargs):  # noqa: ANN002, ANN003
        _ = (args, kwargs)
        return contextlib.nullcontext()

    def create_input(*args, **kwargs):  # noqa: ANN002, ANN003
        _ = (args, kwargs)
        return object()

    def create_output(*args, **kwargs):  # noqa: ANN002, ANN003
        _ = (args, kwargs)
        return object()

    def patch_stdout(*args, **kwargs):  # noqa: ANN002, ANN003
        _ = (args, kwargs)
        return contextlib.nullcontext()

    prompt_toolkit.PromptSession = PromptSession
    prompt_toolkit_application_current.create_app_session = create_app_session
    prompt_toolkit_completion.WordCompleter = WordCompleter
    prompt_toolkit_completion.merge_completers = merge_completers
    prompt_toolkit_cursor_shapes.CursorShape = types.SimpleNamespace(BLINKING_BEAM="beam")
    prompt_toolkit_input_defaults.create_input = create_input
    prompt_toolkit_key_binding.KeyBindings = KeyBindings
    prompt_toolkit_output_defaults.create_output = create_output
    prompt_toolkit_patch_stdout.patch_stdout = patch_stdout

    return {
        "prompt_toolkit": prompt_toolkit,
        "prompt_toolkit.application": prompt_toolkit_application,
        "prompt_toolkit.application.current": prompt_toolkit_application_current,
        "prompt_toolkit.completion": prompt_toolkit_completion,
        "prompt_toolkit.cursor_shapes": prompt_toolkit_cursor_shapes,
        "prompt_toolkit.input": prompt_toolkit_input,
        "prompt_toolkit.input.defaults": prompt_toolkit_input_defaults,
        "prompt_toolkit.key_binding": prompt_toolkit_key_binding,
        "prompt_toolkit.output": prompt_toolkit_output,
        "prompt_toolkit.output.defaults": prompt_toolkit_output_defaults,
        "prompt_toolkit.patch_stdout": prompt_toolkit_patch_stdout,
    }


class TestCliReplPromptPrefetch(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        asyncio.get_running_loop().slow_callback_duration = 1.0

    async def test_invalidate_pending_prompt_prefetch_after_turn(self) -> None:
        import openagentic_cli.repl_chat as repl_chat

        session = _FakeSession()
        blocker = asyncio.Event()

        async def _pending_prompt() -> str:
            await blocker.wait()
            return "unused"

        prompt_task = asyncio.create_task(_pending_prompt())
        try:
            repl_chat._invalidate_pending_prompt_prefetch(session=session, prompt_task=prompt_task)
            self.assertEqual(session.app.invalidate_calls, 1)
        finally:
            prompt_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await prompt_task

    async def test_does_not_invalidate_completed_prompt_prefetch(self) -> None:
        import openagentic_cli.repl_chat as repl_chat

        session = _FakeSession()
        prompt_task = asyncio.create_task(asyncio.sleep(0, result="typed ahead"))
        await prompt_task

        repl_chat._invalidate_pending_prompt_prefetch(session=session, prompt_task=prompt_task)
        self.assertEqual(session.app.invalidate_calls, 0)

    async def test_run_chat_redraws_pending_prompt_toolkit_prefetch_after_turn(self) -> None:
        from openagentic_cli.repl import run_chat
        from openagentic_cli.style import StyleConfig

        controller = _FakePromptToolkitController()
        fake_modules = _build_fake_prompt_toolkit_modules(controller)

        with TemporaryDirectory() as td:
            opts = OpenAgenticOptions(
                provider=_Provider(),
                model="gpt-5.2",
                api_key=None,
                cwd="C:\\proj",
                project_dir="C:\\proj",
                permission_gate=PermissionGate(permission_mode="deny"),
                setting_sources=[],
                session_root=Path(td),
            )

            stdin = _TtyStringIO("")
            stdout = _TtyStringIO()

            with mock.patch.dict(sys.modules, fake_modules):
                with mock.patch.dict(
                    os.environ,
                    {
                        "OA_CLI_INPUT_BACKEND": "prompt_toolkit",
                        "OA_CLI_AUTOAPPROVE_PROMPT": "0",
                        "OA_CLI_BOTTOM_TOOLBAR": "0",
                    },
                    clear=False,
                ):
                    code = await asyncio.wait_for(
                        run_chat(
                            opts,
                            color_config=StyleConfig(color="never"),
                            debug=False,
                            stdin=stdin,
                            stdout=stdout,
                        ),
                        timeout=1.0,
                    )

        self.assertEqual(code, 0)
        self.assertEqual(controller.invalidate_calls, 1)
        self.assertEqual(controller.prompt_messages[:2], ["oa> ", "oa> "])
        self.assertIn("ok", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
