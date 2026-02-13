# PRD-0028 — Model-Driven E2E Runner (Core Smoke Gate v28)（模型驱动 E2E 运行器：核心 Smoke 门禁 v28）

## Vision

把 LLM/真网络 e2e 从“单次确定性测试”升级为**可工程化的随机系统门禁**：

- 我（Agent）来跑：自动多次运行、自动归因、自动出报告
- 对核心 smoke：提供可复制的一条命令（Windows/PowerShell 友好）
- 输出“证据优先”的报告：包含 pass-rate、失败分类（网络/模型抖动/疑似回归）与关键日志片段

## Non-Goals

- 不引入 LLM-as-a-judge 作为主裁判（避免自证循环）；优先以 trace/tool.result/落盘为证据。
- 不替代所有传统单测/静态检查；这是对真网络 e2e 的补强。
- 不测试 Gateway/MCP。
- 不涉及 CLI PTY/ConPTY（另有人负责）。

## Requirements

### REQ-0028-001 — Provide a stable runner entrypoint

提供一个可复制的运行入口（脚本/模块），支持：

- 指定测试套件（默认 `e2e_tests.smoke_core`）
- 指定运行次数 `runs`
- 指定门禁阈值 `min_pass_rate`
- 指定 timeout
- 输出 JSON 报告（机器可读）与简要文本摘要（人类可读）

### REQ-0028-002 — Failure triage (network vs model vs regression)

runner 对失败进行最小可用的自动归因：

- **network-ish**：出现明显上游错误信号（HTTP 429/5xx、timeout、连接错误等）
- **model-ish**：出现“模型未按步骤完成/未在预算步数内完成”等典型失败模式
- **regression-ish**：其它失败（默认保守归因），并输出失败用例列表

### REQ-0028-003 — Preserve a hard-invariant lane

文档中明确：对核心协议/安全/落盘等“硬不变量”，仍以 100% 通过为目标；runner 只是把随机性纳入门禁与归因，而不是放松硬约束。

## Acceptance (DoD)

必须全部满足：

1) `python scripts/model_driven_e2e.py --suite e2e_tests.smoke_core --runs 3 --min-pass-rate 1.0` exit code=0
2) 运行后在 report_dir 产生：
   - `run_report.json`（或同等的机器可读报告）
   - `run_report.md` / stdout 摘要（可选，但必须有人类可读摘要）
3) 文档落地：v28 PRD + Plan + Index
4) 方法固化：新增 project skill（`skills/model-driven-e2e/`），并在 `AGENTS.md` 中记录该范式与命令

