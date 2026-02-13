# PRD-0037 — Core Composed Flows (Resume + Compaction) v37（核心组合流程：恢复 + 压缩修剪 v37）

## Vision

在 hard-invariants 的基础上，继续堆“组合流程”的真网络 E2E 密度，优先覆盖最核心的跨 turn 行为：

- `Sessions+Resume × Permissions(prompt)`：deny → resume → allow（append-only + 行为一致）
- `Sessions+Resume × Hooks(post_tool_use block)`：失败事件落盘后 resume 仍可继续
- `Compaction(prune) × Resume × Tools`：prune 后仍可继续工具链，不因旧 tool result 被清理而破坏会话

## Non-Goals

- 不扩大到 Gateway/MCP。
- 不触碰 PTY/ConPTY。
- 不追求“模型自主选工具”的覆盖（本轮以 injected 硬断言为主）。

## Requirements

### REQ-0037-001 — Resume + prompt permission (deny then allow)

新增 injected 真网络 E2E：

- Run1（resume=session_id）：注入 `Write`，prompt 回答 `no` → `PermissionDenied`，无文件副作用
- Run2（同 resume=session_id）：注入 `Write`，prompt 回答 `yes` → 写入成功，文件含 token
- 断言 `events.jsonl` append-only（行数增加），且包含 `user.question` 与 deny/allow 两类结果

### REQ-0037-002 — Resume + post-tool-use block then unblock

新增 injected 真网络 E2E：

- Run1：`post_tool_use` block `Read` → tool.result error（RuntimeError），会话继续结束
- Run2（resume 同 session）：去掉 block，注入 `Read` → tool.result ok，内容含 token
- 断言 `events.jsonl` append-only 且两次 tool_use_id 均落盘

### REQ-0037-003 — Prune + resume still usable for tools

新增 injected 真网络 E2E：

- Run1：注入 `Read` 大文件，制造可 prune 的旧 tool result
- Run2/Run3：注入仅 final text，形成足够 user turns 触发 prune
- Run4（resume 同 session）：注入 `Read` 小文件 → 必须成功
- 断言 `events.jsonl` 含 `tool.output_compacted`，且 Run4 的 Read 仍能返回小文件 token

### REQ-0037-004 — Stable suite: core_matrix_v37

新增聚合套件：

- `e2e_tests/core_matrix_v37.py`

套件包含 `core_matrix_v36` + 本轮新增 3 条组合流程用例，作为稳定回归门。

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest -v e2e_tests.core_matrix_v37` exit code=0
2) `python scripts/model_driven_e2e.py --suite e2e_tests.core_matrix_v37 --runs 3 --min-pass-rate 1.0` exit code=0
3) 覆盖矩阵文档更新映射（新增用例被登记）

