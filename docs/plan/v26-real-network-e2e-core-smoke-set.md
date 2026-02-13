# v26 Plan — Real-Network E2E (Core Smoke Set)（真实网络 E2E：核心 Smoke 集）

## Goal

建立一组真实网络的核心 smoke 集，供日常高频回归（2–3 分钟）使用；并在文档中固化入口命令与覆盖范围。

## PRD Trace

- REQ-0026-001
- REQ-0026-002

## Scope

做：
- 新增 `e2e_tests/smoke_core.py` 作为 smoke 入口（不被 `e2e_*.py` discover 自动包含）
- 新增 v26 PRD + Plan + Index 文档

不做：
- 不改 CLI PTY/ConPTY
- 不改 MCP/Gateway

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest -v e2e_tests.smoke_core` exit code=0

## Evidence（填写为可复现证据）

- Date: 2026-02-12
- `python -m unittest -v e2e_tests.smoke_core` → OK（10 tests, 74.111s）

## Steps（Strict）

1) Red：先定义 smoke 集的覆盖范围与入口
2) Green：落地入口并跑通
3) Verify：写回 Evidence
