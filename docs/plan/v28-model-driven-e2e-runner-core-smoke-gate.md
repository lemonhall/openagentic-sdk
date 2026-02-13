# v28 Plan — Model-Driven E2E Runner (Core Smoke Gate)（模型驱动 E2E 运行器：核心 Smoke 门禁）

## Goal

落地一个“模型驱动”的真网络 e2e runner：能自动多次运行 `smoke_core`，做失败归因与 pass-rate 门禁，并产出可追溯证据。

## PRD Trace

- REQ-0028-001
- REQ-0028-002
- REQ-0028-003

## Scope

做：

- 新增 runner 脚本：`scripts/model_driven_e2e.py`
- runner 输出 JSON 报告（机器可读）+ 简要摘要（人类可读）
- runner 能对失败做最小归因（network/model/regression）
- 新增 project skill：`skills/model-driven-e2e/SKILL.md`
- 更新 `AGENTS.md`：固化“硬不变量 vs 随机层”的门禁理念与命令入口

不做：

- 不改 CLI PTY/ConPTY
- 不引入 LLM-as-a-judge 做主裁判
- 不改 MCP/Gateway

## Acceptance (DoD)

必须全部满足：

1) `python scripts/model_driven_e2e.py --suite e2e_tests.smoke_core --runs 3 --min-pass-rate 1.0` exit code=0
2) runner 生成报告文件（JSON 至少 1 个）
3) `python -m unittest -v e2e_tests.smoke_core` exit code=0（runner 前后都应一致）

## Evidence（填写为可复现证据）

- Date: 2026-02-12
- `python scripts/model_driven_e2e.py --suite e2e_tests.smoke_core --runs 3 --min-pass-rate 1.0` → OK（Runs=3, Passes=3, pass_rate=1.000）
- Report dir: `.openagentic_e2e_reports/20260212T025210Z/`

## Steps（Strict）

1) Red：写 PRD/Plan，定义门禁规则与 DoD
2) Green：实现 runner + 归因 + 报告产物
3) Verify：实跑 runner，并写回 Evidence
4) Refactor：把范式固化为 skill + AGENTS.md 规范
