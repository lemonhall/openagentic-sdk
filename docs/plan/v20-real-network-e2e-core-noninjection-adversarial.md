# v20 Plan — Real-Network E2E (Core Non-Injection + Adversarial Paths)（真实网络 E2E：核心非注入 + 对抗路径）

## Goal

继续按“更真 e2e”的方向推进：
- 增加非注入流程覆盖（以落盘产物为准）；
- 增加可复现的对抗路径（工具输入错误、绝对路径越界）；
- 维持全量真网 e2e 作为硬证据。

## PRD Trace

- REQ-0020-001
- REQ-0020-002
- REQ-0020-003
- REQ-0020-004

## Scope

做：
- 新增 4 个真实网络 E2E（其中 2 个非注入长流程）
- 断言以 `tool.result / 落盘文件 / 事件序列` 为主

不做：
- 不引入第三方依赖
- 不测试 MCP / Gateway

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` exit code=0
2) 新增用例覆盖 REQ-0020-001..004

## Evidence（填写为可复现证据）

- Date: 2026-02-11
- `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` → OK（Ran 61 tests in ~459s）

## Steps（Strict）

1) Red：先写 E2E（断言先行）
2) Green：必要时最小修复（只修使测试可复现的核心行为）
3) Verify：跑 full 并写回 Evidence
4) Delta：在 v20-index 填“愿景 vs 现实”
