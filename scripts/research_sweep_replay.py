"""Offline causal 15m sweep replay; CSV only, no exchange or credentials.

CSV columns: close_time,open,high,low,close (close_time in Unix ms).
A signal at bar close is filled at the NEXT bar open. Stop-first within
ambiguous candles, fee and slippage both sides. Research, not orders.
"""
import argparse
import csv
import json
from agent.short_liquidity_sweep_research import detect_bearish_liquidity_sweep


def replay(bars, *, lookback=12, stop_buffer=0.001, rr=2.0,
           fee_bps=4.5, slip_bps=1.0, max_hold=32):
    if not (lookback >= 3 and stop_buffer > 0 and rr > 0 and
            fee_bps >= 0 and slip_bps >= 0 and max_hold >= 1):
        raise ValueError("invalid replay parameters")
    if any(a["time"] >= b["time"] for a, b in zip(bars, bars[1:])):
        raise ValueError("non-chronological candles")
    trades = []
    seen = set()
    busy_until = -1
    for i in range(lookback, len(bars) - 1):
        if i <= busy_until:
            continue
        signal = detect_bearish_liquidity_sweep(bars[:i + 1], lookback)
        if signal is None or signal.setup_key in seen:
            continue
        seen.add(signal.setup_key)
        entry_idx = i + 1
        entry = bars[entry_idx]["open"] * (1 - slip_bps / 10000)
        stop = bars[i]["high"] * (1 + stop_buffer)
        risk = stop - entry
        if risk <= 0:
            continue
        target = entry - rr * risk
        if target <= 0:
            continue
        last = min(len(bars) - 1, i + max_hold)
        exit_idx = last
        reason = "TIME"
        exit_price = bars[last]["close"] * (1 + slip_bps / 10000)
        for j in range(entry_idx, last + 1):
            if bars[j]["high"] >= stop:
                exit_idx, reason = j, "STOP"
                exit_price = stop * (1 + slip_bps / 10000)
                break
            if bars[j]["low"] <= target:
                exit_idx, reason = j, "TARGET"
                exit_price = target * (1 + slip_bps / 10000)
                break
        fees = (entry + exit_price) * fee_bps / 10000
        pnl_r = (entry - exit_price - fees) / risk
        trades.append({"setup_key": signal.setup_key, "signal_time": bars[i]["time"],
                       "entry_time": bars[entry_idx]["time"], "exit_time": bars[exit_idx]["time"],
                       "exit": reason, "net_r": round(pnl_r, 5)})
        busy_until = exit_idx
    n = len(trades)
    return {"research_only": True, "trades": n,
            "net_r": round(sum(t["net_r"] for t in trades), 5),
            "avg_r": round(sum(t["net_r"] for t in trades) / n, 5) if n else None,
            "win_rate": round(sum(t["net_r"] > 0 for t in trades) / n, 5) if n else None,
            "results": trades,
            "limitations": "OHLC proxy, stop-first, fixed fees/slippage; no funding, depth, exchange failures, or independent OOS."}


def load_csv(path):
    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return [{"time": int(row["close_time"]), **{
        k: float(row[k]) for k in ("open", "high", "low", "close")}} for row in rows]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="15m closed candles CSV")
    args = parser.parse_args()
    print(json.dumps(replay(load_csv(args.csv)), indent=2))
