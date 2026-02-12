# PRD-0030 — Model-Driven E2E (Core Flows Suite v30)（模型驱动 E2E：核心用户流程套件 v30）

## Vision

在保持 `smoke_core` 作为 **hard-invariant 门禁（pass-rate=1.0）** 的前提下，新增一组更“活”的**核心用户流程**套件：

- 覆盖 core pillars：tools / skills / hooks / permissions / sessions(resume) / human-in-the-loop
- 允许合理的模型/网络抖动，用 pass-rate 门禁（例如 0.8–0.9）管理
- 产出可追溯证据：runner 报告（JSON/MD）+ 失败归因（network/model/regression）

## Non-Goals

- 不替代全量 `e2e_tests` discover（完整回归仍保留）。
- 不测试 Gateway/MCP。
- 不测试 CLI PTY/ConPTY（另有人负责）。
- 不引入 LLM-as-a-judge 作为主裁判（避免自证循环）。

## Requirements

### REQ-0030-001 — Add a core flows suite (stochastic lane)

新增 `e2e_tests.core_flows` 作为独立套件入口（不被 `e2e_*.py` discover 自动包含），包含若干真实用户流程型用例（尽量使用落盘与 tool events 断言）。

### REQ-0030-002 — Gate core flows by pass-rate (not single-run)

提供可复制的门禁命令（默认推荐）：

- `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows --runs 5 --min-pass-rate 0.8`

### REQ-0030-003 — Keep smoke_core as hard-invariant gate

明确约束：

- `e2e_tests.smoke_core` 仍作为 hard-invariant 门禁，推荐 `--min-pass-rate 1.0`。

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest -v e2e_tests.core_flows` exit code=0（单次运行能通过，但不作为门禁口径）
2) `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows --runs 5 --min-pass-rate 0.8` exit code=0
3) `python scripts/model_driven_e2e.py --suite e2e_tests.smoke_core --runs 3 --min-pass-rate 1.0` exit code=0
4) runner 报告包含：pass-rate、失败归因、失败用例列表与每-run 摘要

