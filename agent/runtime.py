import threading,time
from datetime import datetime,timezone
from .market import Market,snapshot
from .ai import Trader
from .candidate import detect_candidate
from .risk import entry_gate
from .virtual import openv,closev,stops

class Runtime:
    def __init__(self,c,st):
        self.c=c; self.st=st; self.m=Market(c.symbol)
        self.ai=Trader(c.api_key,c.base_url,c.model)
        self.stop=threading.Event()
        self.last_attempt=int(st.getkv("v13_last_ai_attempt_ms",0) or 0)
        self.last_success=int(st.getkv("v13_last_ai_success_ms",0) or 0)
        self.last_candidate=st.getkv("v13_last_candidate_fingerprint","")
        self.err=None; self.ai_err=None; self.snap=None

    def _day(self,ts):
        return datetime.fromtimestamp(ts/1000,timezone.utc).strftime("%Y-%m-%d")

    def risk(self):
        x=self.st.stats()
        x.update({"equity":self.st.equity(),"risk_per_trade_pct":self.c.risk_pct,"kill_switch":self.c.kill})
        return x

    def status(self):
        ts=(self.snap or {}).get("ts_ms")
        day=self._day(ts or int(time.time()*1000))
        return {
            "version":"1.3.0",
            "architecture":"CANDIDATE_ONLY_FREE_AI",
            "last_ai_attempt_ms":self.last_attempt,
            "last_ai_success_ms":self.last_success,
            "last_candidate_fingerprint":self.last_candidate,
            "ai_calls_today":self.st.ai_calls(day),
            "ai_daily_limit":self.c.ai_daily_limit,
            "observer_enabled":False,
            "last_runtime_error":self.err,
            "last_ai_error":self.ai_err,
            "last_snapshot_ts":ts
        }

    def _run_ai(self,snap,p,rs,ts,mark,cand):
        day=self._day(ts)
        if not self.st.consume_ai_call(day,self.c.ai_daily_limit):
            self.st.event(ts,"AI_DAILY_BUDGET_EXHAUSTED",
                          {"limit":self.c.ai_daily_limit,"candidate":cand.__dict__},
                          severity="WARN")
            return

        self.last_attempt=ts
        self.st.setkv("v13_last_ai_attempt_ms",ts)
        d,meta=self.ai.decide(snap,p,rs,self.st.recent(3),cand.__dict__)

        if meta.get("ok") is not True:
            self.ai_err=meta.get("error") or meta.get("error_kind")
            self.st.event(ts,meta.get("error_kind") or "AI_PROVIDER_ERROR",
                          {"meta":meta,"mark":mark,"risk":rs,"model":self.c.model,
                           "candidate":cand.__dict__,"lane":"CANDIDATE_ONLY"},
                          severity="WARN")
            return

        self.ai_err=None
        ok=False; reason="HOLD"
        if p:
            if d.action=="CLOSE":
                closev(self.st,p,mark,self.c,ts,"AI_CLOSE")
                ok=True; reason="AI_CLOSE"
            else:
                reason="POSITION_HOLD"
        else:
            if d.action in {"LONG","SHORT"}:
                if d.action!=cand.side:
                    reason="CANDIDATE_MISMATCH"
                else:
                    g=entry_gate(d,mark,self.st.equity(),rs["daily_pnl"],rs["trades_today"],self.c)
                    ok=g.ok; reason=g.reason
                    if ok: openv(self.st,d.action,mark,g,d,self.c,ts)
            else:
                reason="AI_VETO_HOLD"

        self.st.decision(ts,d,ok,reason,{
            "meta":meta,"mark":mark,"risk":rs,
            "lane":"CANDIDATE_ONLY","candidate":cand.__dict__
        })
        self.last_success=ts
        self.st.setkv("v13_last_ai_success_ms",ts)

    def cycle(self):
        snap,raw=snapshot(self.m)
        self.snap=snap
        ts=snap["ts_ms"]; mark=snap["mark_price"]
        p=self.st.position()

        if p:
            stops(self.st,p,raw["5m"].iloc[-1],self.c)
            p=self.st.position()

        cand=detect_candidate(snap,p)
        if cand is None:
            return
        if cand.fingerprint==self.last_candidate:
            return

        self.last_candidate=cand.fingerprint
        self.st.setkv("v13_last_candidate_fingerprint",cand.fingerprint)
        self.st.event(ts,"CANDIDATE_DETECTED",
                      {"candidate":cand.__dict__,"mark":mark,"position_id":p.get("id") if p else None},
                      severity="INFO")
        self._run_ai(snap,p,self.risk(),ts,mark,cand)

    def loop(self):
        while not self.stop.is_set():
            try:
                self.cycle(); self.err=None
            except Exception as e:
                self.err=f"{type(e).__name__}: {e}"
                try:self.st.event(int(time.time()*1000),"RUNTIME_EXCEPTION",{"error":self.err},severity="ERROR")
                except Exception:pass
            self.stop.wait(max(30,self.c.loop_seconds))
