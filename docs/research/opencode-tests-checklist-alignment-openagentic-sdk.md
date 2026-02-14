# opencode-tests-checklist 对齐：openagentic-sdk 现状与缺口（核心模块）

对齐输入：

- 源头清单：`docs/research/opencode-tests-checklist.md`（来自 `E:\development\opencode` 的 tests 归纳）
- 本项目核心模块定义：根 `AGENTS.md`（Runtime Core / Tools / Skills&Commands / Hooks / Permissions(HITL) / Sessions&Resume）

对齐口径（“算覆盖”的证据）：

- 单元测试：`tests/`（`python -m unittest -q` 默认跑的套件）
- 离线 E2E：`e2e_tests_offline/`（确定性 scripted provider）
- 真网络 E2E：`e2e_tests/`（会发真实请求/可能产生费用，**不默认跑**）
- CLI 交互 E2E：`e2e_cli_tests/`、`e2e_cli_win_tests/`（PTY/ConPTY，**不默认跑**）

> 本文的“缺口”定义为：清单中 P0/P1 的能力点，在本仓库里 **没有任何可回归的自动化断言**（unit/offline-e2e/real-e2e 都算）。

---

## 结论摘要（只列 P0/P1）

已明确属于“设计不一致 / 不适用（N/A）”的条目（不纳入补测）：

- `external_directory` 询问/归一化（OpenCode）：本项目走更强硬策略 —— `openagentic_sdk/tools/path_utils.py` 直接拒绝 project_root 外路径（ValueError），不存在“询问一次并 canonical glob”的分支。
- `apply_patch` 工具（OpenCode）：本项目无同名工具（有 `Edit` / `NotebookEdit`）。
- WebFetch 图片/附件分流（OpenCode）：本项目当前 `WebFetch` 统一按文本返回（`text`），不做附件。
- PermissionNext / arity（OpenCode）：本项目权限门是 `PermissionGate` 模式机（default/prompt/acceptEdits/callback/can_use_tool），没有 PermissionNext 的 glob ruleset 解析与 merge/evaluate。
- Sessions 事件类型（OpenCode 的 `session.started/session.updated`）：本项目用 `system.init`/`user.message`/`tool.use`/`tool.result`/`result` 等 append-only 事件序列。

主要“可补齐测试”的缺口（P0/P1）集中在 **Tools 的边界/负路径/落盘证据**：

- `ReadTool`：✅ 已补单测（`tests/test_read_tool_edges.py`），覆盖 image mode / path gate / `/mnt/data` 映射 / `max_bytes` + `truncated`
- `GrepTool`：✅ 已补单测（`tests/test_grep_tool_edges.py`），覆盖 no-match / CRLF / context / case-insensitive / `max_matches` + root path gate
- `BashTool`：✅ 已补单测（`tests/test_bash_tool_edges.py`），覆盖 output_lines_truncated / `full_output_file_path` 落盘 / Windows `/mnt/...` 归一化
- `ListTool`：✅ 已补 unit 快速回归（`tests/test_list_tool_unit.py`），并保留既有多条 E2E 覆盖
- custom tools：✅ 已补单测（`tests/test_custom_tools_precedence_and_isolation.py`），覆盖多 roots 的发现顺序/覆盖优先级 + import 失败隔离

---

## 对齐矩阵（P0/P1 优先；按核心模块分组）

### 1) Runtime Core

| 源头清单能力点 | 本项目对应 | 覆盖状态 | 证据（示例） | 备注 |
|---|---|---:|---|---|
| tool loop 基本行为 / error 序列化 | runtime_core tool loop | ✅ | `tests/test_runtime_tool_loop.py`、`tests/test_runtime_tool_error_serialization.py`、`e2e_tests_offline/` | 口径以 `tool.use/tool.result` + `events.jsonl` 为主 |
| Compaction / prune 关键边界 | compaction | ✅ | `tests/test_compaction_*.py`、`e2e_tests_offline/` | 已有多轮 vN 计划累积 |

### 2) Tools

#### 2.1 Tool Registry（自定义工具加载）

