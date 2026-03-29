from __future__ import annotations

import os
import unittest
from unittest import mock


class TestWebProxyEnv(unittest.TestCase):
    def test_scoped_proxy_env_takes_precedence_over_global_proxy_env(self) -> None:
        from openagentic_sdk.tools._web_proxy import proxy_map_from_env

        with mock.patch.dict(
            os.environ,
            {
                "OPENAGENTIC_WEB_HTTP_PROXY": "http://scoped-http:17897",
                "OPENAGENTIC_WEB_HTTPS_PROXY": "http://scoped-https:17897",
                "HTTP_PROXY": "http://global-http:7897",
                "HTTPS_PROXY": "http://global-https:7897",
            },
            clear=False,
        ):
            proxy_map = proxy_map_from_env()

        self.assertEqual(
            proxy_map,
            {
                "http": "http://scoped-http:17897",
                "https": "http://scoped-https:17897",
            },
        )

    def test_global_proxy_env_is_used_when_scoped_proxy_env_is_absent(self) -> None:
        from openagentic_sdk.tools._web_proxy import proxy_map_from_env

        with mock.patch.dict(
            os.environ,
            {
                "HTTP_PROXY": "http://global-http:7897",
                "HTTPS_PROXY": "http://global-https:7897",
            },
            clear=True,
        ):
            proxy_map = proxy_map_from_env()

        self.assertEqual(
            proxy_map,
            {
                "http": "http://global-http:7897",
                "https": "http://global-https:7897",
            },
        )


if __name__ == "__main__":
    unittest.main()
