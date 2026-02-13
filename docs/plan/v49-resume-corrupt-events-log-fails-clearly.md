# v49 Plan — Resume: Corrupt `events.jsonl` Must Fail Clearly（恢复：events.jsonl 损坏必须明确失败）

## Goal

实现并证明：resume 读取 `events.jsonl` 时，一旦发现坏行/截断/解码失败，SDK 立刻失败并给出清晰可定位错误。

## PRD Trace

- REQ-0049-001..003（见 PRD-0049）

## Scope

做：

- 新增 `CorruptSessionLogError`，并在读取/推断 seq 时发现坏行就抛出
- 新增真网络 no-injection E2E：人为追加坏行后 resume 必须失败
- 更新 `core_flows_sessions` suite
- 实跑 DoD 并写回 Evidence

不做：

- 不做自动修复（不改写 events.jsonl）
- 不动 PTY/ConPTY
- 不扩大到 Gateway/MCP

## Acceptance (DoD)

必须全部满足：

- `python -m unittest -v e2e_tests.core_flows_sessions` exit code=0
- `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_sessions --runs 3 --min-pass-rate 0.8 --rerun-failures 1` exit code=0

## Evidence（填写为可复现证据）

- Date: 2026-02-13
- Env: Windows + PowerShell, real-network provider via `e2e_tests/_harness.py`（dotenv supported）
- Commands + Results:
  - `python -m unittest -v e2e_tests.core_flows_sessions` → exit code=0
  - `python scripts/model_driven_e2e.py --suite e2e_tests.core_flows_sessions --runs 3 --min-pass-rate 0.8 --rerun-failures 1 --include-history`
    - Verdict: pass (Pass rate=1.000, Gate>=0.800)
    - Report:
      - `.openagentic_e2e_reports/20260213T012510Z-e2e_tests.core_flows_sessions-pid27296/run_report.md`
      - `.openagentic_e2e_reports/20260213T012510Z-e2e_tests.core_flows_sessions-pid27296/run_report.json`
- Reports:
  - `.openagentic_e2e_reports/20260213T012510Z-e2e_tests.core_flows_sessions-pid27296/`
