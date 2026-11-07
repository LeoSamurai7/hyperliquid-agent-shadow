"""Research-only bearish breakdown / retest detector.

This module deliberately does not integrate with Runtime, Risk, Signer, or orders.
A positive result is an *offline hypothesis* and not authorization to trade.
All inputs must be fully closed bars at/before ``asof_ms``.
"""
from dataclasses import asdict, dataclass
import math
from typing import Mapping, Sequence


@dataclass(frozen=True)
class ShortResearchResult:
    eligible: bool
    reason: str
    setup_id: str | None = None
    support: float | None = None
    entry_reference: float | None = None
    stop_reference: float | None = None
    target_reference: float | None = None
    risk_pct: float | None = None
    atr: float | None = None
    research_only: bool = True

    def to_dict(self):
        return asdict(self)


def _number(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _bad(reason):
    return ShortResearchResult(False, reason)


def _atr(bars: Sequence[Mapping], period: int = 14):
    trs = []
    for i in range(1, len(bars)):
        x, previous = bars[i], bars[i - 1]
        high, low, close = (_number(x.get(k)) for k in ('high', 'low', 'close'))
        prev_close = _number(previous.get('close'))
        if high is None or low is None or close is None or prev_close is None:
            return None
        if low <= 0 or high < low:
            return None
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    if len(trs) < period:
        return None
    return sum(trs[-period:]) / period


def evaluate_short_break_retest(
    m15_bars: Sequence[Mapping],
    h1: Mapping,
    h4: Mapping,
    asof_ms: int,
    *,
    support_lookback: int = 12,
    retest_max_bars: int = 4,
) -> ShortResearchResult:
    """Return a research signal only after a *closed* 15m retest.

    Candidate structure: H4 & H1 bearish regime, break below the prior
    12-bar support (not including the breakout), then a failed retest of
    support on the most recent candle. Stop is above retest rejection high.
    The 2R target is *hypothetical*; fills are never placed here.
    """
    if support_lookback < 6 or retest_max_bars < 1:
        return _bad('INVALID_PARAMETERS')
    n = len(m15_bars)
    if n < max(32, support_lookback + retest_max_bars + 14):
        return _bad('INSUFFICIENT_HISTORY')
    if not isinstance(asof_ms, int) or asof_ms <= 0:
        return _bad('INVALID_ASOF')
    last_close = 0
    for bar in m15_bars:
        ts = _number(bar.get('close_time'))
        o, high, low, close = (_number(bar.get(k)) for k in ('open', 'high', 'low', 'close'))
        if ts is None or ts <= last_close or ts > asof_ms:
            return _bad('UNSORTED_OR_FUTURE_M15')
        if any(v is None for v in (o, high, low, close)) or min(o, high, low, close) <= 0 or not low <= min(o, close) <= max(o, close) <= high:
            return _bad('INVALID_OHLC')
        last_close = ts
    for tf, row in (('H4', h4), ('H1', h1)):
        ts = _number(row.get('close_time'))
        if ts is None or ts > asof_ms or ts <= 0:
            return _bad(tf + '_FUTURE_OR_MISSING')
        close = _number(row.get('close'))
        ema21 = _number(row.get('ema21'))
        if close is None or ema21 is None or close >= ema21:
            return _bad(tf + '_PRICE_NOT_BEARISH')
    if h4.get('trend') != 'DOWN':
        return _bad('H4_NOT_DOWN')
    if h1.get('trend') not in ('DOWN', 'MIXED'):
        return _bad('H1_OPPOSITE_TREND')

    atr = _atr(m15_bars)
    if atr is None or atr <= 0:
        return _bad('ATR_UNAVAILABLE')
    final = m15_bars[-1]
    final_close = float(final['close'])
    if not 0.0005 <= atr / final_close <= 0.04:
        return _bad('ATR_REGIME_OUT_OF_RANGE')

    # Breakout must PRECEDE the final retest candle. A breakout observed
    # later cannot be used to create an earlier hypothetical signal.
    first = max(support_lookback, n - 1 - retest_max_bars)
    for bi in range(n - 2, first - 1, -1):
        breakout = m15_bars[bi]
        support = min(float(b['low']) for b in m15_bars[bi - support_lookback:bi])
        if not (float(breakout['close']) < support - 0.10 * atr and
                float(breakout['close']) < float(breakout['open'])):
            continue
        # The level may be tested, but closes above it invalidate the break.
        if any(float(bar['close']) > support + 0.20 * atr
               for bar in m15_bars[bi + 1:]):
            return _bad('BREAKOUT_INVALIDATED')
        # A falling candle which revisits the old support and closes below.
        if float(final['high']) < support - 0.25 * atr:
            return _bad('NO_RETEST')
        if float(final['high']) > support + 0.45 * atr:
            return _bad('RETEST_OVERTHROW')
        if not (final_close < float(final['open']) and
                final_close < support - 0.08 * atr):
            return _bad('NO_BEARISH_REJECTION')
        if support - final_close > 0.75 * atr:
            return _bad('LATE_ENTRY_CHASE_GUARD')
        # The stop is structurally above the retested level/rejection wick.
        stop = max(float(final['high']), support + 0.35 * atr) + 0.15 * atr
        risk = stop - final_close
        risk_pct = risk / final_close * 100
        if not 0.4 <= risk_pct <= 4.0:
            return _bad('STOP_OUTSIDE_EXISTING_RISK_RANGE')
        # Target is a research-only 2R hypothesis, not a market order.
        target = final_close - 2.0 * risk
        if target <= 0:
            return _bad('INVALID_TARGET')
        return ShortResearchResult(
            True, 'BREAKDOWN_RETEST_SHORT_RESEARCH',
            setup_id='SHORT_BREAK:' + str(int(breakout['close_time'])),
            support=round(support, 8), entry_reference=round(final_close, 8),
            stop_reference=round(stop, 8), target_reference=round(target, 8),
            risk_pct=round(risk_pct, 6), atr=round(atr, 8),
        )
    return _bad('NO_CONFIRMED_BREAKDOWN')
