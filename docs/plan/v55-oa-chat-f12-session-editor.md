# v55 Plan — `oa chat` F12 Session Editor（会话内 TUI 文本编辑 + resume 语义重置）

## Goal

交付一个只聚焦“修正文案记忆”的最小可用会话编辑器：

- 在 `oa chat` 的 Prompt Toolkit prompt 中按 `F12` 打开编辑器；
- 仅编辑 `user.message` / `assistant.message`；
- 保存后原子化更新本地 session 文件；
- 下一轮对话强制按编辑后的历史继续，不再沿用旧 `previous_response_id` 链路；
- 用 Windows ConPTY E2E 把真按键 / 真 REPL / 真 session 更新链路锁死。

## PRD Trace

- REQ-0055-001
- REQ-0055-002
- REQ-0055-003
- REQ-0055-004
- REQ-0055-005
- REQ-0055-006
- REQ-0055-007

## Scope

做：

- 新增 session 编辑服务层：读取可编辑 message，应用文本修改，原子重写 `events.jsonl` / `transcript.jsonl`
- 在 `oa chat` Prompt Toolkit 路径中挂接 `F12`，打开最小 TUI（消息列表 + 文本编辑区 + 保存/取消）
- 保存后失效化旧 provider conversation linkage，确保下一 turn 使用本地重建历史
- 补齐单元/集成测试与 Windows ConPTY offline E2E

不做：

- 不编辑 `tool.use` / `tool.result` / `result`
- 不支持 legacy backend F12
- 不做多会话管理器、搜索替换、批量编辑、复杂 diff
- 不做真实网络 E2E

## Implementation Notes（设计约束）

- 只使用现有依赖：Prompt Toolkit 已在 `pyproject.toml` 中存在；v55 不新增第三方库。
- 编辑器数据源以 session event log 为准，不以屏幕缓存或 provider 返回文本为准。
- 可编辑项的稳定标识直接绑定 event `seq`；如需 UI 友好标签，可映射成 `user_<seq>` / `assistant_<seq>`。
- 保存策略采用“全量读取 → 内存替换目标 event 文本 → 原子写回”：
  - 目标 event 之外的 JSON 内容保持字节语义稳定（字段值不变，允许格式重写）；
  - `transcript.jsonl` 由改写后的 event 列表重新生成；
  - 写回必须通过 `.tmp` + `replace()` 完成。
- provider 链路重置策略在 v55 明确为：
  - 只要发生实际文本改动，就将该 session 内所有 `result.response_id` 置空；
  - 同时让“下一轮 resume 不再沿用 previous_response_id”成为测试断言；
  - 若需要额外稳固 Responses provider 的重建路径，可同步在最新 `result.provider_metadata` 中标记 `supports_previous_response_id=False`。
- 为了可测性，TUI 本身必须保持薄，编辑/保存/校验逻辑放进可单测的纯 Python helper 中。
- Windows E2E 使用本地 OpenAI-compatible stub provider + 项目级 `opencode.json`，避免真实外网与真密钥。

## Acceptance (DoD)

必须全部满足：

1) 单元/集成：
   - `python -m unittest -q tests.test_session_edit_store tests.test_session_edit_resume_reset tests.test_cli_session_editor_model`
2) Windows ConPTY offline E2E：
   - `python -m unittest discover -s e2e_cli_win_tests -p "e2e_win_f12_session_editor_*.py" -v`
3) 反作弊条款：
   - 不允许只把 `events.jsonl` 改了却仍沿用旧 `previous_response_id`
   - 不允许只做 HTTP / store 层测试而不做 F12 真按键 E2E
   - 不允许保存时重写整个 session 但把 `tool.use` / `tool.result` 等非目标 event 改坏

## Files（预期变更路径）

- `openagentic_cli/repl_chat.py`
- `openagentic_cli/session_editor.py`
- `openagentic_sdk/sessions/store.py`
- `openagentic_sdk/sessions/edit.py`
- `openagentic_sdk/sessions/errors.py`
- `tests/test_session_edit_store.py`
- `tests/test_session_edit_resume_reset.py`
- `tests/test_cli_session_editor_model.py`
- `e2e_cli_win_tests/e2e_win_f12_session_editor_save_offline.py`
- `e2e_cli_win_tests/e2e_win_f12_session_editor_busy_guard_offline.py`

## Test Contract（先写死，后实现）

### Contract A — 文件态编辑正确性

`tests.test_session_edit_store` 至少覆盖：

- 编辑 `user.message` 后：
  - `events.jsonl` 对应 `seq` 的 `text` 更新；
  - 该 event 的 `seq` / `ts` / 其它字段不变；
  - 非目标 event 内容不变；
  - `transcript.jsonl` 对应文本同步更新。
