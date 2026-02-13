# PRD-0025 — Real-Network E2E (Core Non-Injection Negative Paths v25)（真实网络 E2E：核心非注入负路径 v25）

## Vision

在保持“真网络 + 真运行时 tool loop”的前提下，把一批核心 **负路径**（错误输入 / 权限拒绝 / 越界路径）用 **非注入** E2E 固化下来：

- 失败必须以 `tool.result(is_error=True)` 明确可机读；
- 失败之后 runtime/tool loop 必须可继续（不短路）；
- 安全边界必须无泄露（越界 token 不得出现在输出/最终文本）。

## Non-Goals

- 不测试 MCP / Gateway。
- 不测试 CLI PTY（另有并行工作流）。
- 不追求不可控网络故障（429/断网）复现。

## Requirements

### REQ-0025-001 — Non-injected Read invalid offset errors, then recovery Read succeeds（真实网络）

模型先对 `Read(offset=-1)` 触发输入错误（必须 tool.result error），随后再次 Read 成功，并正确返回文件 token。

### REQ-0025-002 — Non-injected acceptEdits allows Write without prompting（真实网络）

`PermissionGate(permission_mode="acceptEdits")` 下，Write 流程必须：
- 不产生 `user.question`
- 文件落盘正确

### REQ-0025-003 — Non-injected acceptEdits allows Edit without prompting（真实网络）

`PermissionGate(permission_mode="acceptEdits")` 下 Edit 必须：
- 不产生 `user.question`
- Edit 成功落盘（替换 PLACEHOLDER 为 token）

### REQ-0025-004 — Non-injected security: Read absolute path outside project is rejected and token not leaked（真实网络）

准备一个 project_dir 外的外部文件（含 token），引导模型对其绝对路径 Read：
- 必须 tool.result error
- 外部 token 不得出现在任何 tool.output / final_text
- 之后对 project 内文件 Read 仍可成功（证明 loop 不中断）

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` exit code=0
2) 新增用例覆盖 REQ-0025-001..004

