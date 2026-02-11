# v6 Plan — Offline E2E More Core Tooling（离线 E2E：更多核心 Tool/Core 覆盖）

## Goal

在 `e2e_tests_offline/` 新增 3 个离线 E2E 用例，覆盖 AskUserQuestion / SlashCommand(tool) / tool error serialization。

## PRD Trace

- REQ-0006-001
- REQ-0006-002
- REQ-0006-003

## Scope

做：
- 新增 3 个离线 E2E 测试文件（`e2e_*.py`）
- 必要时补最小单测（只覆盖本次新增链路）

不做：
- 不改生产逻辑（除非测试暴露真实缺陷）
- 不引入三方依赖

## Acceptance (DoD)

必须全部满足：

1) WSL2：`wsl -e bash -lc "cd /mnt/e/development/openagentic-sdk && python3 -m unittest -q"` exit code=0
2) Windows：`python -m unittest discover -s e2e_tests_offline -p "e2e_*.py" -v` exit code=0
3) 离线约束：不读取 `RIGHTCODE_*`、不发真实网络请求

## Evidence（填写为可复现证据）

- Date: 2026-02-11
- WSL2：`wsl -e bash -lc "cd /mnt/e/development/openagentic-sdk && python3 -m unittest -q"` → OK（346 tests）
- Windows：`python -m unittest discover -s e2e_tests_offline -p "e2e_*.py" -v` → OK（11 tests）

## Steps（Strict）

1) Red：先写 3 个 E2E 用例断言（provider 先做强断言）
2) Green：补齐 fake provider / fixtures，让断言通过
3) Verify：跑 WSL2 全量 unittest
4) Verify：跑 Windows 离线 E2E discover
5) 写回 Evidence，并更新 `docs/plan/v6-index.md` 的状态与差异
