# v10 Plan — Real-Network E2E (Core Hooks + Permissions)（真实网络 E2E：Hooks 与权限门）

## Goal

新增 2 个真实网络 E2E，用硬断言把 hook/permission 的关键语义做回归。

## PRD Trace

- REQ-0010-001
- REQ-0010-002

## Scope

做：
- 新增 2 个 `e2e_tests/e2e_*.py`
- 全量跑 `e2e_tests` 作为证据

不做：
- 不引入第三方依赖
- 不做长流程高成本对话

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` exit code=0
2) 新增用例覆盖 REQ-0010-001..002

## Evidence（填写为可复现证据）

- Date: 2026-02-11
- Command: `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v`
- Result (excerpt):
  - `Ran 24 tests in 156.163s`
  - `OK`

## Steps（Strict）

1) Red：先写 E2E（硬断言：tool.result / error_type）
2) Green：必要时通过 hooks 注入降低 LLM 波动，但不改变被测语义（仍然真实网络 + runtime_core tool loop）
3) Verify：跑 DoD 命令并写回 Evidence
