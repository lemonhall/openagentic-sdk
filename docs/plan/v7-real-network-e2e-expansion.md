# v7 Plan — Real-Network E2E Expansion（真实网络 E2E 扩展）

## Goal

在 `e2e_tests/` 新增 5 个真实网络 E2E，用更稳定的断言覆盖 provider/runtime 的核心路径。

## PRD Trace

- REQ-0007-001
- REQ-0007-002
- REQ-0007-003
- REQ-0007-004
- REQ-0007-005

## Scope

做：
- 新增 5 个 `e2e_tests/e2e_*.py`
- 不改变现有 e2e 的定位与运行方式

不做：
- 不做重成本/高不确定性 E2E（如必须模型多次工具调用的流程）
- 不做费用不可控的长 prompt / 大输出

## Acceptance (DoD)

必须全部满足：

1) 配好环境变量后（至少 `RIGHTCODE_API_KEY`），运行：
   - `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v`
   exit code=0
2) 新增用例覆盖 PRD 的 5 条需求（REQ-0007-001..005）

## Evidence（填写为可复现证据）

- Date: 2026-02-11
- `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` → OK（13 tests）

## Notes

- v7 新增用例在无 `RIGHTCODE_API_KEY` 的环境下会直接报错（符合“真实网络 E2E 必须显式配置”的定位）。
- 若你希望“未配置 env 时自动 skip”，需要单开 PRD（避免把缺配置伪装成绿）。

## Steps（Strict）

1) Red：先写 5 个 E2E 文件（断言尽量“硬”且低波动）
2) Green：仅调整测试自身（不改生产逻辑）直到可跑
3) 你本机配置 `RIGHTCODE_API_KEY` 后执行 DoD 命令并把输出粘到 Evidence
