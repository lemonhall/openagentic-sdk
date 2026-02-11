# v8 Plan — Real-Network E2E (Core Modules)（真实网络 E2E：核心模块夯实）

## Goal

在 `e2e_tests/` 新增 5 个真实网络 E2E，用“随机 token 只能通过 tool/hook 得到”的方式硬化断言，覆盖 hooks/skill/tools/runtime_core/人类交互关键链路。

## PRD Trace

- REQ-0008-001
- REQ-0008-002
- REQ-0008-003
- REQ-0008-004
- REQ-0008-005
- REQ-0008-006

## Scope

做：
- 新增 5 个 `e2e_tests/e2e_*.py`
- 更新 `e2e_tests/README.md`（.env + OPENAI_* 别名）

不做：
- 不引入 pytest 等新依赖
- 不扩展 Gateway/MCP 覆盖面

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` exit code=0
2) 新增用例覆盖 REQ-0008-001..005

## Evidence（填写为可复现证据）

- Date: 2026-02-11
- `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` → OK（18 tests）

## Steps（Strict）

1) Red：先写 5 个 E2E 文件（断言硬化：token 不出现在 prompt）
2) Green：必要时微调 prompt/allowed_tools/max_steps，降低波动
3) Verify：跑 DoD 命令并写回 Evidence
