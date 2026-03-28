import os
import unittest
from unittest import mock

from openagentic_sdk.tools.base import ToolContext
from openagentic_sdk.tools.web_fetch import WebFetchTool


class TestWebFetchTavilyFallback(unittest.TestCase):
    def test_falls_back_to_tavily_extract_on_blocked_http_response(self) -> None:
        def transport(url, headers):
            _ = (url, headers)
            return 403, {"content-type": "text/html"}, b"<html><body>Access denied. error code: 1010</body></html>"

        def extract_transport(url, headers, payload):
            _ = headers
            self.assertEqual(url, "https://api.tavily.com/extract")
            self.assertEqual(payload["api_key"], "test-key")
            self.assertEqual(payload["urls"], ["https://example.com/report"])
            self.assertEqual(payload["extract_depth"], "advanced")
            return {
                "results": [
                    {
                        "url": "https://example.com/report",
                        "raw_content": "clean extracted content",
                    }
                ]
            }

        tool = WebFetchTool(transport=transport, extract_transport=extract_transport, allow_private_networks=True)
        with mock.patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}, clear=False):
            out = tool.run_sync({"url": "https://example.com/report"}, ToolContext(cwd="/"))

        self.assertEqual(out["backend"], "tavily_extract")
        self.assertEqual(out["fallback_reason"], "http_status:403")
        self.assertEqual(out["status"], 200)
        self.assertEqual(out["direct_status"], 403)
        self.assertEqual(out["text"], "clean extracted content")

    def test_falls_back_to_tavily_extract_on_html_shell_page(self) -> None:
        def transport(url, headers):
            _ = (url, headers)
            html = (
                "<html><head>"
                "<script src='/static/app.js'></script>"
                "<script src='/static/vendor.js'></script>"
                "<script src='/static/runtime.js'></script>"
                "</head><body><div id='app'></div></body></html>"
            )
            return 200, {"content-type": "text/html; charset=utf-8"}, html.encode("utf-8")

        def extract_transport(url, headers, payload):
            _ = (url, headers, payload)
            return {"results": [{"url": "https://example.com/app", "raw_content": "rendered app text"}]}

        tool = WebFetchTool(transport=transport, extract_transport=extract_transport, allow_private_networks=True)
        with mock.patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}, clear=False):
            out = tool.run_sync({"url": "https://example.com/app"}, ToolContext(cwd="/"))

        self.assertEqual(out["backend"], "tavily_extract")
        self.assertEqual(out["fallback_reason"], "html_shell")
        self.assertEqual(out["text"], "rendered app text")

    def test_falls_back_to_tavily_extract_on_placeholder_heavy_quote_page(self) -> None:
        def transport(url, headers):
            _ = (url, headers)
            nav = "财经 焦点 股票 新股 期指 期权 行情 数据 全球 美股 港股 期货 外汇 黄金 银行 基金 理财 保险 债券 视频 股吧 财富号 搜索 "
            quote = "上证 ： - - - - 深证 ： - - - - 港股通 - 资金流入 - 沪股通 - 资金流入 - 深股通 - 资金流入 - "
            html = (
                "<html><head>"
                "<script src='/static/a.js'></script>"
                "<script src='/static/b.js'></script>"
                "<script src='/static/c.js'></script>"
                "<script src='/static/d.js'></script>"
                "<script src='/static/e.js'></script>"
                "<script src='/static/f.js'></script>"
                "<script src='/static/g.js'></script>"
                "<script src='/static/h.js'></script>"
                "</head><body><div id='app'>"
                f"黄金9999 行情中心 {nav * 8} {quote * 12}"
                "</div></body></html>"
            )
            return 200, {"content-type": "text/html; charset=utf-8"}, html.encode("utf-8")

        def extract_transport(url, headers, payload):
            _ = (url, headers, payload)
            return {"results": [{"url": "https://example.com/quote", "raw_content": "live quote text"}]}

        tool = WebFetchTool(transport=transport, extract_transport=extract_transport, allow_private_networks=True)
        with mock.patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}, clear=False):
            out = tool.run_sync({"url": "https://example.com/quote"}, ToolContext(cwd="/"))

        self.assertEqual(out["backend"], "tavily_extract")
        self.assertEqual(out["fallback_reason"], "html_shell")
        self.assertEqual(out["text"], "live quote text")

    def test_custom_headers_keep_direct_fetch_semantics(self) -> None:
        def transport(url, headers):
            self.assertEqual(url, "https://example.com/private")
            self.assertEqual(headers, {"authorization": "Bearer token"})
            return 403, {"content-type": "text/plain"}, b"forbidden"

        def extract_transport(url, headers, payload):
            _ = (url, headers, payload)
            raise AssertionError("tavily extract should not run when custom headers are requested")

        tool = WebFetchTool(transport=transport, extract_transport=extract_transport, allow_private_networks=True)
        with mock.patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}, clear=False):
            out = tool.run_sync(
                {"url": "https://example.com/private", "headers": {"authorization": "Bearer token"}},
                ToolContext(cwd="/"),
            )

        self.assertEqual(out["backend"], "direct")
        self.assertEqual(out["status"], 403)
        self.assertEqual(out["text"], "forbidden")


if __name__ == "__main__":
    unittest.main()
