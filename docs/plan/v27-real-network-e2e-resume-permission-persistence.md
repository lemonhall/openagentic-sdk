# v27 Plan — Real-Network E2E (Resume + Permission Persistence)（真实网络 E2E：Resume + 权限持久化）

## Goal

补齐一个“真实用户路径”的真网络回归：permission prompt → Write 落盘 → resume → Read 回读。

## PRD Trace

- REQ-0027-001
- REQ-0027-002

## Scope

做：

- 新增 `e2e_tests/e2e_sessions_resume_permission_prompt_write_then_read_real_no_injection.py`
- 将该用例纳入 `e2e_tests/smoke_core.py`（高频 smoke）
- 新增 v27 PRD + Plan + Index 文档

不做：

- 不改 CLI PTY/ConPTY
- 不改 MCP/Gateway

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest -v e2e_tests.e2e_sessions_resume_permission_prompt_write_then_read_real_no_injection` exit code=0
2) `python -m unittest -v e2e_tests.smoke_core` exit code=0

## Evidence（填写为可复现证据）

- Date: 2026-02-12
- `python -m unittest -v e2e_tests.e2e_sessions_resume_permission_prompt_write_then_read_real_no_injection` → OK（1 test, 10.856s）
- `python -m unittest -v e2e_tests.smoke_core` → OK（11 tests, 88.933s）

## Steps（Strict）

1) Red：写 PRD/Plan，定义断言口径与 DoD
2) Green：落地 e2e 用例并接入 smoke
3) Verify：在 Windows/PowerShell 下实跑并写回 Evidence
