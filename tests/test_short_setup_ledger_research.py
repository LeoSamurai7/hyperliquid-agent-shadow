import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from agent.short_setup_ledger_research import claim_setup, claimed_count


class ShortSetupLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "ledger.sqlite"

    def test_first_claim_then_repeat(self):
        key = "SHORT:LIQUIDITY_SWEEP:100"
        self.assertTrue(claim_setup(self.db, key))
        self.assertFalse(claim_setup(self.db, key))
        self.assertEqual(claimed_count(self.db), 1)

    def test_persists_across_connections(self):
        self.assertTrue(claim_setup(self.db, "SHORT:BREAKDOWN_RETEST:100"))
        self.assertFalse(claim_setup(self.db, "SHORT:BREAKDOWN_RETEST:100"))

    def test_independent_events_can_claim(self):
        self.assertTrue(claim_setup(self.db, "SHORT:LIQUIDITY_SWEEP:100"))
        self.assertTrue(claim_setup(self.db, "SHORT:LIQUIDITY_SWEEP:200"))
        self.assertTrue(claim_setup(self.db, "SHORT:BREAKDOWN_RETEST:100"))
        self.assertEqual(claimed_count(self.db), 3)

    def test_invalid_keys_rejected(self):
        for key in ("ENTRY:SHORT", "SHORT:LIQUIDITY_SWEEP:0",
                    "SHORT:LIQUIDITY_SWEEP:abc", "SHORT:OTHER:100",
                    "SHORT:LIQUIDITY_SWEEP:1;DROP TABLE x", None):
            with self.subTest(key=key), self.assertRaises(ValueError):
                claim_setup(self.db, key)

    def test_simultaneous_claim_only_one_wins(self):
        key = "SHORT:LIQUIDITY_SWEEP:999"
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: claim_setup(self.db, key), range(16)))
        self.assertEqual(results.count(True), 1)
        self.assertEqual(claimed_count(self.db), 1)

    def test_missing_parent_rejected(self):
        with self.assertRaises(FileNotFoundError):
            claim_setup(Path(self.tmp.name) / "missing" / "ledger.sqlite",
                        "SHORT:LIQUIDITY_SWEEP:100")

    def test_memory_database_rejected(self):
        with self.assertRaises(ValueError):
            claim_setup(":memory:", "SHORT:LIQUIDITY_SWEEP:100")


if __name__ == "__main__":
    unittest.main()
