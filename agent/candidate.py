from dataclasses import dataclass

@dataclass(frozen=True)
class Candidate:
    kind:str
    side:str|None
    reason:str
    fingerprint:str
    setup_key:str|None=None  # Optional structural setup ID; all legacy candidates default to None.

def _v(x,default=None):
    return default if x is None else x

def _entry_side(snap,side):
    t=snap["timeframes"]
    m5,m15,h1,h4=t["5m"],t["15m"],t["1h"],t["4h"]
    up=side=="LONG"
    want="UP" if up else "DOWN"

    if h1.get("trend")!=want or h4.get("trend")!=want:
        return False,"HTF_NOT_ALIGNED"
    if m15.get("trend")!=want and m5.get("trend")!=want:
        return False,"NO_LOWER_TF_CONFIRM"

    h1e=h1.get("ema21"); h4e=h4.get("ema21")
    if h1e is None or h4e is None:
        return False,"EMA_MISSING"
    if up and not (h1["close"]>h1e and h4["close"]>h4e):
        return False,"PRICE_NOT_ABOVE_HTF_EMA21"
    if (not up) and not (h1["close"]<h1e and h4["close"]<h4e):
        return False,"PRICE_NOT_BELOW_HTF_EMA21"

    r1=_v(h1.get("rsi14"),50); r4=_v(h4.get("rsi14"),50); r15=_v(m15.get("rsi14"),50)
    if up and not (40<=r1<=72 and 38<=r4<=72 and r15<75):
        return False,"RSI_FILTER"
    if (not up) and not (28<=r1<=60 and 28<=r4<=62 and r15>25):
        return False,"RSI_FILTER"

    rets=[_v(x.get("ret3_pct"),0.0) for x in (m5,m15,h1,h4)]
    confirms=sum(1 for x in rets if x>0) if up else sum(1 for x in rets if x<0)
    if confirms<2:
        return False,"MOMENTUM_FILTER"
    return True,"MTF_TREND_MOMENTUM"


def _pullback_side(snap,side):
    t=snap["timeframes"]
    m5,m15,h1,h4=t["5m"],t["15m"],t["1h"],t["4h"]
    up=side=="LONG"
    want="UP" if up else "DOWN"
    opposite="DOWN" if up else "UP"

    # Lane B: keep the 4h regime, allow 1h to be MIXED during a pullback,
    # but never allow the 1h to be in the opposite trend.
    if h4.get("trend")!=want:
        return False,"H4_REGIME_MISMATCH"
    if h1.get("trend")==opposite:
        return False,"H1_OPPOSITE_TREND"
    if m15.get("trend")!=want:
        return False,"M15_REENTRY_NOT_CONFIRMED"

    h4e=h4.get("ema21")
    h1e55=h1.get("ema55")
    if h4e is None or h1e55 is None:
        return False,"EMA_MISSING"

    if up and not (h4["close"]>h4e and h1["close"]>h1e55):
        return False,"PULLBACK_STRUCTURE_NOT_READY"
    if (not up) and not (h4["close"]<h4e and h1["close"]<h1e55):
        return False,"PULLBACK_STRUCTURE_NOT_READY"

    r1=_v(h1.get("rsi14"),50)
    r4=_v(h4.get("rsi14"),50)
    r15=_v(m15.get("rsi14"),50)
    if up and not (38<=r1<=68 and 38<=r4<=70 and r15<72):
        return False,"PULLBACK_RSI_FILTER"
    if (not up) and not (32<=r1<=62 and 30<=r4<=62 and r15>28):
        return False,"PULLBACK_RSI_FILTER"

    lower_rets=[_v(x.get("ret3_pct"),0.0) for x in (m5,m15,h1)]
    confirms=sum(1 for x in lower_rets if x>0) if up else sum(1 for x in lower_rets if x<0)
    if confirms<2:
        return False,"PULLBACK_MOMENTUM_FILTER"

    m5ret=_v(m5.get("ret3_pct"),0.0)
    if m5.get("trend")!=want:
        if up and m5ret<=0:
            return False,"M5_REENTRY_NOT_CONFIRMED"
        if (not up) and m5ret>=0:
            return False,"M5_REENTRY_NOT_CONFIRMED"

    return True,"H4_REGIME_PULLBACK_REENTRY"

