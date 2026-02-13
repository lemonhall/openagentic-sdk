# v15 Plan — Real-Network E2E (Responses tool output link fallback)（真实网络 E2E：Responses 工具输出关联回退）

## Goal

新增 1 个真实网络 E2E，覆盖 Responses 协议下“outputs-only 被拒绝时”的回退重试路径。

## PRD Trace

- REQ-0015-001

## Scope

做：
- 新增 1 个 `e2e_tests/e2e_*.py`
- 全量跑 `e2e_tests` 作为证据

不做：
- 不引入第三方依赖
- 不做长流程高成本对话

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` exit code=0
2) 新增用例覆盖 REQ-0015-001

## Evidence（填写为可复现证据）

- Date: 2026-02-11
- Command: `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v`
- Result (excerpt):
  - `Ran 34 tests in 226.954s`
  - `OK`

## Steps（Strict）

1) Red：写 E2E（硬断言：provider 的两次输入形态 + Result provider_metadata）
2) Green：必要时用 hooks 注入降低 LLM 波动（仍然真实网络 + tool loop）
3) Verify：跑 DoD 命令并写回 Evidence
