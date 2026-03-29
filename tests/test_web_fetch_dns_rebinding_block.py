import unittest

import openagentic_sdk.tools.web_fetch as wf
from openagentic_sdk.tools.web_fetch import WebFetchTool


class TestWebFetchDnsRebinding(unittest.TestCase):
    def test_blocks_hostname_resolving_to_private_ip(self) -> None:
        def fake_getaddrinfo(host, port, *args, **kwargs):  # noqa: ANN001,ANN002,ANN003
            _ = (host, port, args, kwargs)
            return [(None, None, None, None, ("127.0.0.1", 80))]

        old = getattr(wf, "_getaddrinfo", None)
        wf._getaddrinfo = fake_getaddrinfo
        try:
            t = WebFetchTool()
            with self.assertRaises(ValueError) as ctx:
                t._validate_url("http://example.com/")
            self.assertIn("blocked hostname", str(ctx.exception))
        finally:
            wf._getaddrinfo = old

