# PRD-0054 — Opencode Tests Checklist Parity v54（源头测试清单：对齐与补测）

## Vision

把 `docs/research/opencode-tests-checklist.md`（源头项目 tests 归纳）落到本仓库的核心模块上，形成**可回归、可追溯**的测试网：

- 对每个 P0/P1 能力点，要么有自动化测试证据（unit/offline-e2e/real-e2e 任一），要么明确标注为 **N/A（设计差异）**。
- 对“已实现但缺断言”的能力点补齐测试（优先 unit，其次 offline-e2e）。
- 对“未实现但清单里要求”的能力点不强行补测；改为写清楚“功能缺口/非目标”，避免用假测试掩盖真实差异。

## Background / Motivation

本仓库已经积累了大量核心模块的 unit/E2E 计划与覆盖，但源头项目（`opencode`）的 tests 套件在 **工具边界**（Read/Grep/Bash/custom-tools discovery 等）上有一些非常具体的回归点。

这批回归点若没有在本仓库形成同等强度的自动化断言，会导致：

- 迁移/对齐时行为回归难定位；
- 依赖提示词描述而非代码行为的“文档漂移”；
- E2E 失败时成本高（需要更快、更窄的 unit 断言辅助定位）。

## Non-Goals

- 不引入 `external_directory` 询问/归一化（本项目策略是直接拒绝 project_root 外路径）。
- 不实现 OpenCode 的 `apply_patch` 工具（本仓库使用 `Edit/NotebookEdit`）。
- 不为 `WebFetch` 引入“图片/附件分流”能力（当前统一 `text` 输出）。
- 不实现 OpenCode 的 PermissionNext ruleset（本仓库使用 `PermissionGate` 模式机）。
- 不新增 Structured Output（本仓库当前只保留 `Message.structured_output` 字段，未实现完整协议）。

## Requirements

### REQ-0054-001 — Checklist 对齐矩阵必须完整且可追溯

产出并维护对齐矩阵：

- 文件：`docs/research/opencode-tests-checklist-alignment-openagentic-sdk.md`
- 要求：对清单中 P0/P1 的能力点给出：
  - 覆盖状态：✅ / △ / ❌ / N/A
  - 证据：对应的 `tests/` 或 `e2e_tests_offline/` 或 `e2e_tests/` 路径
  - 设计差异：N/A 必须写清楚“为什么不适用”

### REQ-0054-002 — ReadTool P0/P1 边界补测（unit）

在 `tests/` 增加/补齐以下断言（最少覆盖一次）：

- 图片后缀（`.png/.jpg/.jpeg/.gif/.webp`）返回 `image`（base64）与 `mime_type`
- 非图片后缀（例如 `.fbs`）按文本读取（不应出现 `image/mime_type` 字段）
- project_root 外绝对路径与 `..` 穿越必须 `ValueError`
- Windows POSIX-like 路径映射：
  - `/mnt/data/<file>` 能保守映射到 project_root 下并可读取
  - 未知 POSIX abs（例如 `/etc/passwd`）必须拒绝（`ValueError`）
- `max_bytes` 截断行为可回归（按 bytes 截断，且不会抛解码异常）

### REQ-0054-003 — GrepTool P0/P1 边界补测（unit）

在 `tests/` 增加/补齐以下断言（最少覆盖一次）：

- 无匹配：`matches=[]`、`total_matches=0`、`truncated=False`
- `case_sensitive=false` 生效（IGNORECASE）
- CRLF 行尾：行号/分行结果稳定
- before/after context：返回列表内容正确
- `max_matches` 截断：达到上限立即返回并 `truncated=True`（返回 shape 稳定）

### REQ-0054-004 — BashTool P0/P1 边界补测（unit）

在 `tests/` 增加/补齐以下断言（最少覆盖一次）：

- `max_output_lines`：`output_lines_truncated=True` 且 `output` 只包含前 N 行
- 当 stdout/stderr/lines 任一截断且 `ctx.project_dir` 存在时：
  - `full_output_file_path` 必须落在 `<project_dir>/.openagentic-sdk/tool-output/`
  - 文件内容必须为 **完整 stdout+stderr（未截断）**
- Windows：stdout/stderr/output 中的 `/mnt/<drive>/...` 能归一化为 `X:\\...`（至少 1 条断言）

### REQ-0054-005 — Custom Tools 发现顺序与覆盖优先级必须明确并可测

为 Python custom tools 明确并锁定以下规则（以测试为准）：

- 发现 roots（从低到高优先级）：global config `${OPENCODE_CONFIG_DIR}` < project root < project pack `.opencode/`
- 发现 dirs（同一 root 内，从低到高优先级）：`tool/` < `tools/`
- 文件排序：同一目录内按文件名排序（确定性）
- 重名工具的覆盖：高优先级来源覆盖低优先级来源（最终进入 `ToolRegistry` 的工具实例来自最高优先级的那个文件）
- 导入失败隔离：某个 custom tool module import 失败时，CLI `build_options()` 不应崩溃（该工具缺失即可）

### REQ-0054-006 — ListTool 建议补 2–3 条 unit-level 快速回归（P1）

已有多条 E2E 覆盖的前提下，再补 unit-level 断言以降低定位成本：

- 树输出基本 shape（包含目录/文件）
- 忽略 junk dirs（`.git`/`node_modules`/`__pycache__` 等）
- limit 截断：`truncated=True` 且 `count==limit`

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest -q` exit code = 0
2) `docs/research/opencode-tests-checklist-alignment-openagentic-sdk.md` 中列出的 P0 缺口（❌）全部变为 ✅/△/N/A（△ 必须有明确后续计划或降级理由）
3) 新增测试不依赖真实网络、不读取真实密钥（如 `RIGHTCODE_*`、`TAVILY_API_KEY`）

