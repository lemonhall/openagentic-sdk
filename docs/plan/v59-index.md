# v59 Index

## Vision

v59 解决的是 v58 之后一个非常现实的使用门槛问题：现在 transcript drilldown 已经能用了，但 Jaeger 在日常调试里仍然有两个障碍：

- `Search` 与 `Trace` 页面还是大量英文术语，阅读负担高；
- Search / Trace 页面还有残余可读性问题，尤其在深色主题下容易再次出现“文字看不清”；
- Jaeger UI 的 build / packaging / k3d 导入链路，已经踩出了一套真实经验，但还没沉淀成文档。

因此 v59 的目标是：

- 先把 `Search` 与 `Trace` 两个页面做成简体中文可读；
- 把这两个页面与 transcript panel 的主题安全可读性问题一起收口；
- 把 Jaeger UI 构建 / runtime packaging / WSL / k3d 导入经验写成仓库内经验包；
- 不改变当前用户入口与部署语义：
  - `oa chat --k3d-real`
  - `http://127.0.0.1:16686`

## Milestones

- **M1: Search 页面中文化**
  - Plan: `docs/plan/v59-jaeger-search-trace-zh-cn.md`
  - PRD: `docs/prd/PRD-0059-jaeger-search-trace-zh-cn-v59.md`
  - DoD（命令证据）：
    - `python -m unittest -q tests.test_v58_jaeger_ui_assets tests.test_v59_jaeger_ui_localization_assets`
  - Status: planned

- **M2: Trace 页面中文化与可读性收口**
  - Plan: `docs/plan/v59-jaeger-search-trace-zh-cn.md`
  - PRD: `docs/prd/PRD-0059-jaeger-search-trace-zh-cn-v59.md`
  - DoD（命令证据）：
    - `python -m unittest -q tests.test_actor_tracing tests.test_session_transcript_view tests.test_cluster_chat_transcript_api tests.test_remote_worker_transcript_api tests.test_v58_jaeger_ui_assets tests.test_v59_jaeger_ui_localization_assets`
  - Status: planned

- **M3: Jaeger 构建与部署经验包**
  - Plan: `docs/plan/v59-jaeger-search-trace-zh-cn.md`
  - PRD: `docs/prd/PRD-0059-jaeger-search-trace-zh-cn-v59.md`
  - DoD（命令证据）：
    - 文档审阅通过
    - 经验包中的命令与 fallback 路径可被逐条核对
  - Status: planned

## Plan Index

- `docs/plan/v59-jaeger-search-trace-zh-cn.md`

## Traceability Matrix

- REQ-0059-001 → `docs/plan/v59-jaeger-search-trace-zh-cn.md` → `tests.test_v59_jaeger_ui_localization_assets` + Jaeger Search 页手工验证 → pending
- REQ-0059-002 → `docs/plan/v59-jaeger-search-trace-zh-cn.md` → `tests.test_v59_jaeger_ui_localization_assets` + Jaeger Trace 页手工验证 → pending
- REQ-0059-003 → `docs/plan/v59-jaeger-search-trace-zh-cn.md` → `tests.test_v58_jaeger_ui_assets` + `tests.test_v59_jaeger_ui_localization_assets` + 深浅主题手工验证 → pending
- REQ-0059-004 → `docs/plan/v59-jaeger-search-trace-zh-cn.md` → `tests.test_actor_tracing` + `tests.test_session_transcript_view` + `tests.test_cluster_chat_transcript_api` + `tests.test_remote_worker_transcript_api` + real cluster smoke → pending
- REQ-0059-005 → `docs/plan/v59-jaeger-search-trace-zh-cn.md` → Python 资产测试 + real cluster 手工验证 → pending
- REQ-0059-006 → `docs/plan/v59-jaeger-search-trace-zh-cn.md` → 文档经验包章节审阅 → pending
- REQ-0059-007 → `docs/plan/v59-jaeger-search-trace-zh-cn.md` → vendored source diff 审阅 + build / packaging 回归 → pending

## ECN

- None
