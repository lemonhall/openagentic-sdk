# PRD-0032 — Model-Driven E2E (Runner Rerun + Flake Triage v32)（模型驱动 E2E：失败复跑与抖动归因 v32）

## Vision

在不把 e2e 用例写死的前提下，让 runner 更智能、更可解释：

- 当某次 suite 运行失败时，自动解析失败用例（unittest test id）
- 对失败用例做小成本 rerun（仅 rerun 失败项，而不是整套重跑）
- 在报告中区分：
  - **flake**：初次失败但 rerun 通过
  - **persistent**：初次失败且 rerun 仍失败

## Non-Goals

- 不修改 smoke_core 的 hard-invariant 门禁口径（仍建议 pass-rate=1.0）。
- 不把 `core_flows` 改 injected（保持随机层“活”）。
- 不引入 LLM-as-a-judge。

## Requirements

### REQ-0032-001 — Runner reruns failing test ids

runner 提供参数：

- `--rerun-failures N`：对每次失败的 run，将失败用例列表各 rerun N 次（默认 0）
- `--rerun-timeout-s`：单条 rerun 的 timeout

并在报告 JSON/MD 中输出：

- `rerun_results`（每条失败用例的 rerun 结果）
- `flake_test_counts` / `persistent_test_counts`（聚合）

### REQ-0032-002 — Keep pass-rate gate unchanged

rerun 仅用于 triage 与证据，不改变 pass-rate 门禁本身的计算口径（以“原始 runs 的通过数”计算）。

## Acceptance (DoD)

必须全部满足：

1) `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows --runs 5 --min-pass-rate 0.8 --rerun-failures 1` exit code=0
2) 生成报告中包含 `rerun_results` 字段与 flake/persistent 聚合字段
3) 文档落地：v32 PRD + Plan + Index；AGENTS.md / skill 更新入口命令

