
from types import SimpleNamespace
from agent.ai import Decision
from agent.risk import entry_gate
from agent.virtual import ef,xf
def cfg(**k):
    d=dict(kill=False,min_conf=75,max_trades_day=6,daily_loss_pct=1.5,risk_pct=.25,max_notional_pct=100,min_stop_pct=.4,max_stop_pct=4,min_rr=1.5)
    d.update(k);return SimpleNamespace(**d)
def dec(conf=80,sl=1,tp=2):
    return Decision(action="LONG",confidence=conf,stop_loss_pct=sl,take_profit_pct=tp,thesis="x",invalidation="y",horizon_hours=24)
def test_good(): assert entry_gate(dec(),100,1000,0,0,cfg()).ok
def test_conf(): assert not entry_gate(dec(conf=50),100,1000,0,0,cfg()).ok
def test_rr(): assert not entry_gate(dec(sl=2,tp=2),100,1000,0,0,cfg()).ok
def test_daily(): assert not entry_gate(dec(),100,1000,-20,0,cfg()).ok
def test_fills(): assert ef("LONG",100,1)>100 and ef("SHORT",100,1)<100 and xf("LONG",100,1)<100 and xf("SHORT",100,1)>100
