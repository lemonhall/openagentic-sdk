# Offline E2E Tests

这是一套**离线可重复**的端到端测试：不需要外网、不需要 `RIGHTCODE_API_KEY`，也不会发真实网络请求。

## 运行方式

PowerShell（仓库根目录）：

```powershell
python -m unittest discover -s e2e_tests_offline -p "e2e_*.py" -v
```

## 与 real-network E2E 的区别

- 离线 E2E（本目录）：使用内存 fake provider，覆盖核心链路（Core/Tool/Streaming/Resume）。
- 真实网络 E2E（`e2e_tests/`）：需要 `RIGHTCODE_API_KEY`，会请求真实 OpenAI-compatible API，可能产生费用：
  - `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v`

## 覆盖清单（离线）

- Core：`openagentic_sdk.run()` 返回 `final_text` + `session_id`
- Tool loop：`TodoWrite`（tool call → tool result → function_call_output → 继续）
- Streaming：`stream()` 的 text_delta 累积成最终文本
- Resume/threading：同 session 第二次调用传递 `previous_response_id`
- Skill：`Skill` tool 链路（加载 SKILL.md 并回传 output）
- SlashCommand：用户输入 `/name` 时直执行模板展开 + `@file` 注入
- SlashCommand(tool)：模型调用 `SlashCommand` tool → 返回 `parts`（含 file url 编码）+ 渲染内容
- PermissionGate：`permission_mode="prompt"` + `user_answerer`（包含 `user.question` 事件）
- AskUserQuestion：模型发起问题 → `user.question` → `user_answerer` 回答 → tool output 回传模型
- Tool error serialization：tool 失败时 `function_call_output` 中包含 `is_error/error_type/error_message`
- Compaction：legacy provider 下 overflow 自动 compaction pass + summary pivot
