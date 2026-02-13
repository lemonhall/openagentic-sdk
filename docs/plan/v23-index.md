# v23 Index

## Vision

扩展 `openagentic_cli` 的子命令 E2E 覆盖：

- `oa run`（`--json` / `--no-stream`）作为脚本/自动化入口；
- `oa share/shared/unshare` 的落盘互操作；
- `oa auth` 的落盘与隔离（使用 fake key）。

## Milestones

- **M1: Real-network CLI subcommands E2E (v23)**
  - Plan: `docs/plan/v23-real-network-e2e-cli-subcommands.md`
  - PRD: `docs/prd/PRD-0023-real-network-e2e-cli-subcommands-v23.md`
  - DoD（命令证据）：
    - `python -m unittest discover -s e2e_cli_tests -p "e2e_*.py" -v`
  - Status: done（2026-02-11）

## Traceability Matrix (Req → Plan → Tests → Evidence)

- REQ-0023-001 → `docs/plan/v23-real-network-e2e-cli-subcommands.md` → `e2e_cli_tests/e2e_cli_run_json_real.py` → Evidence in plan
- REQ-0023-002 → `docs/plan/v23-real-network-e2e-cli-subcommands.md` → `e2e_cli_tests/e2e_cli_run_nostream_real.py` → Evidence in plan
- REQ-0023-003 → `docs/plan/v23-real-network-e2e-cli-subcommands.md` → `e2e_cli_tests/e2e_cli_share_roundtrip.py` → Evidence in plan
- REQ-0023-004 → `docs/plan/v23-real-network-e2e-cli-subcommands.md` → `e2e_cli_tests/e2e_cli_auth_roundtrip.py` → Evidence in plan

## ECN

- None

## Deltas (Vision vs Reality)

- 子命令（run/share/auth）已纳入真实网络 E2E，断言以 JSON/exit code/落盘为主，避免模型波动造成脆弱测试。
