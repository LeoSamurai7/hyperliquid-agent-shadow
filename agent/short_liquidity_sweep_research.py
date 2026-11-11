"""Research-only SHORT setup identity and liquidity-sweep detection.

No runtime wiring, no orders, no changes to existing BUY/AI/Risk gates.
All candles must be closed and chronologically sorted.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ShortSetup:
    kind: str
    setup_key: str
    trigger_time: int
    reference: float


def structural_episode_key(kind: str, side: str, closed_bar_time: int) -> str:
    """Stable per independently closed structural event, not per polling run."""
    if kind not in {"BREAKDOWN_RETEST", "LIQUIDITY_SWEEP"}:
        raise ValueError("unsupported structural setup")
    if side != "SHORT" or not isinstance(closed_bar_time, int) or closed_bar_time <= 0:
        raise ValueError("invalid side or closed bar time")
    return f"SHORT:{kind}:{closed_bar_time}"


def detect_bearish_liquidity_sweep(candles, lookback=12, min_wick_fraction=0.35):
    """Detect sweep above prior closed highs followed by a close back below.

    This is a hypothesis detector, NOT a validated entry strategy.
    candles: sequence of dicts with time, open, high, low, close.
    The latest element MUST be a completed candle.
    """
    if lookback < 3 or len(candles) < lookback + 1:
        return None
    window = candles[-lookback - 1:-1]
    bar = candles[-1]
    times = [x["time"] for x in candles]
    if any(not isinstance(t, int) or t <= 0 for t in times):
        raise ValueError("invalid candle time")
    if any(a >= b for a, b in zip(times, times[1:])):
        raise ValueError("candles must be strictly chronological")
    for x in candles:
        if not (x["low"] <= min(x["open"], x["close"]) <= max(x["open"], x["close"]) <= x["high"]):
            raise ValueError("invalid OHLC")
    prior_high = max(x["high"] for x in window)
    spread = bar["high"] - bar["low"]
    if spread <= 0:
        return None
    upper_wick = bar["high"] - max(bar["open"], bar["close"])
    if (bar["high"] > prior_high and bar["close"] < prior_high
            and bar["close"] < bar["open"]
            and upper_wick / spread >= min_wick_fraction):
        return ShortSetup("LIQUIDITY_SWEEP",
                          structural_episode_key("LIQUIDITY_SWEEP", "SHORT", bar["time"]),
                          bar["time"], prior_high)
    return None
