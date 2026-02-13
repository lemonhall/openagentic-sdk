import json
import os
import tempfile
import threading
import time
import unittest
from urllib.request import urlopen


class TestOagCmd(unittest.TestCase):
    def test_oag_starts_and_serves_health(self) -> None:
        from openagentic_gateway.__main__ import main

        os.environ["RIGHTCODE_API_KEY"] = "test"
        os.environ["RIGHTCODE_BASE_URL"] = "https://example.invalid"

        host = "127.0.0.1"
        port = 18989

        code_holder: dict[str, int] = {}

        with tempfile.TemporaryDirectory() as td:
            argv = [
                "--host",
                host,
                "--port",
                str(port),
                "--state-dir",
                td,
                "--exit-after",
                "1.5",
            ]

            def _run() -> None:
                code_holder["code"] = int(main(argv))

            t = threading.Thread(target=_run, name="test-oag", daemon=True)
            t.start()

            deadline = time.time() + 3.0
            last_err: Exception | None = None
            while time.time() < deadline:
                try:
                    with urlopen(f"http://{host}:{port}/health", timeout=0.5) as resp:  # noqa: S310
                        self.assertEqual(resp.status, 200)
                        obj = json.loads(resp.read().decode("utf-8"))
                        self.assertEqual(obj, {"ok": True})
                        break
                except Exception as e:  # noqa: BLE001
                    last_err = e
                    time.sleep(0.05)
            else:
                raise AssertionError(f"oag did not start: {last_err}")

            t.join(timeout=2.0)
            self.assertEqual(code_holder.get("code"), 0)


if __name__ == "__main__":
    unittest.main()
