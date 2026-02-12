# PRD-0026 — Real-Network E2E (Core Smoke Set v26)（真实网络 E2E：核心 Smoke 集 v26）

## Vision

为核心模块建立一组**可高频运行**的真实网络 Smoke 集：

- 运行耗时目标：**2–3 分钟**（约 10–12 条用例）
- 覆盖核心中的核心：`runtime_core/tools/skills/hooks/permissions/sessions`
- 断言口径以“磁盘落盘 / events.jsonl / tool.result”优先，避免纯 final text

## Non-Goals

- 不测试 MCP / Gateway。
- 不测试 CLI PTY / ConPTY（另有人负责）。
- 不替代 full 回归（`python -m unittest discover -s e2e_tests -p "e2e_*.py" -v`）。

## Requirements

### REQ-0026-001 — Provide a stable smoke entrypoint (real-network)

提供一个可复制的 smoke 入口命令，运行一组精选核心用例，且不会被 `e2e_tests` 的全量 discover 自动包含。

### REQ-0026-002 — Smoke covers core pillars

smoke 集至少覆盖：
- provider stream（deltas/done）
- sessions（resume + events.jsonl 不落 delta）
- permissions（default/prompt/acceptEdits）
- tool loop error recovery
- security boundary（越界绝对路径拒绝）

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest -v e2e_tests.smoke_core` exit code=0
2) smoke 用例数量在 10–12 区间（允许后续小幅调整）

