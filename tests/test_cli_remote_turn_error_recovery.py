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

from openagentic_cli.repl import run_chat
from openagentic_cli.style import StyleConfig
from openagentic_sdk.events import AssistantMessage, Result, SystemInit
from openagentic_sdk.options import OpenAgenticOptions
from openagentic_sdk.permissions.gate import PermissionGate


class _TtyStringIO(io.StringIO):
    def isatty(self) -> bool:  # pragma: no cover
        return True

    def fileno(self) -> int:  # pragma: no cover
        return 0


class _PromptToolkitController:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.prompt_messages: list[str] = []

    def next_response(self) -> str:
        if not self._responses:
            raise EOFError
        return self._responses.pop(0)


def _build_fake_prompt_toolkit_modules(controller: _PromptToolkitController) -> dict[str, types.ModuleType]:
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
            return

    class PromptSession:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            _ = (args, kwargs)
            self.app = _PromptApp()

        async def prompt_async(self, **kwargs) -> str:  # noqa: ANN003
            controller.prompt_messages.append(str(kwargs.get("message") or ""))
            return controller.next_response()

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


class _RecordingRemoteErrorRuntime:
    session_id = "a" * 32
    calls: list[tuple[str | None, str]] = []

    def __init__(self, options) -> None:  # noqa: ANN001
        self._options = options

    async def query(self, prompt: str):
        self.__class__.calls.append((self._options.resume, prompt))
        if prompt == "第一轮":
            yield SystemInit(
                session_id=self.session_id,
                cwd=self._options.cwd,
                sdk_version="test-sdk",
                enabled_tools=["Read"],
                enabled_providers=["rightcode"],
            )
            raise RuntimeError(
                'remote session sync failed (error): HTTP 503 from https://www.right.codes/codex/v1/responses '
                '(transient upstream error; try again): {"error":"代理请求繁忙，请稍后重试"}'
            )

        yield AssistantMessage(text="第二轮还活着")
        yield Result(final_text="第二轮还活着", session_id=self.session_id)


async def _no_remote_banner(_options) -> None:  # noqa: ANN001
    return None


class TestCliRemoteTurnErrorRecovery(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        _RecordingRemoteErrorRuntime.calls = []

    async def test_prompt_toolkit_remote_runtime_error_keeps_chat_alive_and_reuses_session(self) -> None:
        import openagentic_cli.repl_chat as repl_chat

        controller = _PromptToolkitController(["第一轮", "第二轮", "/exit"])
        fake_modules = _build_fake_prompt_toolkit_modules(controller)

        with TemporaryDirectory() as td:
            opts = OpenAgenticOptions(
                provider=None,
                model="bridge",
                cwd="C:\\proj",
                project_dir="C:\\proj",
                permission_gate=PermissionGate(permission_mode="deny"),
                setting_sources=[],
                session_root=Path(td),
                remote_chat_base_url="http://127.0.0.1:18776",
                remote_chat_timeout_s=1.0,
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
                    with mock.patch.object(repl_chat, "ClusterChatRuntime", _RecordingRemoteErrorRuntime):
                        with mock.patch.object(repl_chat, "_remote_host_banner", _no_remote_banner):
                            code = await run_chat(
                                opts,
                                color_config=StyleConfig(color="never"),
                                debug=False,
                                stdin=stdin,
                                stdout=stdout,
                            )

        rendered = stdout.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("remote session sync failed (error): HTTP 503", rendered)
        self.assertIn("第二轮还活着", rendered)
        self.assertEqual(
            _RecordingRemoteErrorRuntime.calls,
            [
                (None, "第一轮"),
                (_RecordingRemoteErrorRuntime.session_id, "第二轮"),
            ],
        )
        self.assertEqual(controller.prompt_messages[:3], ["oa> ", "oa> ", "oa> "])

    async def test_legacy_remote_runtime_error_keeps_chat_alive_and_reuses_session(self) -> None:
        import openagentic_cli.repl_chat as repl_chat

        with TemporaryDirectory() as td:
            opts = OpenAgenticOptions(
                provider=None,
                model="bridge",
                cwd="C:\\proj",
                project_dir="C:\\proj",
                permission_gate=PermissionGate(permission_mode="deny"),
                setting_sources=[],
                session_root=Path(td),
                remote_chat_base_url="http://127.0.0.1:18776",
                remote_chat_timeout_s=1.0,
            )
            stdin = io.StringIO("第一轮\n第二轮\n/exit\n")
            stdout = io.StringIO()
            with mock.patch.dict(
                os.environ,
                {
                    "OA_CLI_INPUT_BACKEND": "legacy",
                    "OA_CLI_AUTOAPPROVE_PROMPT": "0",
                    "OA_CLI_BOTTOM_TOOLBAR": "0",
                },
                clear=False,
            ):
                with mock.patch.object(repl_chat, "ClusterChatRuntime", _RecordingRemoteErrorRuntime):
                    with mock.patch.object(repl_chat, "_remote_host_banner", _no_remote_banner):
                        code = await run_chat(
                            opts,
                            color_config=StyleConfig(color="never"),
                            debug=False,
                            stdin=stdin,
                            stdout=stdout,
                        )

        rendered = stdout.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("remote session sync failed (error): HTTP 503", rendered)
        self.assertIn("第二轮还活着", rendered)
        self.assertEqual(
            _RecordingRemoteErrorRuntime.calls,
            [
                (None, "第一轮"),
                (_RecordingRemoteErrorRuntime.session_id, "第二轮"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
