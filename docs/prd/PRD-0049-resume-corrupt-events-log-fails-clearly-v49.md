# PRD-0049 — Resume: Corrupt `events.jsonl` Must Fail Clearly v49（恢复：events.jsonl 损坏必须明确失败 v49）

## Vision

SDK 支持 resume，会读取 `sessions/<session_id>/events.jsonl` 来重建上下文。为了避免“静默丢事件/错乱继续/写坏更多数据”，当发现 `events.jsonl` **存在坏行/截断/无法解码** 时必须：

- **立刻失败**（不允许自动容错继续、不允许静默忽略）
- 报错必须“人话 + 可定位”：包含 `events.jsonl` 路径、`session_id`、行号（或原因）

## Decision (User Choice)

- 策略：**A — 直接失败并给出明确错误**。

## Non-Goals

- 不做自动修复/截断写回（避免修改用户本地数据）。
- 不扩大到 Gateway/MCP。
- 不触碰 PTY/ConPTY（另一个同学负责）。

## Requirements

### REQ-0049-001 — Corrupt events log raises a clear error

当读取 `events.jsonl` 发现坏行/解码失败时：

- 抛出明确异常（例如 `CorruptSessionLogError`）
- 异常信息必须包含：
  - `events.jsonl`（文件名或绝对路径）
  - `session_id=<...>`
  - `line=<N>`（若可定位到具体坏行；解码失败可标明原因）

### REQ-0049-002 — Resume E2E: corrupt tail line fails fast

新增真网络、no-injection E2E：

- Run1：创建 session（任意正常对话即可）
- 手动向 `events.jsonl` 追加一个坏 JSON 行（模拟截断）
- Run2：使用同一个 `resume` 继续，必须抛出 `CorruptSessionLogError`
- 断言异常信息满足 REQ-0049-001

### REQ-0049-003 — Suites + Evidence

- 更新 `e2e_tests/core_flows_sessions.py` 纳入 REQ-0049-002
- 按塔山 DoD 跑真网络 gate 并落证据到 plan 文档：
  - `python -m unittest -v e2e_tests.core_flows_sessions`
  - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_sessions --runs 3 --min-pass-rate 0.8 --rerun-failures 1`

## Acceptance (DoD)

必须全部满足：

- REQ-0049-001..003 全部达成
- 证据写入 `docs/plan/v49-resume-corrupt-events-log-fails-clearly.md`

