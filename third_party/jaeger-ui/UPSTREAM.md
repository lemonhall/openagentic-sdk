# Jaeger UI Vendored Snapshot

- Upstream repository: `https://github.com/jaegertracing/jaeger-ui.git`
- Upstream tag: `v2.16.0`
- Upstream commit: `050fbe2a84b943ae8ec6e539c28a117133eb8684`
- Snapshot date: `2026-03-29`

## Local Patch Boundary

This vendored snapshot is tracked in git because v58 needs a repeatable, auditable UI patch instead of runtime-only JS/CSS injection.

The local openagentic patch boundary for v58 M2 is intentionally narrow:

- `packages/jaeger-ui/src/components/TracePage/TracePageHeader/TracePageHeader.css`
  - readability fixes for low-contrast header text
- `packages/jaeger-ui/src/components/common/LabeledList.css`
  - stronger contrast for summary labels and values
- `packages/jaeger-ui/src/components/TracePage/TraceTimelineViewer/SpanBarRow.css`
  - stronger contrast for service / operation names in the timeline list
- `packages/jaeger-ui/src/components/TracePage/TraceTimelineViewer/VirtualizedTraceView.tsx`
  - dynamic detail-row height tracking for transcript drilldown
- `packages/jaeger-ui/src/components/TracePage/TraceTimelineViewer/SpanDetail/index.tsx`
  - transcript panel mount point + detail height measurement hook
- `packages/jaeger-ui/src/components/TracePage/TraceTimelineViewer/SpanDetail/index.css`
  - stronger contrast for span detail content
- `packages/jaeger-ui/src/components/TracePage/TraceTimelineViewer/SpanDetail/OaTranscriptPanel.tsx`
  - on-demand transcript fetch, cache, structured error rendering
- `packages/jaeger-ui/src/components/TracePage/TraceTimelineViewer/SpanDetail/OaTranscriptPanel.css`
  - transcript panel layout and readability

## Build Entry

- Workspace install: `npm ci --ignore-scripts`
- Bundle Plexus worker:
  - `cd packages/plexus && NODE_ENV=production npx webpack --mode production --config webpack.layout-worker.config.js`
- Build Jaeger UI:
  - `cd packages/jaeger-ui && NODE_ENV=production REACT_APP_VSN_STATE='{"version":"2.16.0","snapshot":"openagentic-v58"}' npx vite build`
- Output directory: `packages/jaeger-ui/build/`

## Deployment Intention

v58 keeps the fixed user-facing Jaeger URL:

- `http://127.0.0.1:16686`

The expected deployment shape is:

- Jaeger query backend exposed internally as `jaeger-query-internal`
- A lightweight proxy/static UI service exposed externally as `jaeger-query`
- Transcript requests proxied from the custom UI to `oa-cluster-chat-host.openagentic-v56-real.svc.cluster.local:8766`
