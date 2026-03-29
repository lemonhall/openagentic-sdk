from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
JAEGER_UI_ROOT = REPO_ROOT / "third_party" / "jaeger-ui"


class TestV58JaegerUiAssets(unittest.TestCase):
    def test_vendored_upstream_metadata_is_recorded(self) -> None:
        upstream = (JAEGER_UI_ROOT / "UPSTREAM.md").read_text(encoding="utf-8")
        self.assertIn("https://github.com/jaegertracing/jaeger-ui.git", upstream)
        self.assertIn("v2.16.0", upstream)
        self.assertIn("050fbe2a84b943ae8ec6e539c28a117133eb8684", upstream)

    def test_transcript_panel_patch_is_present(self) -> None:
        panel = (
            JAEGER_UI_ROOT
            / "packages/jaeger-ui/src/components/TracePage/TraceTimelineViewer/SpanDetail/OaTranscriptPanel.tsx"
        ).read_text(encoding="utf-8")
        self.assertIn("const transcriptCache = new Map", panel)
        self.assertIn("/oa/transcript/session/", panel)
        self.assertIn("/oa/transcript/child/", panel)
        self.assertIn("oa.child_session_id", panel)
        self.assertIn("oa.target_node", panel)
        self.assertIn("sessionId && childSessionId && sessionId !== childSessionId", panel)
        self.assertIn("cacheKey: `root:${sessionId}`", panel)
        self.assertIn("cacheKey: `child:${targetNode}:${childSessionId}`", panel)

        span_detail = (
            JAEGER_UI_ROOT / "packages/jaeger-ui/src/components/TracePage/TraceTimelineViewer/SpanDetail/index.tsx"
        ).read_text(encoding="utf-8")
        self.assertIn("OaTranscriptPanel", span_detail)
        self.assertIn("jaeger:detail-measure", span_detail)

    def test_readability_patch_is_present(self) -> None:
        header_css = (
            JAEGER_UI_ROOT / "packages/jaeger-ui/src/components/TracePage/TracePageHeader/TracePageHeader.css"
        ).read_text(encoding="utf-8")
        self.assertIn("openagentic v58 readability", header_css)
        self.assertIn(".TracePageHeader--title", header_css)
        self.assertIn(".TracePageHeader--overviewItems", header_css)
        self.assertNotIn("#1f2328", header_css)
        self.assertNotIn("#57606a", header_css)
        self.assertNotIn("#f6f8fa", header_css)

        labeled_list_css = (
            JAEGER_UI_ROOT / "packages/jaeger-ui/src/components/common/LabeledList.css"
        ).read_text(encoding="utf-8")
        self.assertIn("openagentic v58 readability", labeled_list_css)
        self.assertIn(".LabeledList--label", labeled_list_css)
        self.assertNotIn("#1f2328", labeled_list_css)
        self.assertNotIn("#57606a", labeled_list_css)

        span_detail_css = (
            JAEGER_UI_ROOT / "packages/jaeger-ui/src/components/TracePage/TraceTimelineViewer/SpanDetail/index.css"
        ).read_text(encoding="utf-8")
        self.assertIn("openagentic v58 readability", span_detail_css)
        self.assertIn(".SpanDetail--debugInfo", span_detail_css)
        self.assertNotIn("#1f2328", span_detail_css)
        self.assertNotIn("#57606a", span_detail_css)

        transcript_css = (
            JAEGER_UI_ROOT
            / "packages/jaeger-ui/src/components/TracePage/TraceTimelineViewer/SpanDetail/OaTranscriptPanel.css"
        ).read_text(encoding="utf-8")
        self.assertIn(".OaTranscriptPanel", transcript_css)
        self.assertNotIn("#1f2328", transcript_css)
        self.assertNotIn("#57606a", transcript_css)
        self.assertNotIn("#f6f8fa", transcript_css)

    def test_v58_deploy_manifests_keep_fixed_jaeger_entrypoint(self) -> None:
        overlay = (REPO_ROOT / "deploy/k8s/v58/jaeger-ui-overlay.yaml").read_text(encoding="utf-8")
        proxy = (REPO_ROOT / "deploy/k8s/v58/jaeger-ui-proxy.yaml").read_text(encoding="utf-8")

        self.assertIn("jaeger-query-internal", overlay)
        self.assertIn("16686", overlay)
        self.assertIn("jaeger-query", proxy)
        self.assertIn("16686", proxy)
        self.assertIn("/oa/transcript/", proxy)
        self.assertIn("oa-cluster-chat-host.openagentic-v56-real.svc.cluster.local:8766", proxy)


if __name__ == "__main__":
    unittest.main()
