# PRD-0036 — Core Hard-Invariants E2E Density v36（核心硬不变量 E2E 密度提升 v36）

## Vision

沿用“覆盖矩阵驱动”，继续把核心模块的**硬语义**用真网络 E2E 堆密度，优先补齐：

- Tools 的输入校验/边界（特别是 `List`/`Edit`/`Write`）
- Permissions 的关键分支（`default` safe tools 不应 prompt；`acceptEdits` 对非 edit 工具必须 prompt）

并把这一批用例收敛到一个稳定聚合套件（必绿回归门）。

## Non-Goals

- 不扩大到 Gateway/MCP。
- 不触碰 PTY/ConPTY。
- 不追求“模型自己选工具”的覆盖（随机层继续在 `core_flows` 里做统计门禁；本 PRD 主要是 hard invariants）。

## Requirements

### REQ-0036-001 — List: truncated/limit behavior

新增真网络 E2E（injected），验证 `List` 在超过默认上限时：

- `truncated=True`
- `count==limit`（默认 100）
- 输出不包含超出上限的尾部文件名（防止“假 truncated”）

### REQ-0036-002 — List: ignore junk dirs

新增真网络 E2E（injected），验证 `List` 会忽略常见垃圾目录（如 `.git/`、`node_modules/`、`__pycache__/`），输出中不应出现这些目录/文件名。

### REQ-0036-003 — Edit: old-not-found errors without side effects

新增真网络 E2E（injected），验证 `Edit` 当 `old` 不在文件里时：

- 返回 error（`ValueError`）
- 文件内容保持不变（Read 的 content 仍为原内容）

### REQ-0036-004 — Write: content type validation

新增真网络 E2E（injected），验证 `Write` 当 `content` 不是 string 时：

- 返回 error（`ValueError`）
- 不创建目标文件（无副作用）
- 随后一次合法 Write 能成功落盘

### REQ-0036-005 — Permissions default: safe tools must not prompt

新增真网络 E2E（injected），在 `permission_mode="default"` 下：

- 对 `Read/Glob/Grep/Skill/SlashCommand/AskUserQuestion` 等 safe tools 不应产生 `user.question`

### REQ-0036-006 — Permissions acceptEdits: non-edit tool prompts

新增真网络 E2E（injected），在 `permission_mode="acceptEdits"` 下：

- 对非 edit 工具（例如 `WebFetch`）必须进入 prompt 流程（产生 `user.question`）
- 当回答 `no` 时必须返回 `PermissionDenied`（且不执行实际 fetch）

### REQ-0036-007 — Stable suite: core_matrix_v36

新增聚合套件：

- `e2e_tests/core_matrix_v36.py`

套件应包含 v35 的 hard-invariants + 本 PRD 新增用例，作为稳定回归门。

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest -v e2e_tests.core_matrix_v36` exit code=0
2) `python scripts/model_driven_e2e.py --suite e2e_tests.core_matrix_v36 --runs 3 --min-pass-rate 1.0` exit code=0
3) 覆盖矩阵文档更新映射（新增用例被登记）

