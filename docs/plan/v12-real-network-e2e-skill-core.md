# v12 Plan — Real-Network E2E (Skill Core)（真实网络 E2E：Skill 核心语义）

## Goal

新增 3 个真实网络 E2E，覆盖 Skill 加载、优先级与错误语义。

## PRD Trace

- REQ-0012-001
- REQ-0012-002
- REQ-0012-003

## Scope

做：
- 新增 3 个 `e2e_tests/e2e_*.py`
- 调整 1 个已有 Skill E2E，避免依赖模型复述内容（以 `tool.result` 硬断言为准）
- 全量跑 `e2e_tests` 作为证据

不做：
- 不引入第三方依赖
- 不做长流程高成本对话

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` exit code=0
2) 新增用例覆盖 REQ-0012-001..003

## Evidence（填写为可复现证据）

- Date: 2026-02-11
- Command: `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v`
- Result (excerpt):
  - `Ran 31 tests in 176.394s`
  - `OK`

## Steps（Strict）

1) Red：写 E2E（硬断言：`tool.result` 输出/错误语义）
2) Green：必要时通过 hooks 注入降低 LLM 波动（仍然真实网络 + runtime_core tool loop）
3) Verify：跑 DoD 命令并写回 Evidence
