# PRD-0040 — Model-Driven E2E (Sessions + Hooks Expansion v40)（模型驱动 E2E：会话与 Hooks 扩容 v40）

## Vision

把随机层（no injection）真正做成“覆盖核心组合流程”的回归网，优先把两个薄弱点补厚：

- `core_flows_sessions`：resume × permissions(prompt/default) × compaction(prune) 的跨 turn 用户流程
- `core_flows_hil`：新增更多 hooks 相关的 no-injection 用户流程（特别是 `post_tool_use` 改写输出）

## Non-Goals

- 不扩大到 Gateway/MCP。
- 不触碰 PTY/ConPTY。
- 不把随机层改 injected（hard-invariants 继续由 `core_matrix_v37` 守门）。

## Requirements

### REQ-0040-001 — Sessions: resume + prompt permission allow flow

新增 no-injection 真网络 E2E：

- Run1（resume）：prompt permission 下 Write+Read 落盘成功
- Run2（resume）：再次 Read 并返回 token
- 断言 events.jsonl append-only（行数增长）+ 至少出现一次 `user.question`

### REQ-0040-002 — Sessions: resume + prompt permission deny then allow (two runs)

新增 no-injection 真网络 E2E：

- Run1（resume）：prompt permission 回答 `no`，Write 被拒绝且无文件副作用，流程能结束
- Run2（resume）：prompt permission 回答 `yes`，Write 成功且文件含 token

### REQ-0040-003 — Sessions: prune + resume still usable (user-flow)

新增 no-injection 真网络 E2E：

- Run1（resume）：Read big.txt（产生可 prune 的大 tool result）
- Run2/3（resume）：纯文本 turn（不使用工具）
- Run4（resume）：Read small.txt 并回传 token
- 断言 events.jsonl 包含 `tool.output_compacted`（prune 发生），且 Run4 仍可正常 Read

### REQ-0040-004 — Hooks: post_tool_use overrides Read output (user-flow)

新增 no-injection 真网络 E2E：

- 钩子 `post_tool_use` 将 Read 输出的 `content` 改写为固定字符串（例如 `REDACTED`）
- 模型在流程中 Read 文件并回传看到的内容
- 断言最终返回是 `REDACTED`（证明 hook 改写生效且对模型可见）

### REQ-0040-005 — Suites + evidence

- 更新 `e2e_tests/core_flows_sessions.py` 纳入新增 sessions 用例
- 更新 `e2e_tests/core_flows_hil.py` 纳入新增 hooks 用例
- 证据（DoD）：
  - `python -m unittest -v e2e_tests.core_flows_sessions`
  - `python -m unittest -v e2e_tests.core_flows_hil`
  - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_sessions --runs 3 --min-pass-rate 0.8 --rerun-failures 1`
  - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_hil --runs 3 --min-pass-rate 0.8 --rerun-failures 1`

## Acceptance (DoD)

必须全部满足：

- REQ-0040-001..005 全部落地
- 证据写入 `docs/plan/v40-model-driven-e2e-sessions-hooks-expansion.md`

