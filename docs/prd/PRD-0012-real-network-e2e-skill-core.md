# PRD-0012 — Real-Network E2E (Skill Core)（真实网络 E2E：Skill 核心语义）

## Vision

用真实网络 E2E 把 `Skill` 工具的核心语义做硬回归：
- 能从项目 `.claude/skills/**/SKILL.md` 正确加载；
- 项目 skills 对全局 skills 的覆盖优先级正确；
- `project_dir` 参数能改变索引/加载基准；
- 不存在的 skill 以 `tool.result` 错误返回，且错误信息包含可用 skills 提示。

## Non-Goals

- 不测试 MCP/Gateway。
- 不依赖模型“复述 skill 内容”；断言以 `tool.result` 输出为准。

## Requirements

### REQ-0012-001 — project overrides global skills（真实网络）

当全局与项目同时存在同名 skill 时，`Skill` 必须加载项目版本（`.claude`）并返回其内容/路径。

### REQ-0012-002 — Skill not found yields FileNotFoundError（真实网络）

请求不存在的 skill 时，必须得到 `tool.result`（`is_error=True`，`error_type="FileNotFoundError"`），且错误信息包含 Available skills 列表。

### REQ-0012-003 — project_dir argument changes base（真实网络）

传入 `project_dir`（相对路径）时，索引/加载基准必须以 `ctx.project_dir` 为根进行解析，并能加载该目录下的 `.claude/skills`。

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` exit code=0
2) 新增用例覆盖 REQ-0012-001..003

