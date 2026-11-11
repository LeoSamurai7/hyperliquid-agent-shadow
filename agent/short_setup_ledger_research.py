"""Research-only persistent idempotency for structural SHORT episode IDs.

Not connected to production candidate detection, AI, or order execution.
The database must be stored on durable shared storage; ephemeral CI files do
not provide cross-run protection. No automatic expiry of claimed IDs.
"""
import re
import sqlite3
from pathlib import Path

_KEY = re.compile(r"^SHORT:(BREAKDOWN_RETEST|LIQUIDITY_SWEEP):([1-9][0-9]*)$")


def claim_setup(db_path, setup_key):
    """Atomically claim a setup once. Return True only for its first claim.

    Uses SQLite UNIQUE constraint and BEGIN IMMEDIATE to serialize writers.
    The caller must NOT interpret a claim as authorization to place an order.
    """
    if not isinstance(setup_key, str) or not _KEY.fullmatch(setup_key):
        raise ValueError("invalid structural SHORT setup key")
    path = Path(db_path)
    if str(path) == ":memory:":
        raise ValueError("in-memory databases cannot persist claims")
    if not path.parent.exists():
        raise FileNotFoundError("database directory must exist")
    with sqlite3.connect(str(path), timeout=10, isolation_level=None) as db:
        db.execute("PRAGMA busy_timeout=10000")
        db.execute("""CREATE TABLE IF NOT EXISTS research_short_claims (
            setup_key TEXT PRIMARY KEY,
            claimed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        db.execute("BEGIN IMMEDIATE")
        try:
            cursor = db.execute(
                "INSERT OR IGNORE INTO research_short_claims(setup_key) VALUES (?)",
                (setup_key,),
            )
            db.execute("COMMIT")
            return cursor.rowcount == 1
        except BaseException:
            db.execute("ROLLBACK")
            raise


def claimed_count(db_path):
    """Research diagnostics only."""
    with sqlite3.connect(str(db_path)) as db:
        return db.execute("SELECT COUNT(*) FROM research_short_claims").fetchone()[0]
