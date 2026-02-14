# v54 Index

## Vision

把 `opencode` 源头 tests 清单（P0/P1）对齐到本仓库核心模块：能测的补测、不可测/不适用的明确 N/A，形成“清单 → 计划 → 测试 → 证据”的闭环。

## Milestones

- **M1: Opencode tests checklist parity (P0/P1)** — 补齐 Tools 边界单测 + custom tools precedence 规格化
  - Alignment: `docs/research/opencode-tests-checklist-alignment-openagentic-sdk.md`
  - Plan: `docs/plan/v54-opencode-tests-checklist-parity.md`
  - PRD: `docs/prd/PRD-0054-opencode-tests-checklist-parity-v54.md`
  - DoD（命令证据）：
    - `python -m unittest -q`
  - Status: done (2026-02-14)

## Traceability Matrix (Req → Plan → Tests → Evidence)

- REQ-0054-001 → `docs/plan/v54-opencode-tests-checklist-parity.md` → `docs/research/opencode-tests-checklist-alignment-openagentic-sdk.md` → Evidence in plan
- REQ-0054-002 → `docs/plan/v54-opencode-tests-checklist-parity.md` → `tests/`（ReadTool edges）→ Evidence in plan
- REQ-0054-003 → `docs/plan/v54-opencode-tests-checklist-parity.md` → `tests/`（GrepTool edges）→ Evidence in plan
- REQ-0054-004 → `docs/plan/v54-opencode-tests-checklist-parity.md` → `tests/`（BashTool truncation +落盘）→ Evidence in plan
- REQ-0054-005 → `docs/plan/v54-opencode-tests-checklist-parity.md` → `tests/`（custom tools precedence + import isolation）→ Evidence in plan
- REQ-0054-006 → `docs/plan/v54-opencode-tests-checklist-parity.md` → `tests/`（ListTool unit）→ Evidence in plan

## ECN

- None

## Deltas (Vision vs Reality)

- 本轮补齐：`Read`/`Grep`/`Bash` 工具的 P0/P1 边界单测（见新增 `tests/test_*_tool_edges.py`）
- custom tools：定义并锁定 precedence（global < project < .opencode；tool < tools），并实现 import 失败按文件隔离
- 行为变更（向后兼容）：`ReadTool` 增加 `truncated` 字段；`GrepTool` 的 `root` 走 `resolve_tool_path()`（project_root 外拒绝）
