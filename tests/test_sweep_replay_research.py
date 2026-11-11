import unittest
from scripts.research_sweep_replay import replay

def bar(t, o=100, h=102, l=99, c=100):
    return {"time": t, "open": o, "high": h, "low": l, "close": c}

class SweepReplayTests(unittest.TestCase):
    def test_no_trades_no_fake_win_rate(self):
        r = replay([bar(i+1) for i in range(20)])
        self.assertEqual(r["trades"], 0)
        self.assertIsNone(r["win_rate"])

    def test_stop_first_when_both_hit(self):
        rows = [bar(i+1) for i in range(12)]
        rows += [bar(13,103,106,98,100), bar(14,100,108,90,99)]
        r = replay(rows)
        self.assertEqual(r["trades"], 1)
        self.assertEqual(r["results"][0]["exit"], "STOP")
        self.assertLess(r["net_r"], 0)

    def test_next_bar_fill(self):
        rows = [bar(i+1) for i in range(12)]
        rows += [bar(13,103,106,98,100), bar(14,100,101,90,95)]
        r = replay(rows)
        self.assertEqual(r["results"][0]["entry_time"], 14)
        self.assertEqual(r["results"][0]["exit"], "TARGET")

    def test_unsorted_rejected(self):
        with self.assertRaises(ValueError):
            replay([bar(2), bar(1)])

    def test_fee_reduces_net_r(self):
        rows = [bar(i+1) for i in range(12)]
        rows += [bar(13,103,106,98,100), bar(14,100,101,90,95)]
        self.assertLess(replay(rows,fee_bps=4.5)["net_r"],
                        replay(rows,fee_bps=0)["net_r"])

if __name__ == "__main__":
    unittest.main()
