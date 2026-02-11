# v13 Plan — Real-Network E2E (Sessions Transcript Redaction)（真实网络 E2E：会话转录脱敏）

## Goal

新增 1 个真实网络 E2E，验证 `events.jsonl` 与 `transcript.jsonl` 的落盘语义：审计包含 tool 输出、转录不包含。

## PRD Trace

- REQ-0013-001

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
2) 新增用例覆盖 REQ-0013-001

## Evidence（填写为可复现证据）

- Date: 2026-02-11
- Command: `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v`
- Result (excerpt):
  - `Ran 32 tests in 190.765s`
  - `OK`

## Steps（Strict）

1) Red：写 E2E（硬断言：`events.jsonl` 含 token，`transcript.jsonl` 不含 token）
2) Green：必要时用 hooks 注入避免模型复述 token（仍然真实网络 + tool loop）
3) Verify：跑 DoD 命令并写回 Evidence