- 编辑 `assistant.message` 后同理。
- 对 `tool.result` / `result` / 不存在 `seq` 发起编辑必须失败。
- 无改动保存不得重写文件。
- 基线 fingerprint 漂移时保存失败且文件保持原状。

### Contract B — resume / previous_response_id 语义

`tests.test_session_edit_resume_reset` 至少覆盖：

- 构造一个已存在 `result.response_id` 的 session；
- 编辑其中一条历史 `user.message` 或 `assistant.message`；
- 下一次 `resume=session_id` 运行时：
  - provider 收到的第一次调用 `previous_response_id is None`；
  - provider 收到的历史里包含编辑后的文本；
  - 不再沿用旧 `response_id`。

### Contract C — 编辑器状态机与守卫

`tests.test_cli_session_editor_model` 至少覆盖：

- 无 session 时 F12 打不开编辑器；
- busy 状态下 F12 打不开编辑器；
- dirty state 下 `Ctrl+S` 才允许提交；
- `Esc` 取消不产生写入；
- 只读消息不能进入可编辑态。

### Contract D — Windows ConPTY 真按键 E2E

`e2e_win_f12_session_editor_save_offline.py` 至少覆盖：

1. 启动真 `oa chat`
2. 发送第一轮 prompt，生成 session
3. 按 `F12` 打开编辑器
4. 选中第一条 `user.message`，改成新文本，保存退出
5. 发送下一轮 prompt
6. 断言：
   - `events.jsonl` 已含新文本
   - stub provider 的下一轮请求历史中出现新文本
   - stub provider 记录到的 `previous_response_id` 为 `None`

`e2e_win_f12_session_editor_busy_guard_offline.py` 至少覆盖：

1. assistant 正在流式输出时按 `F12`
2. 编辑器不得打开
3. 当前输出链路正常完成并返回 prompt

## Steps（Strict）

1) Analysis / Design
   - 确认 session 文件结构、resume 链路、Prompt Toolkit keybinding 接入点
   - 先锁定“编辑后必须切断 provider linkage”的实现方式

2) TDD Red：session edit store
   - 新增 `tests/test_session_edit_store.py`
   - 先写失败断言：只改 message 文本、原子回写、transcript 同步、漂移保护
   - 运行：`python -m unittest tests.test_session_edit_store -v`

3) TDD Green：session edit helper / store
   - 实现编辑 helper 与原子回写
   - 跑到绿：`python -m unittest tests.test_session_edit_store -v`

4) TDD Red：resume reset contract
   - 新增 `tests/test_session_edit_resume_reset.py`
   - 先写失败断言：编辑后首次 resumed provider call 不得带旧 `previous_response_id`
   - 运行：`python -m unittest tests.test_session_edit_resume_reset -v`

5) TDD Green：provider linkage reset
   - 实现 edit-save 后的 response linkage invalidation
   - 跑到绿：`python -m unittest tests.test_session_edit_resume_reset -v`

6) TDD Red：editor state model
   - 新增 `tests/test_cli_session_editor_model.py`
   - 先写无 session / busy / cancel / dirty / read-only 守卫
   - 运行：`python -m unittest tests.test_cli_session_editor_model -v`

7) TDD Green：Prompt Toolkit editor integration
   - 在 `openagentic_cli/repl_chat.py` 接入 `F12`
   - 新增最小 TUI 模块并跑到绿
   - 运行：`python -m unittest -q tests.test_session_edit_store tests.test_session_edit_resume_reset tests.test_cli_session_editor_model`

8) E2E Red：Windows ConPTY offline stub
   - 准备本地 OpenAI-compatible stub provider
   - 新增 `e2e_cli_win_tests/e2e_win_f12_session_editor_save_offline.py`
   - 先让它在未实现/未接通链路时失败

9) E2E Green
   - 实现/修正 F12 真按键链路、保存链路、busy guard
   - 运行：
     - `python -m unittest discover -s e2e_cli_win_tests -p "e2e_win_f12_session_editor_*.py" -v`

10) Review / Evidence
   - 回填 `docs/plan/v55-index.md` 状态
   - 回填本计划 Evidence
   - 检查 Req → Plan → Tests 无断链

## Evidence（待实现后回填）

- Date: 2026-03-26
- Env: Windows 11 + PowerShell 7.x + ConPTY + local stub provider
- Command + Result:
  - `python -m unittest -q tests.test_session_edit_store tests.test_session_edit_resume_reset tests.test_cli_session_editor_model tests.test_cli_repl_multiline_paste tests.test_cli_repl_thinking_hint tests.test_resume_rebuild_messages` → OK（25 tests, skipped=2）
  - `python -m unittest discover -s e2e_cli_win_tests -p "e2e_win_f12_session_editor_*.py" -v` → OK（2 tests）
