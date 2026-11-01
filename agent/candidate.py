from dataclasses import dataclass

@dataclass(frozen=True)
class Candidate:
    kind:str
    side:str|None
    reason:str
    fingerprint:str

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

    for side in ("LONG","SHORT"):
        ok,reason=_entry_side(snap,side)
        if ok:
            return Candidate("ENTRY",side,reason,f"ENTRY:{side}:{fpbar}")
    return None


def candidate_diagnostics(snap):
    t=snap["timeframes"]
    out={}
    for side in ("LONG","SHORT"):
        ok,reason=_entry_side(snap,side)
        out[side]={"eligible":bool(ok),"reason":reason}
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
