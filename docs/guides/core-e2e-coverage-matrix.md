# Core E2E Coverage Matrix（核心真网络 E2E 覆盖矩阵）

本矩阵用于把“核心模块定义（Tool / Skill / Runtime Core / Human-in-the-loop / Sessions+Resume / Permissions / Hooks）”落实为**可执行、可扩展**的真网络 E2E 覆盖面清单：

- 目标：让核心 SDK 的关键行为都有 **tool.use/tool.result + 磁盘产物（sessions/events.jsonl 等）** 的硬证据。
- 原则：优先覆盖 **负路径/边界条件**（拒绝、错误、恢复、落盘一致性），再扩展长链路用户流程。
- 两车道（见 `AGENTS.md`）：`smoke_core`（硬不变量，全绿）+ `core_flows`（随机层，统计门禁）。

> 注：这里的“覆盖”指**有可回归的硬断言**，不是“prompt 看起来跑通了”。

---

## 1) Tools（工具语义）

| 能力点 | 现有真网络 E2E | 状态 | 备注 / 缺口 |
|---|---|---:|---|
| `Read` 基本读取 + 产物断言 | `e2e_read_roundtrip_real_no_injection.py` 等 | ✅ | 继续补：编码/大文件截断/路径边界 |
| `Write` 覆盖写入（overwrite=true） | 多个 write 流程用例 | ✅ | 继续补：二次写入、并发冲突（非目标则不做） |
| `Write` 覆盖保护（overwrite=false） | `e2e_write_overwrite_false_real_no_injection.py` | ✅ | 可补：错误信息稳定性（别泄露路径） |
| `Edit` 单点替换（count=1） | `e2e_tools_edit_roundtrip_real_no_injection.py`、`e2e_metamorphic_edit_variants_real_no_injection.py` | ✅ | 继续补：old 不匹配、count>1、空文件 |
| `NotebookEdit` 编辑回归 | `e2e_tools_notebook_edit_roundtrip_real.py` | ✅ | 可补：多 cell/非 json 输入错误 |
| `Glob` + `Grep` 组合 | `e2e_glob_read_write_summary_real_no_injection.py`、`e2e_tools_glob_grep_find_token_real.py` | ✅ | 可补：root 相对 cwd 的更多形态 |
| `TodoWrite` 落盘 | `e2e_tools_todowrite_persists_real.py`、`e2e_todowrite_two_items_real_no_injection.py` | ✅ | 可补：重复 id、非法 shape |
| `List`（opencode `list`）| `e2e_tools_list_tree_output_real_injected.py`、`e2e_security_list_abs_path_rejected_real_injected.py` | ✅ | 已覆盖树输出与 abs 越界拒绝 |
| `List`：limit/truncated | `e2e_tools_list_truncated_limit_real_injected.py` | ✅ | 覆盖默认 limit=100 的截断语义 |
| `List`：忽略 junk dirs | `e2e_tools_list_ignores_junk_dirs_real_injected.py` | ✅ | 覆盖 `.git`/`node_modules`/`__pycache__` 忽略 |
| `Edit`：old 不存在错误 | `e2e_tools_edit_old_not_found_errors_real_injected.py` | ✅ | 覆盖 error + 无副作用（文件不变） |
| `Write`：content 非 string | `e2e_tools_write_content_non_string_errors_real_injected.py` | ✅ | 覆盖 error + 无副作用 + 后续恢复 |
| `SlashCommand` 模板渲染 | 多个 slash 用例 | ✅ | 可补：unknown command / args 解析边界 |
| `Skill` 工具执行 | `e2e_skill_tool_real.py`、`e2e_skill_tool_real_no_injection.py` 等 | ✅ | 可补：skill 链接/失败回退 |
| `AskUserQuestion` 人类交互 | `e2e_ask_user_question_real.py`、`e2e_ask_user_write_read_pipeline_real_no_injection.py` | ✅ | 可补：ask_user + resume、ask_user 与 permissions 组合 |

---

## 2) Runtime Core（tool loop / 编排）

| 能力点 | 现有真网络 E2E | 状态 | 备注 / 缺口 |
|---|---|---:|---|
| tool error → 恢复继续 | `e2e_tool_loop_recover_read_missing_real_no_injection.py`（含 injected 版本） | ✅ | 可补：多 tool_calls 同一 turn 的顺序/稳定性 |
| `allowed_tools` gate（ToolNotAllowed） | `e2e_runtime_allowed_tools_gate_tool_not_allowed_real_injected.py` | ✅ | 覆盖 ToolNotAllowed + 无副作用 |
| 单次 model 输出多 tool_calls | `e2e_tools_glob_grep_find_token_real.py`（injected） | ✅ | 继续补：混合 Read/Write/最后文本的完整链路 |
| streaming delta 对调用方可见 | `e2e_query_emits_deltas.py` | ✅ | 需要持续确保“可见但不落盘” |
| delta 不落入 `events.jsonl` | `e2e_sessions_events_jsonl_excludes_deltas_real_no_injection.py` | ✅ | 可补：resume 后继续不落盘 |

