# v19 Index

## Vision

进一步提高真实网络 E2E 的“真度”和“语义硬度”：
- 更长的非注入用户流程（Skill 驱动、多工具链、落盘为准）；
- 权限语义（acceptEdits/prompt）硬回归；
- 路径语义：相对路径以 cwd 为准，同时被 project_dir 约束；Windows 未知 POSIX 绝对路径拒绝。

## Milestones

- **M1: Real-network E2E (non-injection + permissions + path semantics v19)**
  - Plan: `docs/plan/v19-real-network-e2e-core-noninjection-permissions-path.md`
  - PRD: `docs/prd/PRD-0019-real-network-e2e-core-noninjection-permissions-path-v19.md`
  - DoD（命令证据）：
    - `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v`
  - Status: done（2026-02-11）

## Traceability Matrix (Req → Plan → Tests → Evidence)

- REQ-0019-001 → `docs/plan/v19-real-network-e2e-core-noninjection-permissions-path.md` → `e2e_tests/e2e_workflow_skill_write_glob_grep_edit_read_real_no_injection.py` → Evidence in plan
- REQ-0019-002 → `docs/plan/v19-real-network-e2e-core-noninjection-permissions-path.md` → `e2e_tests/e2e_permissions_acceptEdits_read_prompts_edit_auto_allows_real.py` → Evidence in plan
- REQ-0019-003 → `docs/plan/v19-real-network-e2e-core-noninjection-permissions-path.md` → `e2e_tests/e2e_permissions_prompt_three_calls_mixed_real.py` → Evidence in plan
- REQ-0019-004 → `docs/plan/v19-real-network-e2e-core-noninjection-permissions-path.md` → `e2e_tests/e2e_path_semantics_cwd_vs_project_dir_real.py` → Evidence in plan
- REQ-0019-005 → `docs/plan/v19-real-network-e2e-core-noninjection-permissions-path.md` → `e2e_tests/e2e_windows_posix_unknown_abs_path_rejected_real.py` → Evidence in plan

## ECN

- None

## Deltas (Vision vs Reality)

- `resolve_tool_path` 纠偏：相对路径以 `cwd` 为基准解析，但通过 `project_dir` 做安全根约束；新增 E2E 覆盖该语义。
- 为提升真实网络可回归性：在 `e2e_tests/_harness.py` 增加 provider request-level 外层重试（仅在未产出任何 stream event 时生效），并提高默认重试配置（可用 env 覆盖）。
