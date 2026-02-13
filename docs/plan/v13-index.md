# v13 Index

## Vision

继续扩大真实网络 E2E 的核心覆盖面，夯实 `sessions` 落盘语义与“转录脱敏”安全边界。

## Milestones

- **M1: Real-network E2E (sessions transcript redaction)** — events include tool output, transcript excludes
  - Plan: `docs/plan/v13-real-network-e2e-sessions-transcript-redaction.md`
  - PRD: `docs/prd/PRD-0013-real-network-e2e-sessions-transcript-redaction.md`
  - DoD（命令证据）：
    - `python -m unittest discover -s e2e_tests -p "e2e_*.py" -v`
  - Status: done

## Traceability Matrix (Req → Plan → Tests → Evidence)

- REQ-0013-001 → `docs/plan/v13-real-network-e2e-sessions-transcript-redaction.md` → `e2e_tests/e2e_sessions_transcript_redaction_real.py` → Evidence in plan

## ECN

- None

## Deltas (Vision vs Reality)

- 用 hooks 注入 Read + 固定收尾文本，避免模型复述 token；验证以落盘 `events.jsonl`/`transcript.jsonl` 文本是否包含 token 为准。
