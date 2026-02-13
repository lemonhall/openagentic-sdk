# v20 Index

## Vision

继续提升真实网络 E2E 的“真度”和“对抗性”：
- 非注入工作流更长（多工具链、落盘为准）；
- 对抗路径系统化（工具输入错误不短路、绝对路径越界拒绝）。

## Milestones

- **M1: Real-network E2E (core non-injection + adversarial v20)**
  - Plan: `docs/plan/v20-real-network-e2e-core-noninjection-adversarial.md`
  - PRD: `docs/prd/PRD-0020-real-network-e2e-core-noninjection-adversarial-v20.md`
  - DoD（命令证据）：
    - `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v`
  - Status: done（2026-02-11）

## Traceability Matrix (Req → Plan → Tests → Evidence)

- REQ-0020-001 → `docs/plan/v20-real-network-e2e-core-noninjection-adversarial.md` → `e2e_tests/e2e_tools_glob_grep_edit_single_target_real_no_injection.py` → Evidence in plan
- REQ-0020-002 → `docs/plan/v20-real-network-e2e-core-noninjection-adversarial.md` → `e2e_tests/e2e_ask_user_write_read_pipeline_real_no_injection.py` → Evidence in plan
- REQ-0020-003 → `docs/plan/v20-real-network-e2e-core-noninjection-adversarial.md` → `e2e_tests/e2e_tool_loop_continues_after_input_error_real.py` → Evidence in plan
- REQ-0020-004 → `docs/plan/v20-real-network-e2e-core-noninjection-adversarial.md` → `e2e_tests/e2e_security_absolute_path_outside_project_rejected_real.py` → Evidence in plan

## ECN

- None

## Deltas (Vision vs Reality)

- 新增 2 条非注入链路（Glob/Grep→Edit 单目标、AskUserQuestion→Write→Read），断言以落盘为准并允许最多 3 次重试对冲模型波动。
- 新增 2 条确定性对抗路径（工具输入错误不短路、绝对路径越界拒绝），断言以 tool.result 机读字段为准。
