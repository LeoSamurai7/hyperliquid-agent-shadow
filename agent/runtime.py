import threading,time
from .market import Market,snapshot
from .ai import Trader
from .risk import entry_gate
from .virtual import openv,closev,stops

class Runtime:
    def __init__(self,c,st):
        self.c=c
        self.st=st
        self.m=Market(c.symbol)
        self.ai=Trader(c.api_key,c.base_url,c.model)
        self.stop=threading.Event()
        legacy=int(st.getkv("last_ai_ms",0) or 0)
        self.last_attempt=int(st.getkv("last_ai_attempt_ms",legacy) or 0)
        self.last_success=int(st.getkv("last_ai_success_ms",legacy) or 0)
        self.last_observer_attempt=int(st.getkv("last_observer_attempt_ms",0) or 0)
        self.last_observer_success=int(st.getkv("last_observer_success_ms",0) or 0)
        self.err=None
        self.snap=None

    def risk(self):
        x=self.st.stats()
        x.update({"equity":self.st.equity(),"risk_per_trade_pct":self.c.risk_pct,"kill_switch":self.c.kill})
        return x

    def status(self):
        return {
            "last_ai_ms":self.last_success,
            "last_ai_attempt_ms":self.last_attempt,
            "last_ai_success_ms":self.last_success,
            "last_observer_attempt_ms":self.last_observer_attempt,
            "last_observer_success_ms":self.last_observer_success,
            "observer_enabled":self.c.observer_enabled,
            "observer_interval_minutes":self.c.observer_minutes,
            "last_error":self.err,
            "last_snapshot_ts":(self.snap or {}).get("ts_ms")
        }

    def _run_official(self,snap,p,rs,ts,mark):
        d,meta=self.ai.decide(snap,p,rs,self.st.recent(5))
        self.last_attempt=ts
        self.st.setkv("last_ai_attempt_ms",ts)

        if meta.get("ok") is not True:
            event_type=meta.get("error_kind") or "AI_PROVIDER_ERROR"
            self.st.event(ts,event_type,
                          {"meta":meta,"mark":mark,"risk":rs,"model":self.c.model,"lane":"OFFICIAL"},
                          severity="WARN")
            return

        ok=False
        reason="HOLD"
        if p:
            if d.action=="CLOSE":
                closev(self.st,p,mark,self.c,ts,"AI_CLOSE")
                ok=True
                reason="AI_CLOSE"
            elif d.action in {"LONG","SHORT"}:
                reason="POSITION_OPEN_INVALID_ACTION"
            else:
                reason="POSITION_HOLD"
        else:
            if d.action in {"LONG","SHORT"}:
                g=entry_gate(d,mark,self.st.equity(),rs["daily_pnl"],rs["trades_today"],self.c)
                ok=g.ok
                reason=g.reason
                if ok:
                    openv(self.st,d.action,mark,g,d,self.c,ts)
            elif d.action=="CLOSE":
                reason="NO_POSITION"

        self.st.decision(ts,d,ok,reason,{"meta":meta,"mark":mark,"risk":rs,"lane":"OFFICIAL"})
        self.last_success=ts
        self.st.setkv("last_ai_success_ms",ts)
        self.st.setkv("last_ai_ms",ts)

    def _run_observer(self,snap,p,rs,ts,mark):
        d,meta=self.ai.decide(snap,p,rs,self.st.recent(5))
        self.last_observer_attempt=ts
        self.st.setkv("last_observer_attempt_ms",ts)

        if meta.get("ok") is not True:
            base=meta.get("error_kind") or "AI_PROVIDER_ERROR"
            self.st.event(ts,"OBSERVER_"+base,
                          {"meta":meta,"mark":mark,"risk":rs,"model":self.c.model,"lane":"OBSERVER"},
                          severity="WARN")
            return

        hypothetical=False
        reason="HOLD"
        if p:
            if d.action=="CLOSE":
                hypothetical=True
                reason="WOULD_CLOSE"
            elif d.action in {"LONG","SHORT"}:
                reason="POSITION_OPEN_INVALID_ACTION"
            else:
                reason="POSITION_HOLD"
        else:
            if d.action in {"LONG","SHORT"}:
                g=entry_gate(d,mark,self.st.equity(),rs["daily_pnl"],rs["trades_today"],self.c)
                hypothetical=g.ok
                reason=g.reason
            elif d.action=="CLOSE":
                reason="NO_POSITION"

        # Research-only lane: records hypothetical gate result but NEVER calls openv/closev.
        self.st.observer_decision(
            ts,d,hypothetical,reason,
            {"meta":meta,"mark":mark,"risk":rs,"lane":"OBSERVER","research_only":True}
        )
        self.last_observer_success=ts
        self.st.setkv("last_observer_success_ms",ts)

    def cycle(self):
        snap,raw=snapshot(self.m)
        self.snap=snap
        ts=snap["ts_ms"]
        mark=snap["mark_price"]
        p=self.st.position()

        if p:
            stops(self.st,p,raw["5m"].iloc[-1],self.c)
            p=self.st.position()

        official_due=(ts-self.last_attempt >= self.c.ai_minutes*60000)
        observer_due=(self.c.observer_enabled and
                      ts-self.last_observer_attempt >= self.c.observer_minutes*60000)

        # Official lane always has priority. Observer never runs on the same market snapshot.
        if official_due:
            self._run_official(snap,p,self.risk(),ts,mark)
            return

        if observer_due:
            self._run_observer(snap,p,self.risk(),ts,mark)

    def loop(self):
        while not self.stop.is_set():
            try:
                self.cycle()
                self.err=None
            except Exception as e:
                self.err=f"{type(e).__name__}: {e}"
                try:
                    self.st.event(int(time.time()*1000),"RUNTIME_EXCEPTION",
                                  {"error":self.err},severity="ERROR")
                except Exception:
                    pass
            self.stop.wait(max(30,self.c.loop_seconds))
