# v4 Plan — Offline E2E Test Suite（离线端到端测试套件）

## Goal

新增一套不依赖外网/Key 的 E2E 测试，覆盖 SDK 核心用户流程（Core/Tool/Streaming/Resume），并把验证命令纳入里程碑 DoD。

## PRD Trace

- REQ-0004-001
- REQ-0004-002
- REQ-0004-003
- REQ-0004-004
- REQ-0004-005
- REQ-0004-006

## Scope

做：
- 新增 `e2e_tests_offline/`（unittest）
- 用 fake provider（不发网络请求）覆盖 4 条核心链路
- 写清晰 README，区分 offline E2E 与 real-network E2E

不做：
- 不改 `e2e_tests/` 的真实网络定位
- 不把 offline E2E 纳入 `python -m unittest -q` 默认发现（仍需显式 discover）
- 不引入 pytest/requests-mock 等新依赖

## Acceptance (DoD)

必须全部满足：

1) WSL2：`wsl -e bash -lc "cd /mnt/e/development/openagentic-sdk && python3 -m unittest -q"` exit code=0
2) Windows：`python -m unittest -q tests.test_query_messages_tool_loop_blocks` exit code=0
3) Windows：`python -m unittest discover -s e2e_tests_offline -p "e2e_*.py" -v` exit code=0
4) 离线 E2E 测试文件满足：
   - 不读取 `RIGHTCODE_*`
   - 不请求真实网络（provider 为内存 fake）
5) 至少 4 个离线 E2E 场景：
   - quickstart（Core run）
   - tool loop（TodoWrite）
   - streaming text
   - resume/previous_response_id

## Evidence（填写为可复现证据）

- Date: 2026-02-11
- WSL2：`wsl -e bash -lc "cd /mnt/e/development/openagentic-sdk && python3 -m unittest -q"` → OK（344 tests）
- Windows：`python -m unittest -q tests.test_query_messages_tool_loop_blocks` → OK（1 test）
- Windows：`python -m unittest discover -s e2e_tests_offline -p "e2e_*.py" -v` → OK（4 tests）

## Steps（Strict）

1) 写离线 E2E harness：`e2e_tests_offline/_harness.py`
2) Red：逐个补 4 个 E2E 测试文件（先写断言，再写 fake provider）
3) Green：补齐实现（仅测试代码/fixture），确保全部通过
4) Verify：跑 `python -m unittest -q`
5) Verify：跑离线 E2E discover 命令
6) 记录 evidence 到本计划文档，并在 `docs/plan/v4-index.md` 的差异区更新
