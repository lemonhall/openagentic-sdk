# PRD-0042 — Model-Driven E2E (Resume × Hooks × Permissions v42)（模型驱动 E2E：恢复×Hooks×权限 v42）

## Vision

继续把随机层（no injection）做厚，优先补“组合流程”的真实回归证据：

- resume × `acceptEdits`（不应 prompt）× Edit/Read
- resume × hooks(post_tool_use override)（第二次 run 生效）
- hooks(pre_tool_use rewrite) 在 Write 路径重写上的用户流程证据
- `default` 权限下 safe tools（Read）不应 prompt 的 no-injection 证据

## Non-Goals

- 不扩大到 Gateway/MCP。
- 不触碰 PTY/ConPTY。
- 不把随机层改 injected（硬不变量由 `core_matrix_v37` 守门）。

## Requirements

### REQ-0042-001 — Sessions: resume + acceptEdits (no prompt)

新增 no-injection 真网络 E2E：

- Run1（resume）：`permission_mode="acceptEdits"` 下 Edit+Read 成功，且不产生 `user.question`
- Run2（resume）：Read 并回传 token（确认会话可继续）

### REQ-0042-002 — Sessions: resume + post_tool_use override

新增 no-injection 真网络 E2E：

- Run1（resume）：Write 文件写入 token
- Run2（resume）：开启 `post_tool_use` 覆盖 Read 输出 content=REDACTED；模型 Read 并回传 REDACTED

### REQ-0042-003 — Hooks: pre_tool_use rewrite Write file_path

新增 no-injection 真网络 E2E：

- hook 将 Write 的 file_path 从 `./a.txt` 改写为 `./b.txt`
- 模型流程仍按指令在 Step2 Read `./b.txt` 并回传 token
- 断言 `./a.txt` 不存在、`./b.txt` 含 token

### REQ-0042-004 — Permissions: default safe Read no prompt (no injection)

新增 no-injection 真网络 E2E：

- `permission_mode="default"` 下 Read 不应产生 `user.question`
- 用 user_answerer=raise 防止意外 prompt

### REQ-0042-005 — Suites + evidence

- 更新 `e2e_tests/core_flows_sessions.py` / `e2e_tests/core_flows_hil.py`
- 证据（DoD）：
  - `python -m unittest -v e2e_tests.core_flows_sessions`
  - `python -m unittest -v e2e_tests.core_flows_hil`
  - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_sessions --runs 3 --min-pass-rate 0.8 --rerun-failures 1`
  - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_hil --runs 3 --min-pass-rate 0.8 --rerun-failures 1`

## Acceptance (DoD)

必须全部满足：

- REQ-0042-001..005 全部达成
- 证据写入 `docs/plan/v42-model-driven-e2e-resume-hooks-permissions.md`

