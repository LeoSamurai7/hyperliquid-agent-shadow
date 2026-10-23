
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


def test_store_filters_failed_ai_decisions(tmp_path):
    from agent.store import Store
    from agent.ai import Decision
    st=Store(str(tmp_path),1000)
    d=Decision(action="HOLD",confidence=0,stop_loss_pct=0,take_profit_pct=0,
               thesis="x",invalidation="y",horizon_hours=24)
    st.decision(1,d,False,"HOLD",{"meta":{"ok":False}})
    st.decision(2,d,False,"HOLD",{"meta":{"ok":True}})
    assert len(st.decisions(10))==1
    assert len(st.decisions(10,include_invalid=True))==2

def test_store_system_events(tmp_path):
    from agent.store import Store
    st=Store(str(tmp_path),1000)
    st.event(1,"AI_PROVIDER_ERROR",{"status":429})
    e=st.events(10)
    assert len(e)==1 and e[0]["event_type"]=="AI_PROVIDER_ERROR"


def test_config_allows_approved_paid_model(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY","test")
    monkeypatch.setenv("OPENROUTER_MODEL","nvidia/nemotron-3.5-lightning")
    monkeypatch.setenv("SHADOW_MODE","true")
    monkeypatch.setenv("EXECUTION_ENABLED","false")
    monkeypatch.setenv("HL_DATA_NETWORK","mainnet")
    from agent.config import load
    c=load()
    assert c.model=="nvidia/nemotron-3.5-lightning"

def test_config_rejects_unapproved_paid_model(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY","test")
    monkeypatch.setenv("OPENROUTER_MODEL","some/paid-model")
    monkeypatch.setenv("SHADOW_MODE","true")
    monkeypatch.setenv("EXECUTION_ENABLED","false")
    monkeypatch.setenv("HL_DATA_NETWORK","mainnet")
    import pytest
    from agent.config import load
    with pytest.raises(RuntimeError, match="MODEL LOCK"):
        load()
