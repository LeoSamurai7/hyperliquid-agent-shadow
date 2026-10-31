import math,time
from .signer import SignerClient

class TestnetExecution:
    def __init__(self,c,st):
        self.c=c; self.st=st
        self.signer=SignerClient(c.signer_base_url,c.signer_token)
        self.last_reconcile=None
        self.last_error=None

    def preflight(self):
        h=self.signer.health()
        ok=(h.get("ok") is True and h.get("network")=="testnet" and
            h.get("execution_enabled") is True and h.get("kill_switch") is False)
        return {"ok":ok,"agent_execution_enabled":bool(self.c.execution),
                "target":self.c.execution_target,"signer":h}

    def _position_from_snapshot(self,snap):
        positions=((snap or {}).get("account") or {}).get("positions") or []
        for p in positions:
            if str(p.get("coin","")).upper()!=self.c.symbol:
                continue
            try:szi=float(p.get("szi") or 0)
            except Exception:szi=0.0
            if szi==0:return None
            return {
                "side":"LONG" if szi>0 else "SHORT",
                "qty":abs(szi),
                "entry_price":float(p.get("entryPx") or 0),
                "source":"TESTNET"
            }
        return None

    def position(self):
        if not self.c.execution:return None
        try:
            snap=self.signer.snapshot()
            self.last_error=None
            return self._position_from_snapshot(snap)
        except Exception as e:
            self.last_error=f"{type(e).__name__}: {e}"
            return None

    def _floor_btc_qty(self,x):
        return math.floor(max(float(x),0.0)*100000.0)/100000.0

    def place(self,cand,d,g,mark,ts):
        pf=self.preflight()
        if not pf["ok"]:
            return {"ok":False,"status":"PREFLIGHT_BLOCKED","preflight":pf}

        risk=self.signer.risk()
        gate=(risk or {}).get("risk_gate") or {}
        max_size=float((gate.get("max_size") or {}).get(self.c.symbol,0) or 0)
        server_notional=float(gate.get("max_notional_usd") or 0)
        cap=min(self.c.max_testnet_notional_usd,server_notional if server_notional>0 else self.c.max_testnet_notional_usd)
        qty=min(float(g.qty),max_size if max_size>0 else float(g.qty),(cap*0.98)/float(mark))
        qty=self._floor_btc_qty(qty)
        if qty<0.00001:
            return {"ok":False,"status":"QTY_TOO_SMALL","qty":qty,"cap":cap}

        if not self.st.execution_begin(ts,cand.fingerprint,cand.side,qty,{
            "candidate":cand.__dict__,"mark":mark,"agent_cap_usd":cap
        }):
            return {"ok":False,"status":"DUPLICATE_FINGERPRINT"}

        sl=float(d.stop_loss_pct)/100.0
        tp=float(d.take_profit_pct)/100.0
        stop=mark*(1-sl) if cand.side=="LONG" else mark*(1+sl)
        target=mark*(1+tp) if cand.side=="LONG" else mark*(1-tp)

        try:
            result=self.signer.place_bracket(
                self.c.symbol,cand.side=="LONG",qty,mark,stop,target)
            payload={"candidate":cand.__dict__,"strategy":{
                "entry":mark,"stop":stop,"target":target,"qty":qty},
                "signer_result":result}
            self.st.execution_finish(cand.fingerprint,"SUBMITTED",payload)
        except Exception as e:
            payload={"candidate":cand.__dict__,"error":f"{type(e).__name__}: {e}"}
            self.st.execution_finish(cand.fingerprint,"ERROR",payload)
            self.last_error=payload["error"]
            return {"ok":False,"status":"ERROR","error":payload["error"]}

        # One read-only reconciliation; never retry the order.
        try:
            snap=self.signer.snapshot()
            pos=self._position_from_snapshot(snap)
            fills=self.signer.fills(self.c.symbol,20)
            recent=[x for x in (fills.get("fills") or [])
                    if int(x.get("time_ms") or 0)>=int(ts)-5000]
            if pos:
                status="OPEN"
            elif recent:
                status="FILLED_OR_RESOLVED"
            else:
                status="NO_FILL"
            payload["reconcile"]={"position":pos,"recent_fills":recent[:6]}
            self.st.execution_finish(cand.fingerprint,status,payload)
            self.last_reconcile={"status":status,"position":pos}
            self.last_error=None
            return {"ok":status in {"OPEN","FILLED_OR_RESOLVED"},"status":status,
                    "position":pos,"recent_fills":recent[:6]}
        except Exception as e:
            err=f"{type(e).__name__}: {e}"
            payload["reconcile_error"]=err
            self.st.execution_finish(cand.fingerprint,"SUBMITTED_UNRECONCILED",payload)
            self.last_error=err
            return {"ok":True,"status":"SUBMITTED_UNRECONCILED","error":err}

    def reconcile(self):
        if not self.c.execution:return None
        latest=self.st.execution_latest()
        if not latest:return None
        if latest.get("status") not in {"SUBMITTED","SUBMITTED_UNRECONCILED","OPEN"}:
            return latest
        try:
            snap=self.signer.snapshot()
            pos=self._position_from_snapshot(snap)
            fills=self.signer.fills(self.c.symbol,30)
            recent=[x for x in (fills.get("fills") or [])
                    if int(x.get("time_ms") or 0)>=int(latest.get("ts_ms") or 0)-5000]
            if pos:status="OPEN"
            elif recent:status="RESOLVED"
            else:status="NO_FILL"
            payload={"reconcile":{"position":pos,"recent_fills":recent[:10]}}
            self.st.execution_finish(latest["fingerprint"],status,payload)
            self.last_reconcile={"status":status,"position":pos}
            self.last_error=None
            return {"status":status,"position":pos,"recent_fills":recent[:10]}
        except Exception as e:
            self.last_error=f"{type(e).__name__}: {e}"
            return {"status":"RECONCILE_ERROR","error":self.last_error}
