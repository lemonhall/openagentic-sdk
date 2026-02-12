# v22 Plan — Real-Network E2E (Core Non-Injection Ratio)（真实网络 E2E：核心非注入占比）

## Goal

在不触碰 MCP/Gateway/CLI-PTY 的前提下，继续夯实核心模块真实网络 E2E，并把 `no_injection` 占比推进到 ≥ 30%（更贴近真实用户流程）。

## PRD Trace

- REQ-0022-001
- REQ-0022-002
- REQ-0022-003
- REQ-0022-004
- REQ-0022-005
- REQ-0022-006
- REQ-0022-007
- REQ-0022-008
- REQ-0022-009
- REQ-0022-010
- REQ-0022-011
- REQ-0022-012
- REQ-0022-013
- REQ-0022-014

## Scope

做：
- 新增 13 个 `e2e_tests/e2e_*_real_no_injection.py`
- 断言以“磁盘落盘 / events.jsonl” 为硬证据
- 全量跑 `e2e_tests` 作为 DoD 证据

不做：
- 不改 CLI PTY（另有人负责）
- 不加第三方依赖
- 不测 MCP/Gateway

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` exit code=0
2) 非注入用例占比 ≥ 30%（按 unittest 统计）

## Evidence（填写为可复现证据）

- Date: 2026-02-11
- `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` → OK（Ran 74 tests in ~750s；退出码 0）
- 非注入统计（约定：文件名包含 `no_injection`）：
  - `files=73 tests=74`
  - `noinj_files=23 noinj_tests=23`（占比 `23/74 ≈ 31.1%`）

## Steps（Strict）

1) Red：先落地非注入 E2E（断言以落盘/事件为准）
2) Green：必要时只做最小修复（仅为稳定性/一致性）
3) Verify：全量跑 DoD 命令并写回 Evidence
4) Delta：在 v22-index 填“愿景 vs 现实”的差异与取舍
