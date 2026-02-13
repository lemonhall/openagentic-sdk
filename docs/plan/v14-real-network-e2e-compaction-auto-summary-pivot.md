# v14 Plan — Real-Network E2E (Compaction Auto + Summary Pivot)（真实网络 E2E：自动压缩与摘要枢轴）

## Goal

新增 1 个真实网络 E2E，覆盖 compaction 自动触发与摘要枢轴事件语义。

## PRD Trace

- REQ-0014-001

## Scope

做：
- 新增 1 个 `e2e_tests/e2e_*.py`
- 全量跑 `e2e_tests` 作为证据

不做：
- 不引入第三方依赖
- 不做长流程高成本对话（只触发一次 compaction）

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` exit code=0
2) 新增用例覆盖 REQ-0014-001

## Evidence（填写为可复现证据）

- Date: 2026-02-11
- Command: `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v`
- Result (excerpt):
  - `Ran 33 tests in 212.465s`
  - `OK`

## Steps（Strict）

1) Red：写 E2E（硬断言：`user.compaction` / `assistant.message(is_summary=True)` / result provider_metadata）
2) Green：必要时用 hooks 注入降低 LLM 波动（仍然真实网络 + tool loop）
3) Verify：跑 DoD 命令并写回 Evidence
