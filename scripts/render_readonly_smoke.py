"""Read-only Render smoke test. Never loads trading keys or submits orders."""
import json
import sqlite3
import tempfile
import time
import urllib.request
from pathlib import Path

def main():
    started = time.time()
    payload = json.dumps({"type": "allMids"}).encode()
    req = urllib.request.Request(
        "https://api.hyperliquid.xyz/info", data=payload,
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as response:
        mids = json.load(response)
    btc = float(mids["BTC"])
    if btc <= 0:
        raise RuntimeError("INVALID_BTC_MARK")
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "probe.db"
        with sqlite3.connect(path) as conn:
            conn.execute("CREATE TABLE episode (k TEXT PRIMARY KEY, v TEXT)")
            conn.execute("INSERT INTO episode VALUES ('probe', 'locked')")
        with sqlite3.connect(path) as conn:
            value = conn.execute("SELECT v FROM episode WHERE k='probe'").fetchone()[0]
        if value != "locked":
            raise RuntimeError("SQLITE_REOPEN_FAILED")
    print(json.dumps({
        "status": "PASS", "mode": "READ_ONLY_NO_ORDERS",
        "market": "HYPERLIQUID_MAINNET_PUBLIC", "btc_mid": btc,
        "sqlite_same_run": "PASS",
        "cross_run_persistence": "NOT_CONFIGURED",
        "signer_called": False, "ai_called": False,
        "orders_sent": 0, "elapsed_seconds": round(time.time()-started, 2)
    }))

if __name__ == "__main__":
    main()