---

## 3) Sessions + Resume（落盘与恢复）

| 能力点 | 现有真网络 E2E | 状态 | 备注 / 缺口 |
|---|---|---:|---|
| `events.jsonl` append-only（两次 run） | `e2e_sessions_resume_two_turns_append_real_no_injection.py` | ✅ | 可补：同 session 多 turn 多工具混合 |
| 权限 prompt 在 resume 下可继续 | `e2e_sessions_resume_permission_prompt_write_then_read_real_no_injection.py` | ✅ | 可补：callback 权限、deny/allow 混合 |
| resume × permissions(prompt) deny→allow | `e2e_sessions_resume_permission_prompt_deny_then_allow_write_real_injected.py` | ✅ | 覆盖 deny→resume→allow 的 append-only 与无副作用 |
| resume × hooks(post_tool_use block) | `e2e_sessions_resume_post_tool_use_block_then_unblock_read_real_injected.py` | ✅ | 覆盖失败落盘后 resume 仍可继续 |
| compaction/prune 与 resume 兼容 | compaction/prune 若干用例 | ✅/△ | 仍需补：prune 后恢复读写链路不破 |
| prune × resume × tools 可用性 | `e2e_compaction_prune_then_resume_read_still_works_real_injected.py` | ✅ | 覆盖 prune 后继续 Read 的硬证据 |
| **禁止落 streaming delta** | `e2e_sessions_events_jsonl_excludes_deltas_real_no_injection.py` | ✅ | 这是硬约束（防止膨胀到 GB 级） |

---

## 4) Permissions（权限门 / human-in-the-loop）

| 能力点 | 现有真网络 E2E | 状态 | 备注 / 缺口 |
|---|---|---:|---|
| `default`：安全工具不问、危险工具问 | `e2e_perm_default_prompt_write_real_no_injection.py`、`e2e_permissions_default_prompts_edit_real_no_injection.py` | ✅ | 可补：Read/Glob/Grep 不触发 question 的硬断言 |
| `prompt`：deny → allow | `e2e_perm_prompt_deny_then_allow_write_real_no_injection.py`（含 injected 版本） | ✅ | 已覆盖 |
| `acceptEdits`：Edit/Write/NotebookEdit 自动放行 | `e2e_perm_accept_edits_*` | ✅ | 可补：acceptEdits 对非 edit 工具回落 prompt |
| `callback`：外部审批逻辑 | `e2e_permissions_callback_deny_then_allow_write_real_injected.py` | ✅ | 覆盖 deterministic deny→allow |

---

## 5) Hooks（可插拔改写/拦截）

| 能力点 | 现有真网络 E2E | 状态 | 备注 / 缺口 |
|---|---|---:|---|
| before/after model call 改写/覆盖 | `e2e_hooks_before_model_call_rewrite_real.py`、`e2e_hooks_after_model_call_override_real.py` | ✅ | 已覆盖 |
| pre tool use 改写输入 | `e2e_hooks_pre_tool_use_rewrite_read_real_no_injection.py` | ✅ | 已覆盖 |
| post tool use 改写输出 | `e2e_hooks_post_tool_use_override_real.py` | ✅ | 可补：post tool use “block” 的错误语义 |
| post tool use：block | `e2e_hooks_post_tool_use_block_real_injected.py` | ✅ | 覆盖 block 语义（success→error） |
| hook blocks tool（阻断） | `e2e_runtime_hook_blocks_tool_real.py` | ✅ | 可补：block 后 resume 行为 |

---

## v35 计划（本矩阵驱动的下一批缺口）

优先补齐：

1) `List` 工具：树输出 + 路径边界（abs/../）  
2) Runtime Core：`allowed_tools` gate（ToolNotAllowed）  
3) Permissions：`callback` deterministic gate  
4) Hooks：post-tool-use block 的错误语义（硬断言）  

对应计划见：`docs/plan/v35-index.md` 与 `docs/plan/v35-core-e2e-coverage-matrix-and-expansion.md`。

## v36 计划（继续堆 hard invariants 密度）

本轮优先补齐：

1) `List`：limit/truncated（默认 100）  
2) `List`：忽略 junk dirs（`.git`/`node_modules`/`__pycache__`）  
3) `Edit`：old-not-found 错误与无副作用  
4) `Write`：content 类型校验与恢复  
5) Permissions：`default` safe tools 不 prompt；`acceptEdits` 对非 edit 工具 prompt+deny  

对应计划见：`docs/plan/v36-index.md` 与 `docs/plan/v36-core-hard-invariants-e2e-density.md`。
