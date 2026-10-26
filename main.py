import threading
from fastapi import FastAPI
from agent.config import load
from agent.store import Store
from agent.runtime import Runtime

c=load()
st=Store(c.data_dir,c.equity)
rt=Runtime(c,st)
app=FastAPI(title="Hyperliquid Agent V1.2 Live Shadow")

@app.on_event("startup")
def start():
    threading.Thread(target=rt.loop,daemon=True).start()

@app.on_event("shutdown")
def stop():
    rt.stop.set()

@app.get("/health")
def health():
    return {"ok":True,"mode":"SHADOW","execution_enabled":False,
            "coin":c.symbol,"model":c.model,"runtime":rt.status()}

@app.get("/state")
def state():
    return {"equity":st.equity(),"position":st.position(),"risk":rt.risk(),
            "runtime":rt.status(),"snapshot":rt.snap}

@app.get("/trades")
def trades(limit:int=100):
    return {"trades":st.trades(min(max(limit,1),500))}

@app.get("/decisions")
def decisions(limit:int=50,include_invalid:bool=False):
    return {"decisions":st.decisions(min(max(limit,1),200),include_invalid=include_invalid)}

@app.get("/observer")
def observer(limit:int=100,include_invalid:bool=False):
    return {"observer_decisions":st.observers(min(max(limit,1),500),include_invalid=include_invalid)}

@app.get("/events")
def events(limit:int=100):
    return {"events":st.events(min(max(limit,1),500))}

@app.get("/report")
def report():
    x=st.recent(500)
    wins=sum(1 for t in x if (t.get("pnl") or 0)>0)
    obs=st.observers(500)
    return {"starting_equity":c.equity,"current_equity":st.equity(),
            "closed_trades":len(x),"wins":wins,
            "win_rate":wins/len(x) if x else None,
            "realized_pnl":sum(float(t.get("pnl") or 0) for t in x),
            "today":st.stats(),"position":st.position(),
            "observer_samples":len(obs),
            "observer_hypothetical_passes":sum(1 for o in obs if o.get("hypothetical_approved")),
            "runtime":rt.status()}
