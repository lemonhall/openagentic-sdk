# v17 Index

## Vision

继续扩大真实网络 E2E 的核心覆盖面，但这一版强调“更真”的 e2e：
- 提升 **非注入**（模型自主选择工具）用例占比；
- 增强 **对抗性/负路径**（permission deny/allow、tool error 不短路、compaction 多次 prune 仍可用）；
- 以“用户流程”方式覆盖 `Skill + Tools + 人类交互/权限` 的关键链路。

## Milestones

- **M1: Real-network E2E (core adversarial + non-injection v17)** — skill/workflow + adversarial + multi-prune
  - Plan: `docs/plan/v17-real-network-e2e-core-adversarial.md`
  - PRD: `docs/prd/PRD-0017-real-network-e2e-core-adversarial-v17.md`
  - DoD（命令证据）：
    - `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v`
  - Status: done（2026-02-11）

## Traceability Matrix (Req → Plan → Tests → Evidence)

- REQ-0017-001 → `docs/plan/v17-real-network-e2e-core-adversarial.md` → `e2e_tests/e2e_skill_tool_real_no_injection.py` → Evidence in plan
- REQ-0017-002 → `docs/plan/v17-real-network-e2e-core-adversarial.md` → `e2e_tests/e2e_skill_toolchain_edit_real_no_injection.py` → Evidence in plan
- REQ-0017-003 → `docs/plan/v17-real-network-e2e-core-adversarial.md` → `e2e_tests/e2e_permissions_prompt_deny_then_allow_real.py` → Evidence in plan
- REQ-0017-004 → `docs/plan/v17-real-network-e2e-core-adversarial.md` → `e2e_tests/e2e_tool_loop_continues_after_error_real.py` → Evidence in plan
- REQ-0017-005 → `docs/plan/v17-real-network-e2e-core-adversarial.md` → `e2e_tests/e2e_compaction_multi_prune_real.py` → Evidence in plan

## ECN

- None

## Deltas (Vision vs Reality)

- 为降低 Windows 下的跨平台波动：将 `Read/Edit/Write` 的 path 解析收敛为统一实现（`openagentic_sdk/tools/path_utils.py`），支持空字符串字段、POSIX `/mnt/...` 白名单映射，并阻止 `../` 等路径逃逸到 project root 外。
- `e2e_streaming_tool_loop_read_real` 引入最多 3 次重试，以对冲真实网络 + streaming 指令的偶发偏离（断言仍基于工具块与 token）。