| 源头清单能力点 | 本项目对应 | 覆盖状态 | 证据（示例） | 备注 |
|---|---|---:|---|---|
| 从 `.opencode/{tool,tools}` 加载 Python tools | `openagentic_sdk/custom_tools.py` | ✅ | `tests/test_custom_tools_loading.py`、`tests/test_custom_tools_precedence_and_isolation.py` | 覆盖 `.opencode/{tool,tools}`、project root、`${OPENCODE_CONFIG_DIR}` roots |
| 自定义工具导入失败不应导致 CLI 崩溃 | `openagentic_sdk/custom_tools.py` + CLI 兜底 | ✅ | `tests/test_custom_tools_precedence_and_isolation.py` | import 失败按文件隔离，坏工具不会阻断其它工具加载 |
| 发现顺序/覆盖优先级稳定（project pack > project root > global） | `discover_custom_tool_files()` | ✅ | `tests/test_custom_tools_precedence_and_isolation.py` | precedence：global < project < .opencode；tool < tools；同名 tool 以“后注册覆盖” |

#### 2.2 Read Tool

| 源头清单能力点 | 本项目对应 | 覆盖状态 | 证据（示例） | 备注 |
|---|---|---:|---|---|
| 读取项目内文件（happy path） | `ReadTool` | ✅ | `tests/test_tools_read_glob_grep.py` |  |
| offset/limit（含 offset=0 兼容） | `ReadTool` | ✅ | `tests/test_tool_read_offset_zero.py`、`tests/test_tools_cas_io_compat.py` |  |
| project_root 外路径/`../` 穿越拒绝 | `resolve_tool_path()` | ✅ | `tests/test_read_tool_edges.py`、`e2e_tests_offline/e2e_security_abs_path_outside_rejected.py` |  |
| 图片读取（返回 base64 + mime） | `ReadTool` image mode | ✅ | `tests/test_read_tool_edges.py` | 覆盖 `.png`（其余图片后缀同分支） |
| `.fbs` 等非图片后缀按文本读取 | `ReadTool` | ✅ | `tests/test_read_tool_edges.py` | 防止后缀误判回归 |
| `max_bytes` 截断行为可回归 | `ReadTool.max_bytes` | ✅ | `tests/test_read_tool_edges.py` | 按 bytes 截断，并返回 `truncated` 标记 |
| offset 越界报错 |（N/A）| N/A |  | 当前实现 offset 超出返回空片段（不抛错）；与源头不同 |

#### 2.3 Grep Tool

| 源头清单能力点 | 本项目对应 | 覆盖状态 | 证据（示例） | 备注 |
|---|---|---:|---|---|
| 基础搜索（happy path） | `GrepTool` | ✅ | `tests/test_tools_read_glob_grep.py` |  |
| `mode=files_with_matches` | `GrepTool` | ✅ | `tests/test_tools_cas_io_compat.py` |  |
| 无匹配不报错、输出明确 | `GrepTool` | ✅ | `tests/test_grep_tool_edges.py` |  |
| CRLF/Mixed 行尾（splitlines） | `GrepTool` | ✅ | `tests/test_grep_tool_edges.py` |  |
| before/after context | `GrepTool` | ✅ | `tests/test_grep_tool_edges.py` |  |
| `case_sensitive=false` | `GrepTool` | ✅ | `tests/test_grep_tool_edges.py` |  |
| `max_matches` 截断 | `GrepTool.max_matches` | ✅ | `tests/test_grep_tool_edges.py` |  |
| hidden 参数 |（N/A）| N/A |  | 本项目 Grep 不走 ripgrep，也无 hidden 开关 |

#### 2.4 Bash Tool

| 源头清单能力点 | 本项目对应 | 覆盖状态 | 证据（示例） | 备注 |
|---|---|---:|---|---|
| 基础命令执行 + exit_code/stdout | `BashTool` | ✅ | `tests/test_tools_write_edit_bash_web.py` |  |
| workdir override | `BashTool` | ✅ | `tests/test_tools_cas_io_compat.py` |  |
| 无 bash/sh 时明确失败 | `BashTool._shell_argv` | ✅ | `tests/test_tools_write_edit_bash_web.py` |  |
| stdout_truncated flag | `BashTool.max_output_bytes` | ✅ | `tests/test_bash_truncation_flags.py` |  |
| output_lines_truncated | `BashTool.max_output_lines` | ✅ | `tests/test_bash_tool_edges.py` |  |
| 截断时写入完整输出到 `full_output_file_path` | `BashTool` | ✅ | `tests/test_bash_tool_edges.py` | 校验落盘路径与“完整输出包含被截断行” |
| Windows POSIX path 归一化（/mnt/c/... -> C:\...） | `_normalize_posix_paths_to_windows` | ✅ | `tests/test_bash_tool_edges.py` | 校验 stdout/stderr/output 三处一致 |

