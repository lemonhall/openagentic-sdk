# v24 Plan — Windows 11 CLI E2E（Windows 原生交互式 e2e；ConPTY 作为后续加强）

## Goal

建立 `e2e_cli_win_tests/`：在 Windows 原生环境下端到端验证 `openagentic_cli` 的交互命令与真实网络调用。

交付顺序：
- **Phase 1（v24）**：stdio pipes 驱动（稳定、可回归，作为默认测试驱动）
- **Phase 2（后续版本）**：ConPTY（Pseudo Console）驱动（目标：真 TTY/VT 语义）

## PRD Trace

- REQ-0024-001
- REQ-0024-002
- REQ-0024-003
- REQ-0024-004
- REQ-0024-005

## Scope

做：
- Windows e2e suite（独立、隔离、opt-in）
- 最小 e2e：bypass 无启动 prompt、/help、/exit（默认 pipes 驱动）
- 多行输入 e2e：/paste 与 bracketed paste markers
- 运行隔离：`OPENAGENTIC_SDK_HOME` / `OPENCODE_TEST_HOME` / `XDG_CONFIG_HOME`
- ConPTY harness（实验性保留在套件内；不作为 v24 完成门槛）

不做：
- 不支持 Windows 10
- 不引入第三方依赖（pexpect/pywinpty 等）

## Acceptance (DoD)

必须全部满足：

1) Windows 11 下：
   - `python -m unittest discover -s e2e_cli_win_tests -p "e2e_*.py" -v` exit code=0
2) 断言策略：
   - REPL 命令分支以 stdout 关键字 + exit code 为准
   - 多行输入以“未触发 REPL 命令分支 + 能跑通一次固定 token 回复”为准（避免模型波动造成脆弱）

## Evidence（填写为可复现证据）

- Date: 2026-02-12
- `python -m unittest discover -s e2e_cli_win_tests -p "e2e_*.py" -v` → OK（Ran 2 tests）

## Steps（Strict）

1) Red：先写 Windows e2e（会失败）
2) Green：补齐 pipes 驱动 + 交互断言（/help /exit /paste）
3) Verify：跑全套并写回 Evidence
4) Delta：更新 `docs/plan/v24-index.md`（记录 ConPTY 延后原因与下一步）
