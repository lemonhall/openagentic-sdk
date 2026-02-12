# v25 Plan — Real-Network E2E (Core Non-Injection Negative Paths)（真实网络 E2E：核心非注入负路径）

## Goal

把核心负路径（工具输入错误 / acceptEdits 权限策略 / 路径越界安全边界）用 **非注入** 真实网络 E2E 固化成可回归证据。

## PRD Trace

- REQ-0025-001
- REQ-0025-002
- REQ-0025-003
- REQ-0025-004

## Scope

做：
- 新增 4 个 `e2e_tests/e2e_*_real_no_injection.py`
- 断言优先使用 `tool.result` 机读字段 + 磁盘落盘

不做：
- 不改 CLI PTY（另有人负责）
- 不加第三方依赖
- 不测 MCP/Gateway

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` exit code=0
2) 新增用例覆盖 REQ-0025-001..004

## Evidence（填写为可复现证据）

- Date: 2026-02-11
- `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` → OK（Ran 79 tests in ~759s；退出码 0）

## Steps（Strict）

1) Red：先写 E2E（断言口径先行）
2) Green：必要时仅做最小修复（只为稳定/一致性）
3) Verify：跑 DoD 并写回 Evidence
