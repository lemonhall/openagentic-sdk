from __future__ import annotations

import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping

import openagentic_sdk
from openagentic_sdk.hooks.engine import HookEngine
from openagentic_sdk.hooks.models import HookDecision, HookMatcher

from e2e_tests._harness import make_options


class TestE2EFlowHooksPreToolUseRewriteWritePathRealNoInjection(unittest.IsolatedAsyncioTestCase):
    async def test_pre_tool_use_rewrites_write_path(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            token = f"REWRITE_PATH_{uuid.uuid4().hex}"
            a = root / "a.txt"
            b = root / "b.txt"

            async def rewrite_write_input(payload: Mapping[str, Any]) -> HookDecision:
                if payload.get("tool_name") != "Write":
                    return HookDecision()
                inp = payload.get("tool_input")
                if not isinstance(inp, dict):
                    return HookDecision()
                fp_raw = inp.get("file_path") or inp.get("filePath")
                if fp_raw is None:
                    return HookDecision()
                fp_s = str(fp_raw).strip().strip('"').strip("'").replace("\\", "/")
                if not fp_s:
                    return HookDecision()

                # We want this flow to be robust against the model choosing absolute paths
                # or adding leading "./" or "/" by accident. Match by basename and then
                # rewrite to a sibling "b.txt" in the same directory.
                #
                # Also avoid rewriting suspicious traversal inputs.
                parts = [p for p in fp_s.split("/") if p]
                if any(p == ".." for p in parts):
                    return HookDecision()
                if parts and parts[-1].lower() != "a.txt":
                    return HookDecision()

                if fp_s.startswith("/") and ":" not in fp_s:
                    out_fp = "./b.txt"
                else:
                    # Replace only the final component.
                    if parts:
                        parts[-1] = "b.txt"
                        out_fp = "/".join(parts)
                        if fp_s.startswith("./") and not out_fp.startswith("./"):
                            out_fp = f"./{out_fp}"
                    else:
                        out_fp = "./b.txt"

                inp2 = dict(inp)
                inp2["file_path"] = out_fp
                inp2["filePath"] = out_fp
                return HookDecision(action="rewrite_write_path", override_tool_input=inp2)

            hooks = HookEngine(pre_tool_use=[HookMatcher(name="rewrite-write-path", tool_name_pattern="Write", hook=rewrite_write_input)])
            opts0 = make_options(root, allowed_tools=["Write", "Read"], hooks=hooks)
            opts = replace(opts0, max_steps=18)

            for attempt in range(6):
                if a.exists():
                    a.unlink()
                if b.exists():
                    b.unlink()
                prompt = (
                    "You MUST use tools.\n"
                    "Do not reply with any text until after Step 2 succeeds.\n"
                    "Step 1: Call Write to write EXACTLY ./a.txt (do not use absolute paths) with this token (overwrite=true):\n"
                    f"{token}\n"
                    "Step 2: Call Read on ./b.txt.\n"
                    "After tools succeed, reply with exactly: REWRITE_OK\n"
                    f"(attempt={attempt + 1})\n"
                )
                r = await openagentic_sdk.run(prompt=prompt, options=opts)

                # Hard evidence only: don't trust the model's final text alone.
                saw_hook = any(
                    getattr(e, "type", None) == "hook.event" and getattr(e, "hook_point", "") == "PreToolUse" for e in r.events
                )
                write_results = [
                    e
                    for e in r.events
                    if getattr(e, "type", None) == "tool.result"
                    and getattr(e, "is_error", True) is False
                    and isinstance(getattr(e, "output", None), dict)
                    and "bytes_written" in getattr(e, "output", {})
                ]
                wrote_b = False
                if write_results:
                    out = write_results[-1].output  # type: ignore[attr-defined]
                    wrote_b = "b.txt" in str(out.get("file_path") or out.get("filePath") or "").replace("\\", "/").lower()

                disk_ok = b.exists() and token in b.read_text(encoding="utf-8", errors="replace")
                if saw_hook and wrote_b and disk_ok and (r.final_text or "").strip() == "REWRITE_OK":
                    return

            self.fail("pre_tool_use rewrite Write path flow did not complete after 6 attempts")


if __name__ == "__main__":
    unittest.main()