#### 2.5 List Tool（OpenCode `list`）

| 源头清单能力点 | 本项目对应 | 覆盖状态 | 证据（示例） | 备注 |
|---|---|---:|---|---|
| 树输出/limit/truncated/junk ignore/path reject | `ListTool` | ✅ | `tests/test_list_tool_unit.py`、`docs/guides/core-e2e-coverage-matrix.md` | unit + E2E 双层门禁 |

### 3) Skills / Commands

| 源头清单能力点 | 本项目对应 | 覆盖状态 | 证据（示例） | 备注 |
|---|---|---:|---|---|
| SkillTool 加载/缺参错误 | `SkillTool` | ✅ | `tests/test_skill_tool.py` | 可补：not found 报错信息稳定性（P1） |
| Skill 发现（多目录、缺 frontmatter 跳过、排序去重） | skills index/parse | ✅ | `tests/test_skill_index.py`、`tests/test_skill_parser.py`、`tests/test_skill_matrix.py` |  |
| SlashCommand 行为/parts 对齐 | slash command | ✅ | `tests/test_slash_command_*.py` |  |

### 4) Hooks

| 源头清单能力点 | 本项目对应 | 覆盖状态 | 证据（示例） | 备注 |
|---|---|---:|---|---|
| hook matcher/rewrite/user_prompt_submit 等 | hooks | ✅ | `tests/test_hooks_*.py` |  |

### 5) Permissions & HITL

| 源头清单能力点 | 本项目对应 | 覆盖状态 | 证据（示例） | 备注 |
|---|---|---:|---|---|
| default/prompt/acceptEdits/callback/can_use_tool | `PermissionGate` | ✅ | `tests/test_permissions_*.py`、`e2e_tests_offline/` | 权限门语义与 OpenCode PermissionNext 不同，已在多轮 vN 覆盖 |
| AskUserQuestion 的 runtime 交互 | AskUserQuestionTool + runtime | ✅ | `tests/test_tool_ask_user_question.py` |  |

### 6) Sessions / Resume

| 源头清单能力点 | 本项目对应 | 覆盖状态 | 证据（示例） | 备注 |
|---|---|---:|---|---|
| events.jsonl roundtrip / seq/ts / backward compat | sessions | ✅ | `tests/test_events_roundtrip.py`、`tests/test_event_seq_ts.py`、`tests/test_event_backward_compat.py` |  |
| `assistant.delta` 不落盘 | sessions | ✅ | `tests/test_events_jsonl_excludes_deltas.py`、`e2e_tests_offline/e2e_sessions_events_jsonl_excludes_assistant_delta.py` |  |
| resume：events.jsonl 损坏必须明确失败 | resume | ✅ | `docs/plan/v49-index.md` + 对应测试（见追溯矩阵） |  |
| Retry（退避/Retry-After/错误分类） | provider retry | ✅/△ | `tests/test_openai_compatible_retry.py` | 仍可补：更多 header 形态/32-bit cap（P1） |

---

## 建议进入 v54 的“补测清单”（按 P0 → P1）

P0（建议必须补）：

1) `ReadTool`：图片模式 / path gate / POSIX-like 映射 / `max_bytes` 截断（单测）
2) `GrepTool`：no-match / CRLF / context / case-insensitive / `max_matches` 截断（单测）
3) `BashTool`：output_lines_truncated / truncation 落盘 full_output_file_path / Windows POSIX path normalize（单测）
4) custom tools：先定“发现顺序/覆盖优先级”spec，然后补单测锁定（`discover_custom_tool_files` + `build_options` 不中断）

P1（建议补）：

- `ListTool`：加 2–3 条单元测试（树输出/忽略 junk/truncated），与现有 E2E 形成“快慢双层门禁”
- `SkillTool`：not found 错误信息稳定性（包含 available skills 列表）
