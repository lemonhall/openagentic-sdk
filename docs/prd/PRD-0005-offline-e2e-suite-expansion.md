# PRD-0005 — Offline E2E Suite Expansion（离线 E2E 覆盖扩展）

## Vision

把离线 E2E 从“能跑”提升到“**覆盖核心模块**”：在不依赖外网/Key 的前提下，对 **Skill / SlashCommand（直执行）/ PermissionGate / Compaction** 提供端到端回归保护。

## Background / Motivation

v4 已新增 `e2e_tests_offline/` 并覆盖 Core/Tool/Streaming/Resume 四条链路，但仍缺少对下列“核心模块”的整链路验证：

- Skill：模型请求 `Skill` tool → runtime 加载 SKILL.md → tool output 回传模型 → 继续对话
- SlashCommand（直执行）：用户输入 `/name` → runtime 在送模型前展开模板 + @file 注入
- PermissionGate：`permission_mode="prompt"` + `user_answerer` 自动答复的完整链路（包含 `user.question` 事件）
- Compaction：legacy provider 下 overflow 自动触发 compaction pass，并继续下一步

## Non-Goals

- 不覆盖真实网络 E2E（`e2e_tests/`）与费用相关路径。
- 不做 CLI 级别 E2E（子进程跑 `openagentic_cli`），避免平台/输出差异导致脆弱测试（后续单开 PRD）。
- 不引入 pytest 等新框架。

## Requirements

### REQ-0005-001 — 离线 E2E：Skill tool 链路

在 `e2e_tests_offline/` 新增至少 1 个用例覆盖：
- provider 返回 `ToolCall(name="Skill")`
- runtime 执行 SkillTool 并回传 `function_call_output`
- provider 能读取到 tool output 并返回最终文本

### REQ-0005-002 — 离线 E2E：SlashCommand 直执行 + @file 注入

新增至少 1 个用例覆盖：
- `.claude/commands/<name>.md` 存在
- 用户输入 `/name`
- runtime 在写入 `UserMessage` 前完成模板展开与 `@a.txt` 注入
- provider 看到的 user prompt 中包含被注入文件内容

### REQ-0005-003 — 离线 E2E：PermissionGate prompt + user_answerer

新增至少 1 个用例覆盖：
- `permission_mode="prompt"` 且 `interactive=False`
- 发生 `user.question` 事件
- `user_answerer` 返回 yes 后，tool 被实际执行并继续对话

### REQ-0005-004 — 离线 E2E：Legacy compaction overflow

新增至少 1 个用例覆盖：
- legacy provider（`complete(..., messages=...)`）
- 首次输出带 usage 触发 overflow（按 `CompactionOptions` 的数学规则）
- runtime 触发 `UserCompaction(auto=True, reason="overflow")`
- runtime 调用 compaction pass（tools=()），并写入 `AssistantMessage(is_summary=True)`
- 继续下一次模型调用并输出最终文本

### REQ-0005-005 — README 更新

`e2e_tests_offline/README.md` 中补充说明：离线 E2E 当前覆盖范围（列出场景清单）。

## Acceptance (DoD)

必须全部满足：

1) WSL2：`wsl -e bash -lc "cd /mnt/e/development/openagentic-sdk && python3 -m unittest -q"` exit code=0
2) Windows：`python -m unittest discover -s e2e_tests_offline -p "e2e_*.py" -v` exit code=0
3) 新增离线 E2E 至少 4 个（对应 REQ-0005-001..004），且不读取 `RIGHTCODE_*`

