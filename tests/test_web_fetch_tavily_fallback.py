import os
import unittest
from unittest import mock

from openagentic_sdk.tools.base import ToolContext
from openagentic_sdk.tools.web_fetch import WebFetchTool


class TestWebFetchTavilyExtract(unittest.TestCase):
    def test_uses_tavily_extract_as_primary_path(self) -> None:
        def transport(url, headers):
            _ = (url, headers)
            return 200, {"content-type": "text/plain"}, b"direct content should not be used"

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
                        "raw_content": "primary extracted content",
                    }
                ]
            }

        tool = WebFetchTool(transport=transport, extract_transport=extract_transport, allow_private_networks=True)
        with mock.patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}, clear=False):
            out = tool.run_sync({"url": "https://example.com/report"}, ToolContext(cwd="/"))

        self.assertEqual(out["backend"], "tavily_extract")
        self.assertEqual(out["status"], 200)
        self.assertEqual(out["text"], "primary extracted content")

    def test_requires_tavily_api_key(self) -> None:
        def transport(url, headers):
            _ = (url, headers)
            raise AssertionError("direct transport should not be used")

        def extract_transport(url, headers, payload):
            _ = (url, headers, payload)
            raise AssertionError("extract transport should not be called without TAVILY_API_KEY")

        tool = WebFetchTool(transport=transport, extract_transport=extract_transport, allow_private_networks=True)
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TAVILY_API_KEY", None)
            with self.assertRaises(RuntimeError):
                tool.run_sync({"url": "https://example.com/app"}, ToolContext(cwd="/"))

    def test_custom_headers_are_rejected(self) -> None:
        def transport(url, headers):
            _ = (url, headers)
            raise AssertionError("direct transport should not be used")

        def extract_transport(url, headers, payload):
            _ = (url, headers, payload)
            raise AssertionError("extract transport should not be called when headers are unsupported")

        tool = WebFetchTool(transport=transport, extract_transport=extract_transport, allow_private_networks=True)
        with mock.patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}, clear=False):
            with self.assertRaises(ValueError):
                tool.run_sync(
                    {"url": "https://example.com/private", "headers": {"authorization": "Bearer token"}},
                    ToolContext(cwd="/"),
                )

    def test_private_hosts_are_rejected_even_when_allow_private_networks_is_true(self) -> None:
        def transport(url, headers):
            _ = (url, headers)
            raise AssertionError("direct transport should not be used")

        def extract_transport(url, headers, payload):
            _ = (url, headers, payload)
            raise AssertionError("private host should never be sent to Tavily")

        tool = WebFetchTool(transport=transport, extract_transport=extract_transport, allow_private_networks=True)
        with mock.patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}, clear=False):
            with self.assertRaises(ValueError):
                tool.run_sync({"url": "http://localhost/private"}, ToolContext(cwd="/"))


if __name__ == "__main__":
    unittest.main()