def detect_candidate(snap,position):
    t=snap["timeframes"]
    m15=t["15m"]; h1=t["1h"]; h4=t["4h"]
    fpbar=int(m15["bar"]["close_time"])

    if position:
        side=position["side"]
        h1e=h1.get("ema21")
        if h1e is None:
            return None
        adverse=(h1["close"]<h1e and (h1.get("trend")=="DOWN" or h4.get("trend")=="DOWN")) if side=="LONG" else                 (h1["close"]>h1e and (h1.get("trend")=="UP" or h4.get("trend")=="UP"))
        if adverse:
            return Candidate("POSITION_REVIEW",side,"HTF_ADVERSE_REVIEW",f"REVIEW:{side}:{fpbar}")
        return None

    # Lane A: original strict multi-timeframe alignment.
    for side in ("LONG","SHORT"):
        ok,reason=_entry_side(snap,side)
        if ok:
            return Candidate("ENTRY",side,reason,f"ENTRY:{side}:{fpbar}")

    # Lane B: 4h-regime pullback/re-entry. This adds frequency without
    # permitting counter-trend entries or bypassing AI/Risk gates.
    for side in ("LONG","SHORT"):
        ok,reason=_pullback_side(snap,side)
        if ok:
            return Candidate("ENTRY",side,reason,f"ENTRY:{side}:{fpbar}")
    return None


def candidate_diagnostics(snap):
    t=snap["timeframes"]
    out={}
    for side in ("LONG","SHORT"):
        strict_ok,strict_reason=_entry_side(snap,side)
        pull_ok,pull_reason=_pullback_side(snap,side)
        out[side]={
            "eligible":bool(strict_ok or pull_ok),
            "path":"STRICT" if strict_ok else ("PULLBACK" if pull_ok else None),
            "strict_reason":strict_reason,
            "pullback_reason":pull_reason
        }
    out["context"]={
        "5m_trend":t["5m"].get("trend"),
        "15m_trend":t["15m"].get("trend"),
        "1h_trend":t["1h"].get("trend"),
        "4h_trend":t["4h"].get("trend"),
        "1h_close":t["1h"].get("close"),
        "1h_ema21":t["1h"].get("ema21"),
        "4h_close":t["4h"].get("close"),
        "4h_ema21":t["4h"].get("ema21"),
        "15m_rsi14":t["15m"].get("rsi14"),
        "1h_rsi14":t["1h"].get("rsi14"),
        "4h_rsi14":t["4h"].get("rsi14"),
        "ret3_pct":{
            "5m":t["5m"].get("ret3_pct"),
            "15m":t["15m"].get("ret3_pct"),
            "1h":t["1h"].get("ret3_pct"),
            "4h":t["4h"].get("ret3_pct")
        },
        "15m_close_time":(t["15m"].get("bar") or {}).get("close_time")
    }
    return out


EPISODE_RESET_GAP_MS = 15 * 60 * 1000

def episode_step(active,cand,bar_close_time,ts_ms):
    """V1.6.2 persisted episode lock.

    One continuous candidate episode may call AI only once. A same-side/same-kind
    candidate stays locked even when its 15m candle fingerprint changes.
    The lock is released only after the candidate has been absent for at least
    one full 15-minute cooldown and the 15m bar has advanced.
    """
    bar=int(bar_close_time or 0)
    ts=int(ts_ms)

    if cand is None:
        if not isinstance(active,dict) or not active.get("key"):
            return "EMPTY",None
        st=dict(active)
        if st.get("absence_started_ms") is None:
            st["absence_started_ms"]=ts
            st["absence_started_bar"]=bar
            return "HOLD",st
        gap=ts-int(st.get("absence_started_ms") or ts)
        absence_bar=int(st.get("absence_started_bar") or 0)
        if gap>=EPISODE_RESET_GAP_MS and bar!=absence_bar:
            return "RELEASE",None
        return "HOLD",st

    key=f"{cand.kind}:{cand.side or 'NONE'}"
    # Only an explicitly identified NEW structural SHORT setup may re-arm
    # AI inside a continuous downtrend. Legacy BUY/SHORT keys stay frozen.
    setup_key=getattr(cand,"setup_key",None)
    structural=(
        cand.kind=="ENTRY" and cand.side=="SHORT" and
        isinstance(setup_key,str) and setup_key.startswith("SHORT_BREAK:") and
        setup_key[len("SHORT_BREAK:"):].isdigit()
    )
    if structural:
        key=key+":"+setup_key
    elif (isinstance(active,dict) and cand.kind=="ENTRY" and
          cand.side=="SHORT" and
          str(active.get("key","")).startswith("ENTRY:SHORT:SHORT_BREAK:")):
        # Fall back to legacy short eligibility without treating the same
        # structural setup as a new AI request on the next candle.
        key=str(active["key"])
    if isinstance(active,dict) and active.get("key")==key:
        st=dict(active)
        st["last_seen_ms"]=ts
        st["last_seen_bar"]=bar
        st["last_reason"]=cand.reason
        st["absence_started_ms"]=None
        st["absence_started_bar"]=None
        return "SUPPRESS",st

    return "OPEN",{
        "key":key,
        "kind":cand.kind,
        "side":cand.side,
        "opened_ms":ts,
        "opened_bar":bar,
        "last_seen_ms":ts,
        "last_seen_bar":bar,
        "last_reason":cand.reason,
        "absence_started_ms":None,
        "absence_started_bar":None,
    }
