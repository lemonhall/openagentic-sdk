# v1 Index — OpenCode Prompt Parts + Compaction Overflow

## Vision

见：`docs/prd/PRD-0001-opencode-parts-compaction-parity.md`

## Milestones

- M1: Prompt Parts（@file/@agent）对齐（REQ-0001-001/002/003）
  - DoD: WSL2 `python3 -m unittest -q` 通过；Windows 运行本里程碑相关测试通过；相关断言不再依赖“Called the Read tool”前缀
- M2: Compaction Overflow 对齐（REQ-0001-004/005）
  - DoD: overflow 判定单测覆盖 `>=` 与 reserved 推导；WSL2 `python3 -m unittest -q` 通过

## Plan Index

- `docs/plan/v1-opencode-parts-compaction.md`

## Traceability Matrix

| Req ID | Plan | Tests | Evidence |
|---|---|---|---|
| REQ-0001-001 | v1-opencode-parts-compaction.md | `tests/test_slash_command_templating.py`, `tests/test_slash_command_parts_parity.py`, `tests/test_slash_command_special_chars.py` | `wsl -e bash -lc "cd /mnt/e/development/openagentic-sdk && python3 -m unittest -q"` |
| REQ-0001-002 | v1-opencode-parts-compaction.md | `tests/test_slash_command_templating.py`, `tests/test_user_slash_command_execution.py` | `wsl -e bash -lc "cd /mnt/e/development/openagentic-sdk && python3 -m unittest -q"` |
| REQ-0001-003 | v1-opencode-parts-compaction.md | `tests/test_slash_command_parts_parity.py` | `wsl -e bash -lc "cd /mnt/e/development/openagentic-sdk && python3 -m unittest -q"` |
| REQ-0001-004 | v1-opencode-parts-compaction.md | `tests/test_compaction_overflow_parity.py` | `wsl -e bash -lc "cd /mnt/e/development/openagentic-sdk && python3 -m unittest -q"` |
| REQ-0001-005 | v1-opencode-parts-compaction.md | `tests/test_cli_compaction_limits_from_models_dev.py`（扩展） | `wsl -e bash -lc "cd /mnt/e/development/openagentic-sdk && python3 -m unittest -q"` |

## ECN Index

（v1 暂无）

## Deltas / Follow-ups

- provider 侧真正的 attachment（Responses `input_file`）语义对齐不在 v1 范围，后续单列 v2。
