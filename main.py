import threading,time
from datetime import datetime,timezone
from fastapi import FastAPI
from agent.config import load
from agent.store import Store
from agent.runtime import Runtime
from agent.signer import SignerClient

c=load(); st=Store(c.data_dir,c.equity); rt=Runtime(c,st); signer=SignerClient(c.signer_base_url,c.signer_token)
app=FastAPI(title="Hyperliquid Agent V1.3 Candidate-Only Free AI")

@app.on_event("startup")
def start(): threading.Thread(target=rt.loop,daemon=True).start()

@app.on_event("shutdown")
def stop(): rt.stop.set()

@app.get("/health")
def health():
    s=rt.status()
    return {"ok":s["last_runtime_error"] is None,
            "mode":"SHADOW","execution_enabled":False,
            "coin":c.symbol,"model":c.model,"runtime":s}

@app.get("/execution/health")
def execution_health():
    x=signer.health()
    x["agent_execution_enabled"]=False
    x["mode"]="READ_ONLY_PREFLIGHT"
    return x

@app.get("/state")
def state():
    return {"equity":st.equity(),"position":st.position(),"risk":rt.risk(),
            "runtime":rt.status(),"snapshot":rt.snap}

@app.get("/trades")
def trades(limit:int=100): return {"trades":st.trades(min(max(limit,1),500))}

@app.get("/decisions")
def decisions(limit:int=50,include_invalid:bool=False):
    return {"decisions":st.decisions(min(max(limit,1),200),include_invalid=include_invalid)}

@app.get("/observer")
def observer(limit:int=100,include_invalid:bool=False):
    return {"observer_enabled":False,
            "note":"V1.2 history only; V1.3 no longer generates observer calls.",
            "observer_decisions":st.observers(min(max(limit,1),500),include_invalid=include_invalid)}

@app.get("/events")
def events(limit:int=100): return {"events":st.events(min(max(limit,1),500))}

@app.get("/report")
def report():
    x=st.recent(500); wins=sum(1 for t in x if (t.get("pnl") or 0)>0)
    now=int(time.time()*1000)
    day=datetime.fromtimestamp(now/1000,timezone.utc).strftime("%Y-%m-%d")
    return {"version":"1.3.0","starting_equity":c.equity,"current_equity":st.equity(),
            "closed_trades":len(x),"wins":wins,"win_rate":wins/len(x) if x else None,
            "realized_pnl":sum(float(t.get("pnl") or 0) for t in x),
            "today":st.stats(),"position":st.position(),
            "ai_calls_today":st.ai_calls(day),"ai_daily_limit":c.ai_daily_limit,
            "observer_enabled":False,"runtime":rt.status()}
