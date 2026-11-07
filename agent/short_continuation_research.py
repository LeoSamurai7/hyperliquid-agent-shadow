"""Research-only EARLY bearish continuation; intentionally not wired to orders.

A fresh 15m local low after a brief pause, in aligned H1/H4 bearish regime,
can be a candidate for a SHORT even when no 12-bar support retest exists.
Conservative guardrails prevent chasing extended candles / late downswings.
"""
from agent.short_research import ShortResearchResult, _atr, _number, _bad


def _ema(values, period):
    alpha=2/(period+1)
    e=values[0]
    for v in values[1:]:
        e=e+alpha*(v-e)
    return e


def evaluate_short_early_continuation(m15_bars,h1,h4,asof_ms):
    if len(m15_bars)<64:
        return _bad('INSUFFICIENT_HISTORY')
    if not isinstance(asof_ms,int) or asof_ms<=0:
        return _bad('INVALID_ASOF')
    last_close=0
    for row in m15_bars:
        ts=_number(row.get('close_time'))
        values=[_number(row.get(k)) for k in ('open','high','low','close')]
        if ts is None or ts<=last_close or ts>asof_ms:
            return _bad('UNSORTED_OR_FUTURE_M15')
        if any(v is None or v<=0 for v in values):
            return _bad('INVALID_OHLC')
        o,high,low,close=values
        if not low<=min(o,close)<=max(o,close)<=high:
            return _bad('INVALID_OHLC')
        last_close=ts
    for tf,row in (('H4',h4),('H1',h1)):
        ts=_number(row.get('close_time'))
        if ts is None or ts<=0 or ts>asof_ms:
            return _bad(tf+'_FUTURE_OR_MISSING')
        close=_number(row.get('close'));ema=_number(row.get('ema21'))
        if close is None or ema is None or close>=ema:
            return _bad(tf+'_PRICE_NOT_BEARISH')
    if h4.get('trend')!='DOWN':
        return _bad('H4_NOT_DOWN')
    if h1.get('trend') not in ('DOWN','MIXED'):
        return _bad('H1_OPPOSITE_TREND')
    atr=_atr(m15_bars)
    if atr is None or atr<=0:
        return _bad('ATR_UNAVAILABLE')
    last=m15_bars[-1]
    close=float(last['close'])
    if not .0005<=atr/close<=.04:
        return _bad('ATR_REGIME_OUT_OF_RANGE')
    vals=[float(b['close']) for b in m15_bars]
    ema9=_ema(vals,9)
    ema21=_ema(vals,21)
    if not (ema9<ema21 and close<ema9):
        return _bad('M15_NOT_BEARISH')
    prev=m15_bars[-4:-1]
    # A pause distinguishes a new short opportunity from chasing a waterfall
    # of red candles and consuming AI budget every fifteen minutes.
    if not any(float(b['close'])>=float(b['open']) or
               abs(float(b['close'])-float(b['open']))<0.20*atr
               for b in prev):
        return _bad('NO_PAUSE_BEFORE_IMPULSE')
    support=min(float(b['low']) for b in prev)
    if not close<support-.08*atr:
        return _bad('NO_LOCAL_BREAK')
    body=float(last['open'])-close
    if body<.25*atr:
        return _bad('WEAK_BEARISH_IMPULSE')
    if body>1.35*atr:
        return _bad('IMPULSE_TOO_LARGE')
    if ema21-close>1.60*atr:
        return _bad('LATE_ENTRY_CHASE_GUARD')
    stop=max(float(last['high']),support+.45*atr,
             max(float(b['high']) for b in prev))+0.15*atr
    risk=stop-close
    risk_pct=risk/close*100
    if not .4<=risk_pct<=4.0:
        return _bad('STOP_OUTSIDE_EXISTING_RISK_RANGE')
    target=close-2*risk
    if target<=0:
        return _bad('INVALID_TARGET')
    return ShortResearchResult(
        True,'EARLY_CONTINUATION_SHORT_RESEARCH',
        setup_id='SHORT_IMPULSE:'+str(int(last['close_time'])),
        support=round(support,8),entry_reference=round(close,8),
        stop_reference=round(stop,8),target_reference=round(target,8),
        risk_pct=round(risk_pct,6),atr=round(atr,8),
    )
