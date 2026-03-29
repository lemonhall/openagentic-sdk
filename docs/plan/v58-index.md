# v58 Index

## Vision

v58 解决的是 v57 之后一个很自然的缺口：我们已经能在 Jaeger 里看见 host ↔ subagent trace 了，但还看不到对应会话正文。v58 要做的是把“trace 可见”推进到“点击可读”：

- trace 保持轻量，只存稳定引用，不存全文正文；
- 正文继续以 session / `events.jsonl` 为权威来源；
- Jaeger 前端通过仓库内跟踪的 UI 源码 patch 按需回捞 transcript；
- Jaeger 当前灰字难读的问题在 v58 一并修复；
- 用户入口仍然保持简单：
  - `oa chat --k3d-real`
  - `http://127.0.0.1:16686`

## Milestones

- **M1: Transcript Refs And Read APIs**
  - Plan: `docs/plan/v58-jaeger-transcript-drilldown.md`
  - PRD: `docs/prd/PRD-0058-jaeger-transcript-drilldown-v58.md`
  - Status: planned

- **M2: Jaeger Drilldown UI**
  - Plan: `docs/plan/v58-jaeger-transcript-drilldown.md`
  - PRD: `docs/prd/PRD-0058-jaeger-transcript-drilldown-v58.md`
  - Status: planned

## Plan Index

- `docs/plan/v58-jaeger-transcript-drilldown.md`

## Traceability Matrix

- REQ-0058-001 → `docs/plan/v58-jaeger-transcript-drilldown.md` → `tests.test_actor_tracing` → pending
- REQ-0058-002 → `docs/plan/v58-jaeger-transcript-drilldown.md` → `tests.test_cluster_chat_transcript_api` + `tests.test_session_transcript_view` → pending
- REQ-0058-003 → `docs/plan/v58-jaeger-transcript-drilldown.md` → `tests.test_remote_worker_transcript_api` → pending
- REQ-0058-004 → `docs/plan/v58-jaeger-transcript-drilldown.md` → hand verification in Jaeger UI → pending
- REQ-0058-005 → `docs/plan/v58-jaeger-transcript-drilldown.md` → UI behavior verification → pending
- REQ-0058-006 → `docs/plan/v58-jaeger-transcript-drilldown.md` → transcript panel hand verification → pending
- REQ-0058-007 → `docs/plan/v58-jaeger-transcript-drilldown.md` → API / UI error-path tests → pending
- REQ-0058-008 → `docs/plan/v58-jaeger-transcript-drilldown.md` → regression on local + remote chat/tracing → pending
- REQ-0058-009 → `docs/plan/v58-jaeger-transcript-drilldown.md` → `tests.test_v58_jaeger_ui_assets` + hand verification in Jaeger UI → pending
- REQ-0058-010 → `docs/plan/v58-jaeger-transcript-drilldown.md` → vendored source audit + build/deploy verification → pending

## ECN

- None
