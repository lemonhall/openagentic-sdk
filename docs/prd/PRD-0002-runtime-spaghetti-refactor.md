# PRD-0002: Runtime 意大利面重构（拆分 `openagentic_sdk/runtime.py`）

## Vision

把 `openagentic_sdk/runtime.py`（~1900 行）拆成一组**职责单一、可读、可验证**的小模块（目标：单文件 ~200 行量级），并保持：

- 行为不变（tests 作为证据）
- 对外 API 不变（`from openagentic_sdk.runtime import AgentRuntime, RunResult` 继续可用）
- 后续新增功能可以“加模块 + 接线”，而不是继续往同一坨文件里堆

## Background

当前 `openagentic_sdk/runtime.py` 同时承担：

- Provider protocol 检测与调用（legacy vs responses）
- session/events rebuild 与 compaction 触发
- tool loop（权限门、工具执行、特殊工具分支）
- SlashCommand 渲染（模板、shell、@file/@dir/@agent parts）
- MCP client lifecycle（local/remote）
- 以及大量 helper function

这种耦合让修改风险高、review 成本高、未来继续膨胀。

## Requirements

### REQ-0002-001 — 拆分为子目录模块，`runtime.py` 变薄

- 新增目录：`openagentic_sdk/runtime_core/`
- `openagentic_sdk/runtime.py` 仅作为薄 re-export/兼容层（目标 < 200 行）
- runtime 核心实现拆到多个模块，单模块目标 ~200 行量级（允许少量偏差，但禁止再出现单文件 1000+）

### REQ-0002-002 — Public API 保持不变

以下 import 必须继续工作（不改调用方）：

- `from openagentic_sdk.runtime import AgentRuntime, RunResult`

并且 `openagentic_sdk.api`（`query/run`）行为不变。

### REQ-0002-003 — 行为保持不变（证据=测试）

验收以测试为准：

- WSL2：`python3 -m unittest -q` 必须通过（342 tests）
- Windows：允许存在已知平台差异失败，但本 PRD 影响范围内的回归必须通过（见 v2 计划）

### REQ-0002-004 — 代码边界清晰（职责拆分）

至少拆出这些逻辑边界（模块名可调整）：

- provider protocol/输入构建/系统 prompt 注入
- tool loop/dispatch（含权限门）
- SlashCommand 渲染（模板 args、shell、@file/@dir/@agent parts 注入）
- compaction 触发与工具输出 prune（如果已在别处，可只做 glue）

## Non-Goals

- 不改功能、不改协议、不引入新依赖
- 不做 ruff 全量修复（避免跑偏）

## Risks

- 混入行为改动（通过全套 tests 防回归）
- 模块循环 import（通过清晰的依赖方向 + 小步提交避免）

