"""An early impulse must not mean chasing every red candle."""
from agent.short_continuation_research import evaluate_short_early_continuation


def scenario():
    bars=[]
    for i in range(70):
        close=100-.025*(i+1)
        bars.append(dict(open=close+.06, high=close+.23, low=close-.18,
                         close=close,close_time=(i+1)*900_000))
    p=bars[-1]['close']
    bars.append(dict(open=p, high=p+.15, low=p-.16, close=p+.05,close_time=71*900_000))
    q=min(b['low'] for b in bars[-3:])
    bars.append(dict(open=q+.20,high=q+.24,low=q-.34,close=q-.24,close_time=72*900_000))
    h1=dict(close=94.5,ema21=96.0,trend='DOWN',close_time=70*900_000)
    h4=dict(close=93.0,ema21=96.0,trend='DOWN',close_time=64*900_000)
    return bars,h1,h4


def test_realistic_early_impulse_is_research_only():
    b,h1,h4=scenario()
    x=evaluate_short_early_continuation(b,h1,h4,b[-1]['close_time'])
    assert x.eligible,x.reason
    assert x.research_only and x.setup_id.startswith('SHORT_IMPULSE:')
    assert x.stop_reference>x.entry_reference>x.target_reference


def test_future_m15_lookahead_is_forbidden():
    b,h1,h4=scenario()
    x=evaluate_short_early_continuation(b,h1,h4,b[-2]['close_time'])
    assert x.reason=='UNSORTED_OR_FUTURE_M15'


def test_no_pause_rejects_waterfall_red_candles():
    b,h1,h4=scenario()
    for row in b[-4:-1]:
        row['open']=row['close']+.3
        row['high']=max(row['high'],row['open']+.1)
    x=evaluate_short_early_continuation(b,h1,h4,b[-1]['close_time'])
    assert x.reason=='NO_PAUSE_BEFORE_IMPULSE'


def test_h4_trend_mismatch_is_blocked():
    b,h1,h4=scenario()
    h4['trend']='UP'
    assert not evaluate_short_early_continuation(b,h1,h4,b[-1]['close_time']).eligible


def test_oversized_candle_is_not_chased():
    b,h1,h4=scenario()
    b[-1]['low']-=2.0
    b[-1]['close']-=2.0
    x=evaluate_short_early_continuation(b,h1,h4,b[-1]['close_time'])
    assert not x.eligible and x.reason in ('IMPULSE_TOO_LARGE','LATE_ENTRY_CHASE_GUARD')
