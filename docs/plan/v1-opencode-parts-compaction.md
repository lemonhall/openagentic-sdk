# v1 Plan — OpenCode Prompt Parts（@file/@agent）与 Compaction Overflow 对齐

## Goal

交付 PRD-0001 的 v1 需求：SlashCommand 的 prompt parts 语义对齐 + compaction overflow 判定对齐，并有可重复验证的测试证据。

## PRD Trace

- REQ-0001-001
- REQ-0001-002
- REQ-0001-003
- REQ-0001-004
- REQ-0001-005

## Scope

做：
- 调整 SlashCommand 渲染：file URL 编码、parts 顺序与去重、内容注入无“工具调用转录”
- 调整 compaction overflow：reserved/input_limit/>= 边界
- 更新/新增 `unittest` 用例形成证据链

不做：
- Responses 真正 attachments 上传/引用协议对齐
- JS/TS plugins、MCP OAuth、Server API 面

## Acceptance (DoD)

必须全部满足：

1) WSL2 下 `python3 -m unittest -q` 退出码为 0
2) Windows 下相关回归（本计划范围内）通过：
   - `python -m unittest -q tests.test_slash_command_templating tests.test_user_slash_command_execution tests.test_slash_command_parts_parity tests.test_slash_command_special_chars tests.test_compaction_overflow_parity`
2) SlashCommand 渲染结果中包含引用文件内容，但不包含 `Called the Read tool` / `Called the list tool` 前缀
3) `@file#name.txt` 产生的 `file` part URL 含 `%23`
4) Subtask 命令不产生 `file` parts 且不注入文件内容
5) overflow 判定在 `count == usable` 时为 True（覆盖 `>=` 边界）

## Files

预计修改：
- `openagentic_sdk/runtime.py`
- `openagentic_sdk/compaction.py`
- `openagentic_sdk/options.py`
- `openagentic_cli/config.py`
- `tests/test_slash_command_templating.py`
- `tests/test_user_slash_command_execution.py`
- `tests/test_slash_command_parts_parity.py`

预计新增：
- `tests/test_slash_command_special_chars.py`
- `tests/test_compaction_overflow_parity.py`

## Steps（Strict）

1) TDD Red：新增 special chars / overflow 边界测试，运行到红（预期失败：URL 未编码、overflow 用 `>` 而非 `>=`）
2) TDD Green：实现：
   - parts URL 用 `Path.as_uri()`
   - 内容注入改为“内容本身”，去掉“Called the ... tool”文本
   - compaction overflow 计算补齐 reserved/input_limit/>=
3) Refactor：收敛实现（不改变行为），保持测试全绿
4) Verify：运行 `python -m unittest -q`

## Risks

- Windows `Path.as_uri()` 输出格式与历史手拼 `file://` 不同，需同步更新测试断言为更宽松（只断言 `file:` 前缀 + `%23` 等关键点）。
