# v18 Plan — Real-Network E2E (Core Non-Injection + Security Boundaries)（真实网络 E2E：核心非注入 + 安全边界）

## Goal

继续夯实核心模块的真实网络 E2E：
- 拉高非注入用户流程比例（以落盘产物/事件为硬断言）；
- 把文件类工具的路径安全边界做成可回归证据；
- 给出 smoke/full 的可复制命令（full 仍是 DoD）。

## PRD Trace

- REQ-0018-001
- REQ-0018-002
- REQ-0018-003
- REQ-0018-004
- REQ-0018-005
- REQ-0018-006
- REQ-0018-007

## Scope

做：
- 新增 7 个 `e2e_tests/e2e_*.py`
- 必要时对 `tools` 做最小修复（只为“跨平台稳定 + 安全边界”）
- 证据以 `tool.result / 事件 / 落盘文件` 为主

不做：
- 不引入第三方依赖
- 不做 MCP / Gateway

## Smoke / Full

- Smoke（快速验证核心链路，非 DoD）：挑选 6–10 个最关键用例单独跑（后续补充到 `docs/plan/v18-index.md` 的清单）
- Full（DoD，真实回归证据）：
  - `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v`

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` exit code=0
2) 新增用例覆盖 REQ-0018-001..007

## Evidence（填写为可复现证据）

- Date: 2026-02-11
- `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` → OK（Ran 52 tests in ~402s）

## Steps（Strict）

1) Red：先写 E2E（断言先行）
2) Green：最小修复 tools/runtime_core（不做无关重构）
3) Verify：跑 full 并写回 Evidence
4) Delta：在 v18-index 填“愿景 vs 现实”
