# PRD-0055 — `oa chat` F12 Session Editor v55（交互式会话内 TUI 编辑器）

## Vision

把 `oa chat` 从“只能继续对话”提升到“能在当前会话里修正历史文本并继续对话”：

- 在 `oa chat` 的 prompt idle 状态下，按 `F12` 打开一个基于当前 session 的 TUI 编辑器；
- 编辑器从本地 session 文件读取当前可见会话内容，只允许修改 `user.message` / `assistant.message` 的文本；
- 保存后，不只是本地文件变了，而且**当前 `oa chat` 进程的下一轮对话也必须按编辑后的历史继续**，不得继续沿用旧的 provider 远端会话链路；
- 整个能力在测试上必须有硬合同：单元/集成测试锁定落盘与 resume 语义，Windows ConPTY E2E 锁定 F12 真按键 + 真 `oa chat` + 真 session 更新链路。

## Non-Goals

- v55 不支持编辑 `tool.use`、`tool.result`、`result`、`system.init`、`hook.event` 等非 message event。
- v55 不做通用 session IDE，不提供搜索替换、多点编辑、diff merge、批量重排。
- v55 不在 legacy 输入后端中实现 F12 TUI；该能力仅要求 Prompt Toolkit TTY 路径支持。
- v55 不做多进程并发合并；若编辑期间底层 session 日志漂移，只允许“失败并提示”，不允许静默覆盖。

## Requirements

### REQ-0055-001 — F12 在 Prompt Toolkit idle prompt 中打开 Session Editor

当 `oa chat` 运行在 Prompt Toolkit 输入后端，且 `stdin/stdout` 都是 TTY 时：

- 在 idle prompt 状态按下 `F12`，打开当前 session 的全屏 TUI 编辑器；
- 如果当前还没有 session（尚未产生 `system.init` / 没有 `session_id`），则不给出空编辑器，而是提示“当前无可编辑 session”，随后返回 prompt；
- 打开编辑器不得创建新的 user turn，不得向 `events.jsonl` 追加伪造的 `user.message`。

### REQ-0055-002 — 编辑器只展示并允许编辑当前 head 下可见的 user/assistant message

编辑器读取当前 session 本地文件，并基于当前 effective head 构建可见消息列表：

- 只展示当前 head 下可见的 `user.message` / `assistant.message`；
- 列表项必须带稳定标识，至少能映射回原始 event 的 `seq`；
- `tool.use` / `tool.result` / `result` 等非目标 event 可以只读显示摘要，或在 v55 中完全不显示，但**不得被误编辑**；
- 选择某条消息后，右侧编辑区展示该条文本，允许修改并保存。

### REQ-0055-003 — 保存时必须原子化改写 session 文件，且只改目标 message 文本

当用户保存编辑时：

- `events.jsonl` 必须落成新的文件态，并保留原始事件顺序；
- 仅允许修改目标 `user.message.text` / `assistant.message.text`；
- 被编辑 event 的 `seq`、`ts`、`parent_tool_use_id`、`agent_name` 等非文本字段必须保持不变；
- 非目标 event 的内容必须保持不变；
- `transcript.jsonl` 必须与新文本同步更新；
- `events.jsonl` / `transcript.jsonl` 的写入必须是原子替换，禁止留下半写入文件或 `.tmp` 残留。

### REQ-0055-004 — 保存后必须切断旧 provider 会话链路，下一轮强制按本地编辑后历史继续

只要本次保存实际修改了任意 message 文本：

- 当前 session 的远端会话链路必须被失效化，禁止下一轮继续使用旧的 `previous_response_id`；
- 下一轮 `oa chat` 发起 runtime 时，provider 看到的历史必须包含编辑后的文本；
- 对 Responses 风格 provider，必须有明确机制保证“编辑后下一轮不再沿用旧 `response_id` 链路”；
- 验收以测试证据为准：下一轮 provider 调用的 `previous_response_id` 必须为 `None`，且 rebuilt input/history 中必须出现编辑后的文本。

### REQ-0055-005 — 取消、无改动保存、并发漂移必须有明确行为

- 取消退出时，`events.jsonl` / `transcript.jsonl` 不得发生任何变化；
- 若用户打开编辑器但没有实际改动，保存后不得重写 session 文件，不得切断 provider 链路；
- 若编辑器打开期间 session 文件发生漂移（例如 `events.jsonl` 已被其他写入改变），保存必须失败并明确提示，且不得覆盖外部变更。

### REQ-0055-006 — Busy / unsupported 路径必须失败得明确且不伤数据

- assistant 正在 in-flight 输出时，按 `F12` 不得打开编辑器；可以提示“当前会话忙碌中”，也可以忽略该按键，但不得破坏现有输出链路与 session 文件；
- legacy 输入后端、非 TTY、或 Prompt Toolkit 不可用时，不要求支持该功能，但不得崩溃；
- 任何保存失败场景都不得破坏现有 session 文件。

### REQ-0055-007 — 测试合同必须覆盖文件态、resume 语义、真实按键 E2E

必须提供以下测试层级：

- 单元/集成：
  - session 文件改写只改 message 文本、不改其他字段；
  - `transcript.jsonl` 同步更新；
  - 编辑后 resume 链路不再取旧 `previous_response_id`，且 rebuilt history 含新文本；
  - 无改动保存 / 并发漂移 / 非法目标类型等负路径明确失败。
- Windows ConPTY E2E：
  - 真 `oa chat` + 真 `F12` 按键 + 真保存流程；
  - provider 走本地 stub，不依赖外网和真密钥；
  - E2E 断言必须同时覆盖：
    - `events.jsonl` 已改；
    - 下一轮对话确实按编辑后历史继续；
    - `previous_response_id` 未被继续沿用。

## Acceptance (DoD)

必须全部满足：

1) 单元/集成：
   - `python -m unittest -q tests.test_session_edit_store tests.test_session_edit_resume_reset tests.test_cli_session_editor_model`
2) Windows ConPTY E2E（本地 stub provider，无真实网络）：
   - `python -m unittest discover -s e2e_cli_win_tests -p "e2e_win_f12_session_editor_*.py" -v`
3) REQ-0055-001..007 均有追溯落地（Req → Plan → Tests/Code → Evidence）。
4) 新增测试不得依赖 `RIGHTCODE_API_KEY`、不得发真实外网请求。
