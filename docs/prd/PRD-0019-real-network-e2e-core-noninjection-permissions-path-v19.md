# PRD-0019 — Real-Network E2E (Core Non-Injection + Permissions + Path Semantics v19)（真实网络 E2E：核心非注入 + 权限 + 路径语义 v19）

## Vision

继续把核心 SDK 的真实网络 E2E 推向“更真、更硬、更安全”：

- **非注入更真**：增加 2–3 条更长的非注入工作流（Skill 驱动、多工具链、落盘为准）。
- **权限语义可回归**：覆盖 `permission_mode="acceptEdits"` 的关键语义（Edit/Write 自动允许、其他仍需 prompt），以及“同轮多 tool_calls”混合场景。
- **路径语义纠偏**：文件工具的相对路径应以 `cwd` 为基准解析，同时以 `project_dir` 作为安全根；并拒绝 Windows 下未知 POSIX 绝对路径（例如 `/etc/hosts`）的误映射风险。

## Non-Goals

- 不测试 MCP / Gateway。
- 不追求制造不可控网络故障（429/断网）复现。

## Requirements

### REQ-0019-001 — Non-injected long workflow via Skill (Write→Glob/Grep→Edit→Read)（真实网络）

新增 E2E（不注入）：skill 指令驱动模型完成：
1) Write 创建目标文件；
2) Glob/Grep 定位 PLACEHOLDER；
3) Edit 替换为 token；
4) Read 验证；
断言：磁盘落盘 + 至少出现 `tool.use(Edit)` + 最终回复 OK。

### REQ-0019-002 — Permissions: acceptEdits auto-allows Edit, prompts for Read (same run)（真实网络）

新增 E2E（可注入，确定性）：`permission_mode="acceptEdits"` + `user_answerer=yes`：
- 注入一个 Read + 一个 Edit；
- Read 必须产生 `user.question`；
- Edit 不应产生 `user.question`（自动 allow）且成功执行；
断言两条路径均存在。

### REQ-0019-003 — Permissions: prompt mixed deny/allow across 3 tool_calls in one output（真实网络）

新增 E2E（可注入，确定性）：PermissionGate `prompt` + answers `no/yes/yes`：
同一轮 model output 内包含 3 个 tool_calls：
- 第 1 个被拒绝（PermissionDenied tool.result）；
- 第 2/3 个成功执行；
断言 loop 不短路。

### REQ-0019-004 — Path semantics: relative paths resolve from cwd but are confined under project_dir（真实网络）

新增 E2E（可注入，确定性）：设置 `cwd=subdir`、`project_dir=root`：
- 注入 `Read(file_path="../a.txt")` 应成功（仍在 project 内）；
- 注入 `Read(file_path="../../escape.txt")` 应失败（逃逸）。

### REQ-0019-005 — Windows security: unknown POSIX absolute paths are rejected (no basename fallback)（真实网络）

新增 E2E（Windows-only，可注入，确定性）：注入 `Read(filePath="/etc/hosts")`（且 `file_path=""`）：
应返回 tool.result error（不读取任意本地 hosts/敏感文件）。

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` exit code=0
2) 新增用例覆盖 REQ-0019-001..005

