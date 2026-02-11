# v16 Plan — Real-Network E2E (Core Hardening)（真实网络 E2E：核心加固）

## Goal

一次性推进 v16 核心加固：stream+tool loop、prune、resume、一致性、permission allow、hook lifecycle、非注入 Edit happy-path。

## PRD Trace

- REQ-0016-001
- REQ-0016-002
- REQ-0016-003
- REQ-0016-004
- REQ-0016-005
- REQ-0016-006

## Scope

做：
- 新增 6 个 `e2e_tests/e2e_*.py`
- 全量跑 `e2e_tests` 作为证据

不做：
- 不引入第三方依赖
- 不做 MCP / Gateway / 长流程高成本对话

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` exit code=0
2) 新增用例覆盖 REQ-0016-001..006

## Evidence（填写为可复现证据）

- Date: 2026-02-11
- `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` → OK（Ran 40 tests in ~302s）

## Steps（Strict）

1) Red：先写 E2E（硬断言：event/tool.result/落盘产物）
2) Green：必要时用 hooks/provider wrapper 降低波动（仍真实网络 + runtime_core tool loop）
3) Verify：跑 DoD 命令并写回 Evidence
