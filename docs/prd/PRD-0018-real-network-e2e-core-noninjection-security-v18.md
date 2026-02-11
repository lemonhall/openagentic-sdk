# PRD-0018 — Real-Network E2E (Core Non-Injection + Security Boundaries v18)（真实网络 E2E：核心非注入 + 安全边界 v18）

## Vision

把核心 SDK 的真实网络 E2E 再推进一档：

- **非注入更真**：新增更多“模型自主选择工具”的用户流程回归（以落盘产物为准）。
- **安全边界可回归**：文件类工具（Read/Write/Edit）在默认安全假设下，不应允许路径遍历/逃逸到 project root 外；并且要能兼容 Windows 下 provider 输出的 POSIX 风格路径而不引入误映射风险。
- **分层跑法**：提供 smoke/full 的可复制命令（减少开发迭代摩擦；full 仍是 DoD）。

## Non-Goals

- 不测试 MCP / Gateway。
- 不做不可控网络故障（429/断网）强复现；本版聚焦可复现的对抗路径。

## Requirements

### REQ-0018-001 — Non-injected Write→Read roundtrip persists to disk（真实网络）

新增 E2E（不注入）：提示模型用 `Write` 创建文件，再 `Read` 校验，并最终回复固定 OK。
断言：磁盘内容与 tool.result 均可验证。

### REQ-0018-002 — Non-injected multi-tool chain (Glob/Grep→Edit) persists to disk（真实网络）

新增 E2E（不注入）：提示模型用 `Glob/Grep` 找到目标文件并定位占位符，再 `Edit` 替换为 token，最后 `Read` 校验。
断言：落盘内容确实变化 + 发生 `tool.use(Edit)`。

### REQ-0018-003 — Non-injected permission default prompts for Edit（真实网络）

新增 E2E（不注入）：`permission_mode="default"` 下，模型尝试使用 `Edit` 时必须走 prompt（`user.question`），并在自动回答 yes 后成功执行。

### REQ-0018-004 — Session resume (non-injected) can read earlier written artifact（真实网络）

新增 E2E（不注入）：Turn1 用工具写入落盘，记录 session_id；Turn2 resume 同 session 并通过工具读回 token。
断言：事件落盘可用 + tool.loop 可继续。

### REQ-0018-005 — Security: relative path traversal is blocked (Read)（真实网络）

新增 E2E（可注入，确定性）：注入 `Read(file_path="../escape.txt")`，要求被阻止并返回 tool.result error（不泄露内容）。

### REQ-0018-006 — Security: relative path traversal is blocked (Write)（真实网络）

新增 E2E（可注入，确定性）：注入 `Write(file_path="../evil.txt")`，要求被阻止且不在 project root 外创建文件。

### REQ-0018-007 — Windows compatibility: POSIX absolute filePath does not break core tools（真实网络）

新增 E2E（可注入，确定性；Windows-only）：注入 `Read`，只提供 `filePath="/mnt/data/a.txt"`（并让 `file_path` 为空/缺失），仍能正确读到 `ctx.cwd` 下的 `a.txt`。

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` exit code=0
2) 新增用例覆盖 REQ-0018-001..007

