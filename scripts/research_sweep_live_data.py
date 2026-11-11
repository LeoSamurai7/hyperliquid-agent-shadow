"""Read-only BTC historical 15m sweep backtest, run in isolated CI.

Fetches public candles only. No credentials, exchange signing, or orders.
"""
import hashlib
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone

from scripts.research_sweep_replay import replay

INTERVAL_MS = 900_000
API = "https://api.hyperliquid.xyz/info"


def fetch_btc_15m(days=30, end_ms=None):
    if not 7 <= days <= 35:
        raise ValueError("days out of range")
    now = int(time.time() * 1000)
    end_ms = now if end_ms is None else int(end_ms)
    if end_ms > now:
        raise ValueError("future end")
    start_ms = end_ms - days * 86_400_000
    request = urllib.request.Request(
        API,
        data=json.dumps({"type": "candleSnapshot", "req": {
            "coin": "BTC", "interval": "15m",
            "startTime": start_ms, "endTime": end_ms}}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "research-v17-readonly"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=35) as response:
        data = json.load(response)
    if not isinstance(data, list):
        raise ValueError("invalid API response")
    rows = []
    for x in data:
        close_time = int(x["T"])
        if close_time > end_ms or close_time <= start_ms:
            continue
        rows.append({"time": close_time, "open": float(x["o"]),
                     "high": float(x["h"]), "low": float(x["l"]),
                     "close": float(x["c"])})
    rows.sort(key=lambda x: x["time"])
    if len(rows) < days * 80:
        raise ValueError("incomplete historical coverage")
    if any(b["time"] - a["time"] > INTERVAL_MS + 1000
           for a, b in zip(rows, rows[1:])):
        raise ValueError("historical candle gap")
    if len({x["time"] for x in rows}) != len(rows):
        raise ValueError("duplicate candle timestamps")
    return rows


def main():
    rows = fetch_btc_15m()
    cutoff = int(len(rows) * 0.7)
    # Context from preceding development candles is permitted; results
    # are classified by signal_time to avoid double-counting.
    full = replay(rows)
    cutoff_time = rows[cutoff]["time"]
    dev = [x for x in full["results"] if x["signal_time"] < cutoff_time]
    oos = [x for x in full["results"] if x["signal_time"] >= cutoff_time]
    def summary(xs):
        n = len(xs)
        return {"trades": n, "net_r": round(sum(x["net_r"] for x in xs), 5),
                "avg_r": round(sum(x["net_r"] for x in xs) / n, 5) if n else None,
                "win_rate": round(sum(x["net_r"] > 0 for x in xs) / n, 5) if n else None}
    report = {
        "research_only": True, "execution_enabled": False,
        "symbol": "BTC", "interval": "15m",
        "source": API, "bar_count": len(rows),
        "first_close_utc": datetime.fromtimestamp(rows[0]["time"]/1000,timezone.utc).isoformat(),
        "last_close_utc": datetime.fromtimestamp(rows[-1]["time"]/1000,timezone.utc).isoformat(),
        "holdout_cutoff_utc": datetime.fromtimestamp(cutoff_time/1000,timezone.utc).isoformat(),
        "dataset_sha256": hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest(),
        "assumptions": {"fee_bps_per_side":4.5, "slip_bps_per_side":1.0,
                        "rr":2.0, "max_hold_bars":32, "stop_first":True},
        "development": summary(dev), "holdout": summary(oos),
        "total": summary(full["results"]),
        "trades": full["results"],
        "limitations": "No funding, depth, orderbook, regime comparison, independent OOS or actual fills."
    }
    with open("v17_sweep_backtest.json", "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(json.dumps({k:v for k,v in report.items() if k != "trades"},indent=2))
    if not oos:
        print("WARNING: no holdout trades; cannot validate strategy", file=sys.stderr)


if __name__ == "__main__":
    main()
