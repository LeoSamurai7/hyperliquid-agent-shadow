
import time, requests, pandas as pd, numpy as np
HL="https://api.hyperliquid.xyz/info"
class Market:
    def __init__(self,coin="BTC"): self.coin=coin; self.s=requests.Session()
    def post(self,p):
        err=None
        for k in range(4):
            try:
                r=self.s.post(HL,json=p,timeout=20); r.raise_for_status(); return r.json()
            except Exception as e: err=e; time.sleep(.5*(k+1))
        raise RuntimeError(f"Hyperliquid request failed: {err!r}")
    def candles(self,tf,limit=220):
        mins={"5m":5,"15m":15,"1h":60,"4h":240}[tf]; now=int(time.time()*1000)
        d=self.post({"type":"candleSnapshot","req":{"coin":self.coin,"interval":tf,
                    "startTime":now-(limit+5)*mins*60000,"endTime":now}})
        x=pd.DataFrame(d).rename(columns={"t":"open_time","T":"close_time","o":"open","h":"high","l":"low","c":"close","v":"volume"})
        x=x[["open_time","close_time","open","high","low","close","volume"]]
        for c in x.columns:x[c]=pd.to_numeric(x[c],errors="coerce")
        return x.dropna().sort_values("open_time").drop_duplicates("open_time").query("close_time <= @now").tail(limit).reset_index(drop=True)
    def context(self):
        d=self.post({"type":"metaAndAssetCtxs"}); meta,ctx=d[0],d[1]
        idx=next((i for i,u in enumerate(meta.get("universe",[])) if u.get("name")==self.coin),None)
        if idx is None:return {}
        out={}
        for k in ["markPx","oraclePx","funding","openInterest","dayNtlVlm","prevDayPx"]:
            try:out[k]=float(ctx[idx][k])
            except:out[k]=None
        return out
def rsi(s,n=14):
    d=s.diff(); u=d.clip(lower=0); dn=-d.clip(upper=0)
    au=u.ewm(alpha=1/n,adjust=False,min_periods=n).mean(); ad=dn.ewm(alpha=1/n,adjust=False,min_periods=n).mean()
    return 100-(100/(1+au/ad.replace(0,np.nan)))
def feats(x):
    p=x.close.shift(1); tr=pd.concat([x.high-x.low,(x.high-p).abs(),(x.low-p).abs()],axis=1).max(axis=1)
    x=x.copy(); x["atr"]=tr.rolling(14).mean()
    for n in (9,21,55):x[f"e{n}"]=x.close.ewm(span=n,adjust=False,min_periods=n).mean()
    x["rsi"]=rsi(x.close); x["r1"]=x.close.pct_change(); x["r3"]=x.close.pct_change(3); x["r12"]=x.close.pct_change(12)
    x["vz"]=(x.volume-x.volume.rolling(30).mean())/x.volume.rolling(30).std().replace(0,np.nan)
    r=x.iloc[-1]; trend="UP" if r.e9>r.e21>r.e55 else ("DOWN" if r.e9<r.e21<r.e55 else "MIXED")
    val=lambda q: None if pd.isna(q) else float(q)
    return {"close":float(r.close),"ema9":val(r.e9),"ema21":val(r.e21),"ema55":val(r.e55),
            "atr_pct":val(r.atr/r.close*100),"rsi14":val(r.rsi),
            "ret1_pct":val(r.r1*100),"ret3_pct":val(r.r3*100),"ret12_pct":val(r.r12*100),
            "volume_z":val(r.vz),"trend":trend,
            "bar":{"open":float(r.open),"high":float(r.high),"low":float(r.low),"close":float(r.close),
                   "open_time":int(r.open_time),"close_time":int(r.close_time)}}
def snapshot(m):
    out={}; raw={}
    for tf in ("5m","15m","1h","4h"):
        raw[tf]=m.candles(tf); out[tf]=feats(raw[tf])
    ctx=m.context(); mark=ctx.get("markPx") or out["5m"]["close"]
    return {"coin":m.coin,"ts_ms":int(time.time()*1000),"mark_price":float(mark),"context":ctx,"timeframes":out},raw
