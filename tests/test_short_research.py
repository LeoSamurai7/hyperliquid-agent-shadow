"""Deterministic research-only contract tests; no keys or exchange calls."""
from copy import deepcopy
from agent.short_research import evaluate_short_break_retest


def scenario():
    bars=[]
    for i in range(60):
        bars.append(dict(open=100.3, high=100.6, low=99.8,
                         close=100.2, close_time=(i+1)*900_000))
    bars.append(dict(open=100.0, high=100.1, low=99.0, close=99.15,
                     close_time=61*900_000))
    bars.append(dict(open=99.75, high=99.85, low=99.25, close=99.55,
                     close_time=62*900_000))
    h1=dict(close=98.0, ema21=99.0, trend='DOWN', close_time=60*900_000)
    h4=dict(close=95.0, ema21=100.0, trend='DOWN', close_time=56*900_000)
    return bars,h1,h4


def evaluate(s):
    b,h1,h4=s
    return evaluate_short_break_retest(b,h1,h4,b[-1]['close_time'])


def test_valid_breakout_retest_research_only_and_two_r():
    s=scenario()
    r=evaluate(s)
    assert r.eligible, r.reason
    assert r.research_only is True
    assert r.setup_id=='SHORT_BREAK:54900000'
    assert r.stop_reference>r.entry_reference>r.target_reference
    assert abs((r.entry_reference-r.target_reference)/(r.stop_reference-r.entry_reference)-2)<1e-5


def test_refuses_future_m15_candle_to_prevent_lookahead():
    b,h1,h4=scenario()
    r=evaluate_short_break_retest(b,h1,h4,b[-2]['close_time'])
    assert not r.eligible and r.reason=='UNSORTED_OR_FUTURE_M15'


def test_refuses_future_higher_timeframe():
    b,h1,h4=scenario()
    h4['close_time']=b[-1]['close_time']+1
    assert evaluate((b,h1,h4)).reason=='H4_FUTURE_OR_MISSING'


def test_refuses_uptrend_without_touching_long_logic():
    b,h1,h4=scenario()
    h4['trend']='UP'
    assert not evaluate((b,h1,h4)).eligible


def test_anti_chase_rejects_candle_closing_too_far_from_level():
    b,h1,h4=scenario()
    b[-1]['low']=97.9
    b[-1]['close']=98.1
    assert evaluate((b,h1,h4)).reason=='LATE_ENTRY_CHASE_GUARD'


def test_without_retest_never_enters_on_raw_breakdown():
    b,h1,h4=scenario()
    b[-1].update(open=99.4,high=99.45,low=99.05,close=99.2)
    assert evaluate((b,h1,h4)).reason=='NO_RETEST'


def test_retest_requires_bearish_rejection():
    b,h1,h4=scenario()
    b[-1].update(open=99.4,high=99.85,low=99.2,close=99.55)
    assert evaluate((b,h1,h4)).reason=='NO_BEARISH_REJECTION'


def test_no_signal_on_insufficient_history():
    b,h1,h4=scenario()
    r=evaluate_short_break_retest(b[-18:],h1,h4,b[-1]['close_time'])
    assert r.reason=='INSUFFICIENT_HISTORY'


def test_rejects_nonmonotonic_bar_timestamps():
    b,h1,h4=scenario()
    b[-2]['close_time']=b[-3]['close_time']
    assert evaluate((b,h1,h4)).reason=='UNSORTED_OR_FUTURE_M15'


def test_rejects_malformed_ohlc():
    b,h1,h4=scenario()
    b[-1]['high']=99.1
    assert evaluate((b,h1,h4)).reason=='INVALID_OHLC'


def test_setup_id_stable_for_same_breakout_bar():
    b,h1,h4=scenario()
    a=evaluate((b,h1,h4))
    # A second retest bar can produce an identical setup id; replay must dedupe.
    b.append(dict(open=99.76,high=99.9,low=99.3,close=99.52,close_time=63*900_000))
    z=evaluate((b,h1,h4))
    assert z.eligible and z.setup_id==a.setup_id


def test_pure_no_mutation():
    s=scenario(); before=deepcopy(s)
    evaluate(s)
    assert s==before
