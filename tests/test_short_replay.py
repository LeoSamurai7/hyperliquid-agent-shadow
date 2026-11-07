from scripts.research_short_replay import simulate_short, summarize, ema_context, replay
from agent.short_research import ShortResearchResult


def test_stop_first_in_candle_with_both_stop_and_tp():
    bars=[{'open':100,'high':100,'low':100,'close':100},
          {'open':100,'high':103,'low':96,'close':99}]
    r=ShortResearchResult(True,'ok',entry_reference=100,stop_reference=102,target_reference=98)
    x=simulate_short(bars,0,r)
    assert x['status']=='STOP' and x['r']<0


def test_next_bar_only_and_slippage_charged():
    bars=[{'open':100,'high':100,'low':100,'close':100},
          {'open':100,'high':100.3,'low':98,'close':99}]
    r=ShortResearchResult(True,'ok',entry_reference=100,stop_reference=102,target_reference=98)
    x=simulate_short(bars,0,r)
    assert x['status']=='TARGET' and x['r']<1.0


def test_higher_tf_warmup_and_no_lookahead():
    rows=[{'close':100-i*0.05,'close_time':(i+1)*1000} for i in range(60)]
    z=ema_context(rows)
    assert z[53] is None and z[54] is not None
    assert z[-1]['trend']=='DOWN'


def test_empty_replay_is_reported_as_no_evidence():
    base=[{'open':100,'close':100,'high':100.3,'low':99.7,'close_time':(i+1)*900000} for i in range(200)]
    h1=[{'close':100,'close_time':(i+1)*3600000} for i in range(60)]
    h4=[{'close':100,'close_time':(i+1)*14400000} for i in range(60)]
    r=replay(base,h1,h4,days=7)
    assert r['oos']['trades']==0 and r['development']['trades']==0
    assert r['research_only'] and not r['execution_enabled']


def test_metrics_do_not_fake_win_rate_for_empty_input():
    z=summarize([])
    assert z['trades']==0 and z['avg_r'] is None
