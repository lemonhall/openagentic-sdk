# v18 Index

## Vision

提升真实网络 E2E 的“真度”与“安全性”：
- 更多非注入用户流程（模型自主选工具，落盘为准）；
- 文件工具路径边界（防 `../` 路径逃逸、兼容 Windows 下 POSIX path 输出）；
- smoke/full 分层跑法（full 仍是 DoD）。

## Milestones

- **M1: Real-network E2E (core non-injection + security boundaries v18)** — workflows + path security + win compat
  - Plan: `docs/plan/v18-real-network-e2e-core-noninjection-security.md`
  - PRD: `docs/prd/PRD-0018-real-network-e2e-core-noninjection-security-v18.md`
  - DoD（命令证据）：
    - `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v`
  - Status: done（2026-02-11）

## Smoke Set（非 DoD）

- 建议 smoke（10 个，快速回归核心）：
  - `python -m unittest -v e2e_tests.e2e_tools_edit_roundtrip_real_no_injection`
  - `python -m unittest -v e2e_tests.e2e_skill_toolchain_edit_real_no_injection`
  - `python -m unittest -v e2e_tests.e2e_tools_write_roundtrip_real_no_injection`
  - `python -m unittest -v e2e_tests.e2e_tools_glob_grep_edit_roundtrip_real_no_injection`
  - `python -m unittest -v e2e_tests.e2e_permissions_default_prompts_edit_real_no_injection`
  - `python -m unittest -v e2e_tests.e2e_permissions_prompt_deny_then_allow_real`
  - `python -m unittest -v e2e_tests.e2e_tool_loop_continues_after_error_real`
  - `python -m unittest -v e2e_tests.e2e_compaction_prune_tool_outputs_real`
  - `python -m unittest -v e2e_tests.e2e_resume_after_fallback_no_threading_real`
  - `python -m unittest -v e2e_tests.e2e_hooks_lifecycle_observability_real`

## Traceability Matrix (Req → Plan → Tests → Evidence)

- REQ-0018-001 → `docs/plan/v18-real-network-e2e-core-noninjection-security.md` → `e2e_tests/e2e_tools_write_roundtrip_real_no_injection.py` → Evidence in plan
- REQ-0018-002 → `docs/plan/v18-real-network-e2e-core-noninjection-security.md` → `e2e_tests/e2e_tools_glob_grep_edit_roundtrip_real_no_injection.py` → Evidence in plan
- REQ-0018-003 → `docs/plan/v18-real-network-e2e-core-noninjection-security.md` → `e2e_tests/e2e_permissions_default_prompts_edit_real_no_injection.py` → Evidence in plan
- REQ-0018-004 → `docs/plan/v18-real-network-e2e-core-noninjection-security.md` → `e2e_tests/e2e_session_resume_read_after_write_real_no_injection.py` → Evidence in plan
- REQ-0018-005 → `docs/plan/v18-real-network-e2e-core-noninjection-security.md` → `e2e_tests/e2e_security_path_traversal_read_blocked_real.py` → Evidence in plan
- REQ-0018-006 → `docs/plan/v18-real-network-e2e-core-noninjection-security.md` → `e2e_tests/e2e_security_path_traversal_write_blocked_real.py` → Evidence in plan
- REQ-0018-007 → `docs/plan/v18-real-network-e2e-core-noninjection-security.md` → `e2e_tests/e2e_windows_posix_filePath_read_maps_to_cwd_real.py` → Evidence in plan

## ECN

- None

## Deltas (Vision vs Reality)

- 文件工具路径解析收敛为统一实现并加固边界：`openagentic_sdk/tools/path_utils.py` 现在同时处理空字符串字段、Windows POSIX path（白名单映射）、并阻止绝对/相对路径逃逸 project root（含 symlink resolve）。
- 对“非注入”用例引入最多 3 次重试（断言仍以落盘为准），在不牺牲“真 e2e”前提下降低波动。
