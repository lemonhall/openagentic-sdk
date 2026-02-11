# v9 Index

## Vision

继续扩大真实网络 E2E 的核心覆盖面，优先夯实 tools + runtime_core 的用户流程。

## Milestones

- **M1: Real-network E2E (core tools workflows)** — Edit/NotebookEdit/TodoWrite/Glob+Grep
  - Plan: `docs/plan/v9-real-network-e2e-core-tools-workflows.md`
  - PRD: `docs/prd/PRD-0009-real-network-e2e-core-tools-workflows.md`
  - DoD（命令证据）：
    - `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v`
  - Status: done

## Traceability Matrix (Req → Plan → Tests → Evidence)

- REQ-0009-001 → `docs/plan/v9-real-network-e2e-core-tools-workflows.md` → `e2e_tests/e2e_tools_edit_roundtrip_real.py` → Evidence in plan
- REQ-0009-002 → `docs/plan/v9-real-network-e2e-core-tools-workflows.md` → `e2e_tests/e2e_tools_notebook_edit_roundtrip_real.py` → Evidence in plan
- REQ-0009-003 → `docs/plan/v9-real-network-e2e-core-tools-workflows.md` → `e2e_tests/e2e_tools_todowrite_persists_real.py` → Evidence in plan
- REQ-0009-004 → `docs/plan/v9-real-network-e2e-core-tools-workflows.md` → `e2e_tests/e2e_tools_glob_grep_find_token_real.py` → Evidence in plan

## ECN

- None

## Deltas (Vision vs Reality)

- 为降低真实网络 LLM 行为波动，`Edit/NotebookEdit/Glob+Grep` 用例改为通过 `HookEngine.after_model_call` 一次性注入 tool_calls；验证仍是“真实网络调用 + runtime_core tool loop + 磁盘产物/tool.result 硬断言”。
- `Glob/Grep` 的 `root` 相对路径解析修正为相对 `ToolContext.cwd`（避免 `root="."` 在测试/真实会话中指向进程 cwd 而非 agent cwd）。
