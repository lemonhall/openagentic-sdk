# PRD-0020 — Real-Network E2E (Core Non-Injection + Adversarial Paths v20)（真实网络 E2E：核心非注入 + 对抗路径 v20）

## Vision

继续提升核心 SDK 的真实网络 E2E 强度：

- **非注入长流程再加码**：以 “Skill/AskUserQuestion 驱动 + 多工具链 + 落盘产物” 的方式扩充非注入覆盖。
- **对抗路径系统化**：补齐“工具输入错误/绝对路径越界”等可复现负路径，确保 runtime 不短路、结果可机读。

## Non-Goals

- 不测试 MCP / Gateway。
- 不追求不可控网络故障（429/断网）复现；本版聚焦可复现的对抗路径与用户流程。

## Requirements

### REQ-0020-001 — Non-injected Glob/Grep→Edit modifies only the matched file（真实网络）

新增 E2E（不注入）：提示模型：
- Glob 枚举 `./d/*.txt`；
- Grep 查找包含 `PLACEHOLDER` 的文件（仅 1 个匹配）；
- Edit 替换为 token；
- Read 验证；
断言：目标文件落盘变化、其他候选文件未被修改。

### REQ-0020-002 — Non-injected AskUserQuestion→Write→Read pipeline persists to disk（真实网络）

新增 E2E（不注入）：模型必须先调用 AskUserQuestion 取 token，再 Write 落盘、Read 校验，最后回复固定 OK。

### REQ-0020-003 — Adversarial: tool input error does not short-circuit subsequent tool calls（真实网络）

新增 E2E（注入，确定性）：同一轮 model output 注入两个 Read：
- 第 1 个传非法 offset（例如 `-1`），应 tool.result error；
- 第 2 个正常 Read 必须仍然成功并读到 token。

### REQ-0020-004 — Security: absolute path outside project_dir is rejected（真实网络）

新增 E2E（注入，确定性）：创建一个位于 project_dir 外的文件（parent dir），注入 Read 使用其绝对路径：
- 必须 tool.result error；
- 输出与最终文本不得包含外部文件 token。

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` exit code=0
2) 新增用例覆盖 REQ-0020-001..004

