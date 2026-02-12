# PRD-0022 — Real-Network E2E (Core Non-Injection Ratio v22)（真实网络 E2E：核心非注入占比 v22）

## Vision

把核心模块的真实网络 E2E 从“多数依赖注入控形态”推进到“更多真实用户流程可回归”：

- **显著提高非注入用例占比**：非注入（`*_no_injection.py`）用例占 `e2e_tests/` 总用例数 **≥ 30%**；
- **仍然聚焦核心中的核心**：`runtime_core/tools/skills/hooks/permissions/sessions`；
- **断言口径更硬**：尽量以“磁盘落盘产物 / events.jsonl 事件”作为硬证据，而不是仅靠 final text。

## Non-Goals

- 不测试 MCP / Gateway。
- 不追求不可控网络故障（断网/随机 429）复现。

## Requirements

### REQ-0022-001 — Raise non-injection ratio to ≥ 30% (real-network)

新增一批 `e2e_tests/e2e_*_real_no_injection.py` 用例，使 “`no_injection` 用例数 / 总用例数” ≥ 30%（以 unittest 统计为准）。

### REQ-0022-002 — Non-injected tool loop recovers after Read missing file (real-network)

非注入：Read 不存在文件（tool.result error）后仍能继续 Write→Read 完整链路，且落盘正确。

### REQ-0022-003 — Non-injected tool loop recovers after Edit old-not-found (real-network)

非注入：Edit 因 old 不存在报错后，仍能继续第二次 Edit 成功并落盘正确。

### REQ-0022-004 — Permission default prompts for Write and allows (real-network, non-injection)

非注入：`PermissionGate(permission_mode="default", interactive=False, user_answerer=...)` 对 Write 产生 user.question，并在答 “yes” 后允许写入落盘。

### REQ-0022-005 — Permission prompt denies then allows Write with retry (real-network, non-injection)

非注入：prompt 模式下首次拒绝 Write（PermissionDenied），随后允许第二次 Write 并完成落盘。

### REQ-0022-006 — Sessions: same resume id across two runs appends events (real-network, non-injection)

非注入：同一 `resume` session id 连续两次 `run()`，events.jsonl 追加增长（seq/事件数增长可验证）。

### REQ-0022-007 — Sessions: events.jsonl seq is monotonic increasing (real-network, non-injection)

非注入：解析 events.jsonl，断言 `seq` 单调递增且无重复。

### REQ-0022-008 — Hooks: PreToolUse rewrites Read target (real-network, non-injection)

非注入：模型调用 Read(`./a.txt`) 时，PreToolUse hook 改写为读取 `./b.txt`，最终回答应来自 b.txt 的 token，并且 hook.event 可观察。

### REQ-0022-009 — Tools: Write overwrite=false errors and does not modify file (real-network, non-injection)

非注入：Write 尝试覆盖已有文件且 overwrite=false → tool.result error；原文件内容保持不变。

### REQ-0022-010 — Tools: Glob→Read→Write summary persists correct basenames (real-network, non-injection)

非注入：Glob 枚举 `./d/*.txt`，Read 每个文件，然后 Write `summary.txt` 写入 basenames（按字典序），最终落盘可验证。

### REQ-0022-011 — Tools: Grep→Edit affects only matched file (real-network, non-injection)

非注入：仅用 Grep 定位包含 `PLACEHOLDER` 的文件，Edit 只修改该文件；其他文件保持不变。

### REQ-0022-012 — Sessions: events.jsonl excludes assistant.delta even when streaming (real-network, non-injection)

非注入：开启 `include_partial_messages` 的 streaming 下，仍要保证 `events.jsonl` **不落** `assistant.delta`，且最终文本被持久化（用于 resume）。

### REQ-0022-013 — Tools: TodoWrite persists multiple todos.json entries (real-network, non-injection)

非注入：TodoWrite 写入 2 条 todo，落盘 `todos.json` 可验证。

### REQ-0022-014 — Permissions callback denies outside-project Write but allows in-project (real-network, non-injection)

非注入：callback 权限门拒绝 `../escape.txt`，允许 `./ok.txt` 并落盘；逃逸文件必须不存在。

## Acceptance (DoD)

必须全部满足：

1) `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v` exit code=0
2) 非注入用例占比 ≥ 30%（按 `unittest` 统计）
3) 新增用例覆盖 REQ-0022-001..014
