# v5 Plan — Offline E2E Suite Expansion（离线 E2E 覆盖扩展）

## Goal

把离线 E2E 覆盖扩展到核心模块：Skill / SlashCommand（直执行）/ PermissionGate / Compaction（legacy overflow）。

## PRD Trace

- REQ-0005-001
- REQ-0005-002
- REQ-0005-003
- REQ-0005-004
- REQ-0005-005

## Scope

做：
- 在 `e2e_tests_offline/` 新增 4 个 E2E 用例（Skill/Slash/Perm/Compaction）
- README 列出覆盖清单

不做：
- 不改生产逻辑（除非测试暴露真实缺陷）
- 不新增第三方依赖

## Acceptance (DoD)

必须全部满足：

1) WSL2：`wsl -e bash -lc "cd /mnt/e/development/openagentic-sdk && python3 -m unittest -q"` exit code=0
2) Windows：`python -m unittest discover -s e2e_tests_offline -p "e2e_*.py" -v` exit code=0
3) 新增用例满足离线约束：不读取 `RIGHTCODE_*`、不发真实网络请求

## Evidence（填写为可复现证据）

- Date: 2026-02-11
- WSL2：`wsl -e bash -lc "cd /mnt/e/development/openagentic-sdk && python3 -m unittest -q"` → OK（345 tests）
- Windows：`python -m unittest discover -s e2e_tests_offline -p "e2e_*.py" -v` → OK（8 tests）

## Steps（Strict）

1) Red：先写 4 个 E2E 用例断言（各自 provider 先抛 AssertionError 证明断言生效）
2) Green：补齐 fake provider 行为，让断言通过
3) README：更新覆盖清单
4) Verify：跑 WSL2 全量 unittest
5) Verify：跑 Windows 离线 E2E discover
6) 写回 Evidence，并更新 `docs/plan/v5-index.md` 的状态与差异
