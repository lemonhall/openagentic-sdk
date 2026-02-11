import unittest


class TestRuntimePublicApiSmoke(unittest.TestCase):
    def test_runtime_exports_expected_symbols(self) -> None:
        import openagentic_sdk.runtime as rt

        self.assertTrue(hasattr(rt, "AgentRuntime"))
        self.assertTrue(hasattr(rt, "RunResult"))

        from openagentic_sdk.runtime import AgentRuntime, RunResult  # noqa: F401


if __name__ == "__main__":
    unittest.main()

