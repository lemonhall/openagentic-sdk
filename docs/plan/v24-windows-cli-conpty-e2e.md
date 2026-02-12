# v24 Plan — Windows 11 CLI E2E（Windows 原生交互式 e2e；ConPTY/真 TTY 为默认驱动）

## Goal

建立 `e2e_cli_win_tests/`：在 Windows 原生环境下端到端验证 `openagentic_cli` 的交互命令与真实网络调用。

交付顺序：
- **Phase 1（v24）**：ConPTY（Pseudo Console / 真 TTY）驱动（默认；覆盖 VT input、回显、粘贴模式等真实终端语义）
- **Phase 2（对照/降级）**：stdio pipes 驱动（必要时用于对照排障与临时降级）

## PRD Trace

- REQ-0024-001
- REQ-0024-002
- REQ-0024-003
- REQ-0024-004
- REQ-0024-005

## Scope

做：
- Windows e2e suite（独立、隔离、opt-in）
- 最小 e2e：bypass 无启动 prompt、/help、/exit（默认 ConPTY 驱动）
- 多行输入 e2e：/paste 与 bracketed paste markers
- 运行隔离：`OPENAGENTIC_SDK_HOME` / `OPENCODE_TEST_HOME` / `XDG_CONFIG_HOME`
- stdio pipes harness（保留在套件内；用于对照/排障/临时降级）

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
- `python -m unittest discover -s e2e_cli_win_tests -p "e2e_*.py" -v` → OK（Ran 6 tests）

## Steps（Strict）

1) Red：先写 Windows e2e（会失败）
2) Green：补齐 ConPTY 驱动 + 交互断言（/help /exit /paste / typeahead）
3) Verify：跑全套并写回 Evidence
4) Delta：更新 `docs/plan/v24-index.md`（记录驱动策略变更与下一步）
