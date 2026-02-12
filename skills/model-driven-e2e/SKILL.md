---
name: model-driven-e2e
description: Use when running or designing real-network E2E tests for LLM/agent systems that show nondeterminism (model sampling, network flake, rate limits), and you need pass-rate gates, automatic triage, and evidence-first assertions (trace/tool.result/disk) instead of brittle single-run expectations.
---

# Model-Driven E2E（模型驱动端到端测试）

## Overview

LLM/Agent + 真网络依赖的 E2E 是“随机系统”。本技能的核心原则是：**分层断言 + 统计门禁 + 证据归因**，让失败可解释、可追溯、可恢复，而不是把测试写得越来越死。

## When to Use

适用场景（触发词/症状）：

- “真网络 e2e 偶发失败 / flaky / 抖动 / 429 / 5xx / timeout”
- “模型有时不按步骤走 / 预算步数内没完成”
- “我不想手动跑测试，需要 agent 自动跑、自动复跑、自动归因”
- “传统 e2e 写死期望值导致套件越来越呆板”

不适用：

- 纯单元测试（确定性函数）——直接用传统断言即可
- UI 像素级截图对比——这类更适合专用视觉回归工具

## Core Pattern

把断言拆成两条“车道”：

1) **硬不变量（Hard Invariants）**：协议/安全/落盘/结构化事件 —— 目标是 **100%**（失败基本视为回归）
2) **随机行为层（Stochastic Behaviors）**：模型规划/工具选择/自然语言细节 —— 用 **多次运行 + pass-rate 阈值 + 失败归因** 管理

> 注意：随机层的“通过率门禁”不是放水，它是把不可避免的随机性工程化；硬不变量仍必须硬。

## Quick Reference（openagentic-sdk）

**高频 smoke（推荐日常）：**

- 单次（传统）：`python -m unittest -v e2e_tests.smoke_core`
- 模型驱动（推荐）：`python scripts/model_driven_e2e.py --suite e2e_tests.smoke_core --runs 3 --min-pass-rate 1.0`

**看报告：**

- runner 默认输出到：`.openagentic_e2e_reports/<timestamp>/run_report.json` 与 `run_report.md`

## Failure Triage（最小可用归因）

runner 的默认归因口径（可扩展）：

- `network`：HTTP 429/5xx、超时、连接/DNS/TLS 等明显上游信号
- `model`：典型“未按步骤完成/未在预算步数内完成”的失败模式（e.g. `model did not complete ...`）
- `regression`：其它失败（默认保守），需要人工/进一步证据定位

## Evidence-First Assertions（写用例时的优先级）

优先断言（从强到弱）：

1) 磁盘落盘（文件内容是否真的变了）
2) `events.jsonl` 事件（例如：禁止落 `assistant.delta`；resume append-only；权限 prompt 的 `user.question`）
3) `tool.use` / `tool.result`（结构化字段与 error_type）
4) 最后才用 `final_text`（尽量只做确认性信号）

## Common Mistakes

- 把 flaky 当作“测试写得不够死”，越写越复杂反而更脆
- 用 `final_text` 当主断言，导致 prompt 轻微变化就全红
- 让“被测模型”自己当裁判（LLM-as-a-judge）而没有校准/交叉裁判/证据锚定

## Red Flags — STOP and Start Over

- “跑一次过了就算了”
- “失败就手动再跑几次，不留证据”
- “为了稳定把断言都删了/改成 contains('OK')”
- “把硬不变量也按 pass-rate 放过”

**出现以上任一条：停下，回到分层断言 + 证据归因。**

