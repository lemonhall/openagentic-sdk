# v23 Plan — Real-Network E2E (CLI Subcommands)（真实网络 E2E：CLI 子命令覆盖）

## Goal

补齐 `openagentic_cli` 非 REPL 子命令的真实网络 E2E 覆盖，并保持可回归：

- 断言以 exit code / 机读输出（JSON）/ 落盘文件为主；
- 通过 `OPENAGENTIC_SDK_HOME` 强隔离，避免污染用户本机；
- 通过 `OPENCODE_TEST_HOME` / `XDG_CONFIG_HOME` 避免读取用户全局 opencode 配置导致不稳定。

## PRD Trace

- REQ-0023-001
- REQ-0023-002
- REQ-0023-003
- REQ-0023-004

## Scope

做：
- 增加 4 个 CLI e2e（`oa run` x2、share roundtrip、auth roundtrip）
- 为每个用例使用独立临时 home（`OPENAGENTIC_SDK_HOME`）
- 尽量避免 pty：子命令本身不需要真交互；（REPL 真交互已由 v21 覆盖）

不做：
- 不测 serve/acp 长驻服务
- 不测 MCP OAuth

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest discover -s e2e_cli_tests -p "e2e_*.py" -v` exit code=0
2) v23 新增用例覆盖 REQ-0023-001..004
3) 不泄露真实 key：auth 用例只能使用 fake key，并避免在断言失败时输出 key

## Evidence（填写为可复现证据）

- Date: 2026-02-11
- `python -m unittest discover -s e2e_cli_tests -p "e2e_*.py" -v` → OK（Ran 9 tests in ~76s；exit code=0）

## Steps（Strict）

1) Red：先写 E2E（断言先行）
   - `e2e_cli_tests/e2e_cli_run_json_real.py`
   - `e2e_cli_tests/e2e_cli_run_nostream_real.py`
   - `e2e_cli_tests/e2e_cli_share_roundtrip.py`
   - `e2e_cli_tests/e2e_cli_auth_roundtrip.py`

2) Green：必要时最小修复
   - 若 CLI 子命令在隔离环境下不可运行，优先修复“读取配置/默认路径/输出格式”的确定性问题

3) Verify：跑全套并写回 Evidence
   - WSL2（PowerShell）：`wsl -e bash -lc 'cd /mnt/e/development/openagentic-sdk && python -m unittest discover -s e2e_cli_tests -p \"e2e_*.py\" -v'`

4) Delta：在 `docs/plan/v23-index.md` 更新“愿景 vs 现实”
