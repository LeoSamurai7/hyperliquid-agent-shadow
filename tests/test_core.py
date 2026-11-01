
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
    d=Decision(action="HOLD",confidence=0,stop_loss_pct=None,take_profit_pct=None,
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


def test_config_forces_free_model(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY","test")
    monkeypatch.setenv("OPENROUTER_MODEL","nvidia/nemotron-3.5-lightning")
    monkeypatch.setenv("SHADOW_MODE","true")
    monkeypatch.setenv("EXECUTION_ENABLED","false")
    monkeypatch.setenv("HL_DATA_NETWORK","mainnet")
    from agent.config import load
    c=load()
    assert c.model=="nvidia/nemotron-3.5-lightning:free"

def test_config_replaces_unapproved_paid_model(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY","test")
    monkeypatch.setenv("OPENROUTER_MODEL","some/paid-model")
    monkeypatch.setenv("SHADOW_MODE","true")
    monkeypatch.setenv("EXECUTION_ENABLED","false")
    monkeypatch.setenv("HL_DATA_NETWORK","mainnet")
    from agent.config import load
    c=load()
    assert c.model=="nvidia/nemotron-3.5-lightning:free"


def test_decision_contract_rejects_direction_with_zero_confidence():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Decision(action="SHORT",confidence=0,stop_loss_pct=1.5,take_profit_pct=2.5,
                 thesis="x",invalidation="y",horizon_hours=8)

def test_decision_contract_rejects_zero_horizon():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Decision(action="HOLD",confidence=0,stop_loss_pct=None,take_profit_pct=None,
                 thesis="x",invalidation="y",horizon_hours=0)

def test_decision_contract_hold_is_zero_confidence():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Decision(action="HOLD",confidence=50,stop_loss_pct=None,take_profit_pct=None,
                 thesis="x",invalidation="y",horizon_hours=4)

def test_decision_contract_valid_short():
    d=Decision(action="SHORT",confidence=82,stop_loss_pct=1.5,take_profit_pct=2.5,
               thesis="x",invalidation="y",horizon_hours=8)
    assert d.action=="SHORT" and d.confidence==82


def test_store_observer_is_separate_from_strategy(tmp_path):
    from agent.store import Store
    from agent.ai import Decision
    st=Store(str(tmp_path),1000)
    d=Decision(action="SHORT",confidence=82,stop_loss_pct=1.0,take_profit_pct=2.0,
               thesis="research",invalidation="x",horizon_hours=8)
    st.observer_decision(10,d,True,"OK",{"meta":{"ok":True},"research_only":True})
    assert len(st.observers(10))==1
    assert st.trades(10)==[]
    assert st.decisions(10)==[]

def test_config_observer_is_hard_disabled(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY","test")
    monkeypatch.setenv("OPENROUTER_MODEL","nvidia/nemotron-3.5-lightning")
    monkeypatch.setenv("SHADOW_MODE","true")
    monkeypatch.setenv("EXECUTION_ENABLED","false")
    monkeypatch.setenv("HL_DATA_NETWORK","mainnet")
    monkeypatch.delenv("FAST_OBSERVER_ENABLED",raising=False)
    monkeypatch.delenv("FAST_OBSERVER_INTERVAL_MINUTES",raising=False)
    from agent.config import load
    c=load()
    assert c.observer_enabled is False



def test_candidate_long_alignment():
    from agent.candidate import detect_candidate
    def tf(trend,close,ema21,rsi,ret3,ct=100):
        return {"trend":trend,"close":close,"ema21":ema21,"rsi14":rsi,"ret3_pct":ret3,
                "bar":{"close_time":ct}}
    s={"timeframes":{
        "5m":tf("UP",101,100,55,0.4),
        "15m":tf("UP",102,100,58,0.5,200),
        "1h":tf("UP",105,100,60,1.0),
        "4h":tf("UP",110,100,62,2.0)}}
    c=detect_candidate(s,None)
    assert c and c.kind=="ENTRY" and c.side=="LONG"

def test_candidate_requires_htf_alignment():
    from agent.candidate import detect_candidate
    def tf(trend,close,ema21,rsi,ret3,ct=100):
        return {"trend":trend,"close":close,"ema21":ema21,"rsi14":rsi,"ret3_pct":ret3,
                "bar":{"close_time":ct}}
    s={"timeframes":{
        "5m":tf("UP",101,100,55,0.4),
        "15m":tf("UP",102,100,58,0.5,200),
        "1h":tf("UP",105,100,60,1.0),
        "4h":tf("DOWN",95,100,40,-2.0)}}
    assert detect_candidate(s,None) is None

def test_ai_daily_budget_is_hard_capped(tmp_path):
    from agent.store import Store
    st=Store(str(tmp_path),1000)
    assert st.consume_ai_call("2026-10-31",2) is True
    assert st.consume_ai_call("2026-10-31",2) is True
    assert st.consume_ai_call("2026-10-31",2) is False
    assert st.ai_calls("2026-10-31")==2


def test_signer_config_defaults(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY","x")
    monkeypatch.delenv("HL_SIGNER_TOKEN",raising=False)
    from agent.config import load
    c=load()
    assert c.signer_base_url=="https://hl-n8n-signer-production.up.railway.app"
    assert c.signer_token==""


def test_execution_target_must_be_testnet(monkeypatch):
    import pytest
    monkeypatch.setenv("OPENROUTER_API_KEY","x")
    monkeypatch.setenv("EXECUTION_ENABLED","true")
    monkeypatch.setenv("HL_SIGNER_TOKEN","x")
    monkeypatch.setenv("HL_EXECUTION_TARGET","mainnet")
    from agent.config import load
    with pytest.raises(RuntimeError,match="testnet"):
        load()

def test_execution_notional_hard_cap(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY","x")
    monkeypatch.setenv("EXECUTION_ENABLED","false")
    monkeypatch.setenv("MAX_TESTNET_NOTIONAL_USD","999")
    from agent.config import load
    c=load()
    assert c.max_testnet_notional_usd==25.0

def test_execution_journal_idempotency(tmp_path):
    from agent.store import Store
    st=Store(str(tmp_path),1000)
    assert st.execution_begin(1,"fp","LONG",0.001,{"x":1}) is True
    assert st.execution_begin(2,"fp","LONG",0.001,{"x":2}) is False
    st.execution_finish("fp","OPEN",{"ok":True})
    x=st.execution_latest()
    assert x["fingerprint"]=="fp" and x["status"]=="OPEN"


def test_ai_smoke_pass_uses_same_model_and_forces_hold():
    from agent.ai import Trader
    class Resp:
        status_code=200
        text=""
        def raise_for_status(self): pass
        def json(self):
            return {
                "model":"nvidia/nemotron-3.5-lightning:free",
                "provider":"TEST_PROVIDER",
                "usage":{"total_tokens":10},
                "choices":[{"finish_reason":"tool_calls","native_finish_reason":"tool_calls",
                            "message":{"tool_calls":[{"function":{
                                "name":"submit_trade_decision",
                                "arguments":'{"action":"HOLD","confidence":0,"stop_loss_pct":null,"take_profit_pct":null,"thesis":"smoke ok","invalidation":"N/A","horizon_hours":1}'
                            }}]}}]
            }
    class Sess:
        def __init__(self): self.body=None
        def post(self,url,headers,json,timeout):
            self.body=json
            return Resp()
    t=Trader("secret","https://openrouter.ai/api/v1","nvidia/nemotron-3.5-lightning:free")
    t.s=Sess()
    d,m=t.smoke()
    assert m["ok"] is True and d.action=="HOLD"
    assert t.s.body["model"]=="nvidia/nemotron-3.5-lightning:free"
    assert t.s.body["max_tokens"]==700

def test_ai_smoke_fail_does_not_expose_api_key():
    from agent.ai import Trader
    class Resp:
        status_code=404
        text='{"error":{"message":"ZDR violation"}}'
        def raise_for_status(self):
            import requests
            raise requests.HTTPError("404")
    class Sess:
        def post(self,*a,**k): return Resp()
    t=Trader("super-secret-key","https://openrouter.ai/api/v1","nvidia/nemotron-3.5-lightning:free")
    t.s=Sess()
    d,m=t.smoke()
    assert m["ok"] is False and d.action=="HOLD"
    assert "super-secret-key" not in str(m)


def test_candidate_pullback_reentry_short():
    from agent.candidate import detect_candidate
    def tf(trend,close,ema21,ema55,rsi,ret3,ct=100):
        return {"trend":trend,"close":close,"ema21":ema21,"ema55":ema55,
                "rsi14":rsi,"ret3_pct":ret3,"bar":{"close_time":ct}}
    s={"timeframes":{
        "5m":tf("DOWN",98,100,101,42,-0.3),
        "15m":tf("DOWN",97,100,101,40,-0.5,200),
        "1h":tf("MIXED",98,99,100,45,-0.2),
        "4h":tf("DOWN",95,100,105,42,-1.0)}}
    c=detect_candidate(s,None)
    assert c and c.side=="SHORT" and c.reason=="H4_REGIME_PULLBACK_REENTRY"

def test_candidate_pullback_does_not_countertrend():
    from agent.candidate import detect_candidate
    def tf(trend,close,ema21,ema55,rsi,ret3,ct=100):
        return {"trend":trend,"close":close,"ema21":ema21,"ema55":ema55,
                "rsi14":rsi,"ret3_pct":ret3,"bar":{"close_time":ct}}
    s={"timeframes":{
        "5m":tf("UP",102,100,100,60,0.3),
        "15m":tf("UP",103,100,100,61,0.5,200),
        "1h":tf("MIXED",102,100,100,60,0.2),
        "4h":tf("DOWN",95,100,105,42,-1.0)}}
    assert detect_candidate(s,None) is None
