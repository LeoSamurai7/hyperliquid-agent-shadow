import unittest
from agent.short_liquidity_sweep_research import (
    detect_bearish_liquidity_sweep, structural_episode_key,
)


class SweepResearchTests(unittest.TestCase):
    def setUp(self):
        self.bars = [
            {"time": i + 1, "open": 100, "high": 102, "low": 99, "close": 100}
            for i in range(12)
        ]

    def test_closed_bearish_sweep(self):
        bar = {"time": 13, "open": 103, "high": 106, "low": 98, "close": 100}
        result = detect_bearish_liquidity_sweep(self.bars + [bar])
        self.assertIsNotNone(result)
        self.assertEqual(result.reference, 102)
        self.assertEqual(result.setup_key, "SHORT:LIQUIDITY_SWEEP:13")

    def test_no_sweep_without_high_break(self):
        bar = {"time": 13, "open": 101, "high": 102, "low": 98, "close": 100}
        self.assertIsNone(detect_bearish_liquidity_sweep(self.bars + [bar]))

    def test_no_sweep_on_bullish_candle(self):
        bar = {"time": 13, "open": 100, "high": 106, "low": 98, "close": 103}
        self.assertIsNone(detect_bearish_liquidity_sweep(self.bars + [bar]))

    def test_reject_repeated_timestamp(self):
        with self.assertRaises(ValueError):
            detect_bearish_liquidity_sweep(self.bars + [
                {"time": 12, "open": 103, "high": 106, "low": 98, "close": 100}
            ])

    def test_structural_identity(self):
        self.assertEqual(
            structural_episode_key("BREAKDOWN_RETEST", "SHORT", 42),
            structural_episode_key("BREAKDOWN_RETEST", "SHORT", 42),
        )
        self.assertNotEqual(
            structural_episode_key("BREAKDOWN_RETEST", "SHORT", 42),
            structural_episode_key("BREAKDOWN_RETEST", "SHORT", 43),
        )
        with self.assertRaises(ValueError):
            structural_episode_key("LIQUIDITY_SWEEP", "LONG", 42)


if __name__ == "__main__":
    unittest.main()
