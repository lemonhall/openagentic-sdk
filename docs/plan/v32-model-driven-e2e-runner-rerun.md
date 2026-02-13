# v32 Plan — Model-Driven E2E (Runner Rerun + Flake Triage)（模型驱动 E2E：失败复跑与抖动归因）

## Goal

增强 `model_driven_e2e.py`：失败时自动 rerun 失败用例，区分 flake vs persistent，提升 triage 可用性，但不改变门禁口径。

## PRD Trace

- REQ-0032-001
- REQ-0032-002

## Scope

做：

- runner 增加 `--rerun-failures` / `--rerun-timeout-s`
- 解析 unittest 输出中的 test id 并 rerun（`python -m unittest -v <test_id>`）
- 报告增加：rerun 明细 + flake/persistent 聚合
- 更新 `AGENTS.md` / `skills/model-driven-e2e/SKILL.md` 的推荐命令
- 实跑并写回 Evidence

不做：

- 不改变 pass-rate 门禁的计算口径（rerun 不影响 gate）
- 不把 core_flows 变 injected

## Acceptance (DoD)

必须全部满足：

1) `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows --runs 5 --min-pass-rate 0.8 --rerun-failures 1` exit code=0
2) 报告 JSON 包含：`rerun_results`、`flake_test_counts`、`persistent_test_counts`

## Evidence（填写为可复现证据）

- Date: 2026-02-12
- `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows --runs 5 --min-pass-rate 0.8 --rerun-failures 1` → OK（Runs=5, Passes=5, pass_rate=1.000）
- Report dir: `.openagentic_e2e_reports/20260212T043500Z-e2e_tests.core_flows-pid13696/`
