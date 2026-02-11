import unittest

from openagentic_sdk.compaction import would_overflow
from openagentic_sdk.options import CompactionOptions


class TestCompactionOverflowParity(unittest.TestCase):
    def test_overflow_uses_reserved_and_ge_boundary(self) -> None:
        comp = CompactionOptions(
            auto=True,
            prune=True,
            context_limit=100,
            output_limit=50,
            global_output_cap=4096,
            protect_tool_output_tokens=40_000,
            min_prune_tokens=20_000,
            reserved=10,
            input_limit=None,
        )
        # usable = 100 - 10 = 90; count == usable should overflow (>=).
        usage = {"input_tokens": 60, "output_tokens": 20, "cache_read_tokens": 10}
        self.assertTrue(would_overflow(compaction=comp, usage=usage))

    def test_overflow_uses_input_limit_when_present(self) -> None:
        comp = CompactionOptions(
            auto=True,
            prune=True,
            context_limit=1000,
            output_limit=50,
            global_output_cap=4096,
            protect_tool_output_tokens=40_000,
            min_prune_tokens=20_000,
            reserved=10,
            input_limit=100,
        )
        usage = {"total_tokens": 89}
        self.assertFalse(would_overflow(compaction=comp, usage=usage))
        usage2 = {"total_tokens": 90}
        self.assertTrue(would_overflow(compaction=comp, usage=usage2))

    def test_overflow_derives_reserved_from_output_limits(self) -> None:
        comp = CompactionOptions(
            auto=True,
            prune=True,
            context_limit=30_000,
            output_limit=1_000,
            global_output_cap=4_096,
            protect_tool_output_tokens=40_000,
            min_prune_tokens=20_000,
            reserved=None,
            input_limit=None,
        )
        # max_output_tokens = min(4096, 1000) = 1000; reserved = min(20000, 1000) = 1000
        # usable = 30000 - 1000 = 29000
        self.assertTrue(would_overflow(compaction=comp, usage={"total_tokens": 29_000}))
        self.assertFalse(would_overflow(compaction=comp, usage={"total_tokens": 28_999}))


if __name__ == "__main__":
    unittest.main()

