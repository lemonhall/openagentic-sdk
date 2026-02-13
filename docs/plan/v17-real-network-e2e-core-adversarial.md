# v17 Plan — Real-Network E2E (Core Adversarial + Non-Injection)（真实网络 E2E：核心对抗 + 非注入）

## Goal

把核心模块的真实网络 E2E 从“happy-path + 少量护栏”推进到“流程化 + 对抗性 + 更高非注入比例”，并用全量 `e2e_tests` 作为可回归证据。

## PRD Trace

- REQ-0017-001
- REQ-0017-002
- REQ-0017-003
- REQ-0017-004
- REQ-0017-005

## Scope

做：
- 新增 5 个真实网络 E2E（核心模块：`skill/tools/runtime_core/hooks/permissions/sessions`）
- 用 `tool.result / 事件 / 落盘产物` 做硬断言
- **非注入**用例允许少量重试（最多 3 次）以对冲模型波动，但断言必须落在“磁盘/事件”上

不做：
- 不引入第三方依赖
- 不做 MCP/Gateway
- 不做不可控网络故障（429/断网）强行复现

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` exit code=0
2) 新增用例覆盖 REQ-0017-001..005

## Evidence（填写为可复现证据）

- Date: 2026-02-11
- `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` → OK（Ran 45 tests in ~365s）

## Steps（Strict）

1) Red：先落地 E2E（先写断言口径，再写用例）
2) Green：必要时修 core（只修使测试可复现的最小行为差异）
3) Verify：跑 DoD 命令并写回 Evidence
4) Delta：在 `v17-index` 回填“愿景 vs 现实”的差异与取舍
