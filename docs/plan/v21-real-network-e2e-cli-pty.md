# v21 Plan — Real-Network E2E (CLI PTY Suite)（真实网络 E2E：CLI 真 TTY/PTY 测试套件）

## Goal

为 `openagentic_cli` 建立一套独立的、真实网络、真交互（TTY/PTY）的 e2e 套件，并把断言锚定在可回归证据（落盘 events.jsonl + 确定性输出）上。

## PRD Trace

- REQ-0021-001
- REQ-0021-002
- REQ-0021-003
- REQ-0021-004
- REQ-0021-005
- REQ-0021-006
- REQ-0021-007

## Scope

做：
- 新增独立套件 `e2e_cli_tests/`（显式运行才执行；需要 POSIX `pty`）
- 覆盖 `oa chat` 的 REPL 基础命令与会话落盘（help/exit、多轮、resume/logs）
- 补齐 `/new`、paste 两类输入语义（/paste 与 bracketed paste）

不做：
- 不引入第三方依赖（expect/pexpect 等）
- 不覆盖 Windows 原生 console 的差异（该类测试另立套件）

## Acceptance (DoD)

必须全部满足：

1) WSL2/Linux/macOS 下：
   - `python -m unittest discover -s e2e_cli_tests -p "e2e_*.py" -v` exit code=0
2) 断言策略满足：
   - “会话/输入语义”以 `events.jsonl` 为准（避免模型输出不确定）
   - “REPL 命令分支”以 stdout 关键字 + exit code 为准
3) 测试隔离满足：
   - 每个用例使用独立临时目录作为 `OPENAGENTIC_SDK_HOME`
   - 设置 `OPENCODE_TEST_HOME` / `XDG_CONFIG_HOME` 防止读取用户全局 opencode 配置

## Evidence（填写为可复现证据）

- Date: 2026-02-11
- `python -m unittest discover -s e2e_cli_tests -p "e2e_*.py" -v` → 部分通过（已有：help/exit、多轮落盘、resume/logs；待补：/new、paste）

## Steps（Strict）

1) Analysis：明确 PTY e2e 的不稳定来源与隔离策略
   - 退出条件：无需人工输入即可运行到结束（无阻塞 prompt）
   - 关键约束：必须在 pty/TTY 下运行（非 pipe）

2) Red：为缺口写测试（先失败）
   - 新增 `e2e_cli_tests/e2e_cli_repl_new_session_real.py`（覆盖 REQ-0021-005）
   - 新增 `e2e_cli_tests/e2e_cli_repl_paste_modes_real.py`（覆盖 REQ-0021-006）

3) Green：最小实现/修复，使新测试稳定绿
   - 优先修复 `openagentic_cli/repl.py` 的可回归交互语义（必要时加 env 开关）
   - 禁止为了“让测试过”而放松安全边界（例如权限门/路径约束）

4) Verify：跑 full 并写回 Evidence
   - `python -m unittest discover -s e2e_cli_tests -p "e2e_*.py" -v`

5) Delta：在 `docs/plan/v21-index.md` 更新“愿景 vs 现实”

## Notes

### 运行命令（PowerShell）

```powershell
wsl -e bash -lc 'cd /mnt/e/development/openagentic-sdk && python -m unittest discover -s e2e_cli_tests -p "e2e_*.py" -v'
```

### 环境变量

- `.env`：测试 harness 会 best-effort 加载仓库根目录 `.env`（`openagentic_cli` 本身不自动加载）。
- 最少必需：`RIGHTCODE_API_KEY`（或 `OPENAI_API_KEY`）。

