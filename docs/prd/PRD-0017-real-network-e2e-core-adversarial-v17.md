# PRD-0017 — Real-Network E2E (Core Adversarial + Non-Injection v17)（真实网络 E2E：核心对抗 + 非注入 v17）

## Vision

把“核心模块”的真实网络 E2E 强度从“能跑通”升级到“经得起折腾也不碎”：

- **非注入比例上升**：更多用例依赖模型按提示自主选择工具（不靠 after_model_call 注入 tool_calls）。
- **对抗/负路径**：permission deny/allow 混合场景、tool error 不短路、compaction 多次 prune 仍可继续对话/用工具。
- **用户流程化**：围绕 `Skill + Tool` 组合做真实“用户工作流”回归（落盘产物可验证）。

## Non-Goals

- 不测试 MCP / Gateway。
- 不追求制造真实 429/断网等不可控网络故障（会引入高波动与成本）；本版聚焦**可复现**的对抗路径。

## Requirements

### REQ-0017-001 — Non-injected Skill happy-path（真实网络）

新增 E2E：不使用 hook 注入，提示模型：
- 调用 `Skill(name=demo-skill)` 加载 skill；
- 最终回复包含 skill 内的 token；
并断言：
- 发生 `tool.use(name="Skill")`；
- `tool.result` 输出包含 token。

### REQ-0017-002 — Non-injected Skill-driven tool chain edits disk（真实网络）

新增 E2E：不使用 hook 注入，提示模型：
- 先调用 `Skill` 读取“操作指南”；
- 再调用 `Read` + `Edit` 修改 `./a.txt`；
并断言：
- 磁盘内容确实发生变化（token 落盘）；
- 发生 `tool.use(name="Edit")`。

### REQ-0017-003 — Permission prompt supports mixed deny/allow within same model output（真实网络）

新增 E2E：PermissionGate `prompt` + `user_answerer`（第一次 no，第二次 yes），同一轮 model output 内包含 2 个 tool_calls：
- 第 1 个 tool_call 被拒绝，产生 `user.question` + `tool.result(is_error=True, error_type=PermissionDenied)`；
- 第 2 个 tool_call 被允许并成功执行；
并断言两条路径都出现且 loop 继续。

### REQ-0017-004 — Tool error does not short-circuit subsequent tool_calls（真实网络）

新增 E2E：同一轮 model output 内包含 2 个 tool_calls：
- 第 1 个故意触发工具错误（例如 Read 缺失文件）；
- 第 2 个工具调用仍然成功执行；
并断言两条 `tool.result` 都存在（先 error 再 success）。

### REQ-0017-005 — Compaction multi-prune under load remains usable（真实网络）

新增 E2E：在 aggressive prune 配置下，制造多个“大 tool result”，并在多轮 resume 后触发 prune：
- 至少 2 个不同 tool_use_id 被写入 `tool.output_compacted`；
- 后续 rebuilt provider input 中包含 placeholder（`[Old tool result content cleared]`）；
- prune 后仍可继续运行 tool loop（至少一次成功 tool.result）。

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` exit code=0
2) 新增用例覆盖 REQ-0017-001..005

