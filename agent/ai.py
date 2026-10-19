
import json,re,requests
from pydantic import BaseModel,Field
from typing import Literal
class Decision(BaseModel):
    action:Literal["LONG","SHORT","HOLD","CLOSE"]; confidence:int=Field(ge=0,le=100)
    stop_loss_pct:float|None=None; take_profit_pct:float|None=None
    thesis:str=Field(min_length=1,max_length=600); invalidation:str=Field(min_length=1,max_length=400)
    horizon_hours:int=Field(default=24,ge=1,le=168)
SYS="""You are the senior decision layer of a LIVE SHADOW crypto trading agent. You never place orders.
Choose exactly LONG, SHORT, HOLD, or CLOSE. If a position is open, only HOLD/CLOSE. If none, only LONG/SHORT/HOLD.
Prefer HOLD when evidence is mixed. Use only supplied data. Entry needs multi-timeframe support.
For LONG/SHORT propose stop_loss_pct normally 0.4-4.0 and take_profit_pct with reward/risk >=1.5.
Return JSON only with keys: action, confidence, stop_loss_pct, take_profit_pct, thesis, invalidation, horizon_hours."""
def parse(s):
    try:return json.loads(s)
    except:
        m=re.search(r"\{.*\}",s,re.S)
        if not m:raise ValueError("no json")
        return json.loads(m.group(0))
class Trader:
    def __init__(self,key,base,model):self.key=key;self.base=base;self.model=model;self.s=requests.Session()
    def decide(self,snap,pos,risk,recent):
        user=json.dumps({"market":snap,"virtual_position":pos,"risk":risk,"recent_closed":recent[-5:]},separators=(",",":"))
        schema={"type":"object","properties":{
              "action":{"type":"string","enum":["LONG","SHORT","HOLD","CLOSE"]},
              "confidence":{"type":"integer","description":"Integer from 0 to 100"},
              "stop_loss_pct":{"type":["number","null"]},
              "take_profit_pct":{"type":["number","null"]},
              "thesis":{"type":"string"},
              "invalidation":{"type":"string"},
              "horizon_hours":{"type":"integer","description":"Integer from 1 to 168"}},
              "required":["action","confidence","stop_loss_pct","take_profit_pct","thesis","invalidation","horizon_hours"],
              "additionalProperties":False}
        body={"model":self.model,"temperature":0.15,"max_tokens":700,
              "provider":{"require_parameters":True},
              "response_format":{"type":"json_schema","json_schema":{"name":"trade_decision","strict":True,"schema":schema}},
              "messages":[{"role":"system","content":SYS},{"role":"user","content":user}]}
        err=None
        for _ in range(2):
            try:
                r=self.s.post(self.base+"/chat/completions",headers={"Authorization":f"Bearer {self.key}","Content-Type":"application/json"},
                              json=body,timeout=45);r.raise_for_status();d=r.json()
                txt=d["choices"][0]["message"].get("content") or ""
                return Decision.model_validate(parse(txt)),{"ok":True,"model":d.get("model"),"usage":d.get("usage"),"raw":txt}
            except Exception as e:
                err=e
                try:
                    last_text=r.text[:1200]
                except Exception:
                    last_text=""

        return Decision(action="HOLD",confidence=0,thesis=f"AI fail-safe: {type(err).__name__}",
                        invalidation="No valid AI decision",horizon_hours=1),{"ok":False,"error":repr(err),"response":locals().get("last_text","")}
