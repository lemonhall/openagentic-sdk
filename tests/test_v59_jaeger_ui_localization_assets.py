from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
JAEGER_UI_ROOT = REPO_ROOT / "third_party" / "jaeger-ui"


class TestV59JaegerUiLocalizationAssets(unittest.TestCase):
    def test_search_page_core_copy_is_localized(self) -> None:
        top_nav = (JAEGER_UI_ROOT / "packages/jaeger-ui/src/components/App/TopNav.tsx").read_text(encoding="utf-8")
        self.assertIn("text: '搜索'", top_nav)
        self.assertIn("text: '对比'", top_nav)
        self.assertIn("text: '系统架构'", top_nav)
        self.assertIn("text: '监控'", top_nav)

        trace_id_input = (
            JAEGER_UI_ROOT / "packages/jaeger-ui/src/components/App/TraceIDSearchInput.tsx"
        ).read_text(encoding="utf-8")
        self.assertIn('placeholder="按 Trace ID 跳转..."', trace_id_input)

        search_results = (
            JAEGER_UI_ROOT / "packages/jaeger-ui/src/components/SearchTracePage/SearchResults/index.tsx"
        ).read_text(encoding="utf-8")
        self.assertIn("排序：", search_results)
        self.assertIn("最新优先", search_results)
        self.assertIn("Span 数最多", search_results)
        self.assertIn("没有找到 Trace 结果。请尝试其他查询条件。", search_results)

        alt_view = (
            JAEGER_UI_ROOT / "packages/jaeger-ui/src/components/SearchTracePage/SearchResults/AltViewOptions.tsx"
        ).read_text(encoding="utf-8")
        self.assertIn("深度依赖图", alt_view)
        self.assertIn("Trace 结果", alt_view)
        self.assertIn("查看全部依赖", alt_view)

    def test_trace_page_core_copy_is_localized(self) -> None:
        header = (
            JAEGER_UI_ROOT / "packages/jaeger-ui/src/components/TracePage/TracePageHeader/TracePageHeader.tsx"
        ).read_text(encoding="utf-8")
        self.assertIn("label: '开始时间'", header)
        self.assertIn("label: '耗时'", header)
        self.assertIn("label: '服务数'", header)
        self.assertIn("label: '深度'", header)
        self.assertIn("label: 'Span 总数'", header)
        self.assertIn("不完整", header)
        self.assertIn("归档 Trace", header)

        trace_views = (
            JAEGER_UI_ROOT / "packages/jaeger-ui/src/components/TracePage/TracePageHeader/AltViewOptions.tsx"
        ).read_text(encoding="utf-8")
        self.assertIn("Trace 时间线", trace_views)
        self.assertIn("Trace 图", trace_views)
        self.assertIn("Trace 统计", trace_views)
        self.assertIn("Span 表格", trace_views)
        self.assertIn("Trace 火焰图", trace_views)
        self.assertIn("其他视图", trace_views)
        self.assertIn("Trace JSON（原始）", trace_views)

        trace_search = (
            JAEGER_UI_ROOT / "packages/jaeger-ui/src/components/TracePage/TracePageHeader/TracePageSearchBar.tsx"
        ).read_text(encoding="utf-8")
        self.assertIn("这是页内搜索", trace_search)
        self.assertIn("精确短语搜索", trace_search)
        self.assertIn("排除某些键值对", trace_search)

        span_detail = (
            JAEGER_UI_ROOT / "packages/jaeger-ui/src/components/TracePage/TraceTimelineViewer/SpanDetail/index.tsx"
        ).read_text(encoding="utf-8")
        self.assertIn("label: '服务：'", span_detail)
        self.assertIn("label: '耗时：'", span_detail)
        self.assertIn("label: '起始时间：'", span_detail)
        self.assertIn('data-label="SpanID："', span_detail)

        transcript_panel = (
            JAEGER_UI_ROOT
            / "packages/jaeger-ui/src/components/TracePage/TraceTimelineViewer/SpanDetail/OaTranscriptPanel.tsx"
        ).read_text(encoding="utf-8")
        self.assertIn("会话正文", transcript_panel)
        self.assertIn("模式：", transcript_panel)
        self.assertIn("会话：", transcript_panel)
        self.assertIn("节点：", transcript_panel)
        self.assertIn("代理：", transcript_panel)
        self.assertIn("执行：", transcript_panel)
        self.assertIn("正在加载会话正文...", transcript_panel)
        self.assertIn("当前会话还没有可显示的 user/assistant 正文。", transcript_panel)


if __name__ == "__main__":
    unittest.main()
