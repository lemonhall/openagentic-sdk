# v11 Plan — Real-Network E2E (runtime_core Tool Loop Guards)（真实网络 E2E：runtime_core 工具环路护栏）

## Goal

新增 4 个真实网络 E2E，覆盖工具环路的拒绝/阻断/错误护栏语义，保证事件与错误类型稳定可回归。

## PRD Trace

- REQ-0011-001
- REQ-0011-002
- REQ-0011-003
- REQ-0011-004

## Scope

做：
- 新增 4 个 `e2e_tests/e2e_*.py`
- 全量跑 `e2e_tests` 作为证据

不做：
- 不引入第三方依赖
- 不做长流程高成本对话（以 event/tool.result 硬断言为主）

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` exit code=0
2) 新增用例覆盖 REQ-0011-001..004

## Evidence（填写为可复现证据）

- Date: 2026-02-11
- Command: `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v`
- Result (excerpt):
  - `Ran 28 tests in 162.264s`
  - `OK`

## Steps（Strict）

1) Red：先写 E2E（硬断言：`tool.result` / `user.question` / `tool.use`）
2) Green：必要时通过 hooks 注入降低 LLM 波动，但不改变被测语义（仍然真实网络 + runtime_core tool loop）
3) Verify：跑 DoD 命令并写回 Evidence
