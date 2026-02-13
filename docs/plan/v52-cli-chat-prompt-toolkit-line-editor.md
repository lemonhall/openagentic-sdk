# v52 Plan — `oa chat` Prompt Toolkit Line Editor（默认行编辑器 + legacy 回退；ConPTY 在线 e2e 守门）

## PRD Trace

- REQ-0052-001
- REQ-0052-002
- REQ-0052-003
- REQ-0052-004
- REQ-0052-005
- REQ-0052-006
- REQ-0052-007

## Scope

做：

- `oa chat` 在 TTY 下默认使用 Prompt Toolkit 读取输入（方向键编辑、backspace 语义更稳定）
- 保留 legacy 输入后端（环境变量开关），并输出一次性废弃提示
- Windows ConPTY 在线 E2E：补一条“方向键编辑可用”的回归（以 `events.jsonl` 为证据）
- 文档：在 `AGENTS.md` 中简要说明输入后端与回退开关；保持套件隔离

不做：

- 不把 `e2e_cli_win_tests/` 合并进 `e2e_tests/`（仍 opt-in）
- 不做完整 TUI

## Implementation Notes（设计约束）

- 仅在 `stdin.isatty()` 与 `stdout.isatty()` 且 `stdin` 支持 `fileno()` 的情况下启用 Prompt Toolkit；否则保持当前 legacy 行读取路径，避免破坏现有单元测试（StringIO/fake tty）。
- Prompt Toolkit 模式下，优先保持外部可观察语义稳定：
  - prompt token 仍为 `oa> `
  - 使用 `show_frame=True` 显示输入框边框（依赖 `prompt_toolkit>=3.0.52`）
  - `/paste ... /end` 与 bracketed paste 继续按“多行 turn 不走命令解析”处理
  - 证据链以 `OPENAGENTIC_SDK_HOME/.../events.jsonl` 为准

## Steps（Strict）

1) Red：新增 Windows ConPTY E2E（方向键编辑）→ 预期在未接入 Prompt Toolkit 前失败
2) Green：接入 Prompt Toolkit 输入后端（默认启用），并提供 `OA_CLI_INPUT_BACKEND` 回退开关
3) Keep：legacy 后端保留、标记废弃并确保单测不破
4) Docs：更新 `AGENTS.md`（说明 v52 输入后端与开关）
5) Verify：跑 DoD 命令并记录 Evidence

## Acceptance (DoD)

必须全部满足：

1) 单元（快速）：
   - `python -m unittest -q tests.test_cli_repl_multiline_paste tests.test_cli_repl_thinking_hint tests.test_cli_prompt_styling tests.test_cli_repl_builtin_cwd`
2) Windows 11 ConPTY 在线 e2e（真网络；读取 `.env`）：
   - `python -m unittest discover -s e2e_cli_win_tests -p "e2e_*.py" -v` exit code=0

## Evidence（填写为可复现证据）

- Date: 2026-02-13
- Env: Windows 11 + PowerShell 7.x + ConPTY + real-network
- `python -m unittest -q tests.test_cli_repl_multiline_paste tests.test_cli_repl_thinking_hint tests.test_cli_prompt_styling tests.test_cli_repl_builtin_cwd` → OK（Ran 16 tests; skipped=2）
- `python -m unittest discover -s e2e_cli_win_tests -p "e2e_*.py" -v` → OK（Ran 15 tests）
