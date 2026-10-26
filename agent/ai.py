import json,re,requests
from pydantic import BaseModel,Field,model_validator
from typing import Literal

class Decision(BaseModel):
    action:Literal["LONG","SHORT","HOLD","CLOSE"]
    confidence:int=Field(ge=0,le=100)
    stop_loss_pct:float|None=None
    take_profit_pct:float|None=None
    thesis:str=Field(min_length=1,max_length=600)
    invalidation:str=Field(min_length=1,max_length=400)
    horizon_hours:int=Field(default=24,ge=1,le=168)

    @model_validator(mode="after")
    def contract(self):
        if self.action in {"LONG","SHORT"}:
            if self.confidence < 1:
                raise ValueError("LONG/SHORT require confidence >= 1")
            if self.stop_loss_pct is None or self.take_profit_pct is None:
                raise ValueError("LONG/SHORT require stop_loss_pct and take_profit_pct")
            if self.stop_loss_pct <= 0 or self.take_profit_pct <= 0:
                raise ValueError("LONG/SHORT require positive stop_loss_pct and take_profit_pct")
        if self.action=="HOLD" and self.confidence != 0:
            raise ValueError("HOLD must use confidence 0")
        return self

SYS="""You are the senior decision layer of a LIVE SHADOW crypto trading agent. You never place orders.
Choose exactly LONG, SHORT, HOLD, or CLOSE. If a position is open, only HOLD/CLOSE. If none, only LONG/SHORT/HOLD.
Prefer HOLD when evidence is mixed. Use only supplied data. Entry needs multi-timeframe support.

OUTPUT CONTRACT:
- HOLD: confidence MUST be 0; stop_loss_pct and take_profit_pct MUST be null.
- LONG/SHORT: confidence MUST be an integer 1-100; stop_loss_pct and take_profit_pct MUST be positive numbers.
- LONG/SHORT stop_loss_pct should normally be 0.4-4.0 and take_profit_pct must target reward/risk >=1.5.
- horizon_hours MUST be an integer from 1 to 168. Never output 0.
- Return JSON only. No markdown, no prose outside JSON.
Keys exactly: action, confidence, stop_loss_pct, take_profit_pct, thesis, invalidation, horizon_hours."""

def parse(s):
    if not isinstance(s,str) or not s.strip():
        raise ValueError("no json")
    try:
        return json.loads(s)
    except Exception:
        m=re.search(r"\{.*\}",s,re.S)
        if not m:
            raise ValueError("no json")
        return json.loads(m.group(0))

class Trader:
    def __init__(self,key,base,model):
        self.key=key
        self.base=base
        self.model=model
        self.s=requests.Session()

    def _body(self,user,repair=False):
        schema={"type":"object","properties":{
              "action":{"type":"string","enum":["LONG","SHORT","HOLD","CLOSE"]},
              "confidence":{"type":"integer","minimum":0,"maximum":100},
              "stop_loss_pct":{"anyOf":[{"type":"number","exclusiveMinimum":0},{"type":"null"}]},
              "take_profit_pct":{"anyOf":[{"type":"number","exclusiveMinimum":0},{"type":"null"}]},
              "thesis":{"type":"string","minLength":1,"maxLength":600},
              "invalidation":{"type":"string","minLength":1,"maxLength":400},
              "horizon_hours":{"type":"integer","minimum":1,"maximum":168}},
              "required":["action","confidence","stop_loss_pct","take_profit_pct","thesis","invalidation","horizon_hours"],
              "additionalProperties":False}
        msgs=[{"role":"system","content":SYS},{"role":"user","content":user}]
        if repair:
            msgs.append({"role":"system","content":"Your previous output was invalid. Re-emit ONLY one JSON object satisfying the schema and OUTPUT CONTRACT. Do not explain."})
        return {
            "model":self.model,
            "temperature":0.10,
            "max_tokens":1600,
            "reasoning":{"effort":"low"},
            "provider":{
                "require_parameters":True,
                "order":["DeepInfra","Phala","CoreWeave"],
                "allow_fallbacks":True
            },
            "response_format":{"type":"json_schema","json_schema":{"name":"trade_decision","strict":True,"schema":schema}},
            "messages":msgs
        }

    def decide(self,snap,pos,risk,recent):
        user=json.dumps({"market":snap,"virtual_position":pos,"risk":risk,"recent_closed":recent[-5:]},separators=(",",":"))
        last_text=""
        last_meta={}
        last_err=None
        for attempt in range(2):
            r=None
            try:
                body=self._body(user,repair=attempt==1)
                r=self.s.post(
                    self.base+"/chat/completions",
                    headers={"Authorization":f"Bearer {self.key}","Content-Type":"application/json"},
                    json=body,timeout=60
                )
                r.raise_for_status()
                data=r.json()
                choice=data["choices"][0]
                msg=choice.get("message") or {}
                txt=msg.get("content") or ""
                last_text=txt
                last_meta={
                    "model":data.get("model"),
                    "provider":data.get("provider"),
                    "usage":data.get("usage"),
                    "finish_reason":choice.get("finish_reason"),
                    "native_finish_reason":choice.get("native_finish_reason"),
                    "raw":txt
                }
                if choice.get("finish_reason")=="length" and not txt.strip():
                    raise ValueError("empty content after length-limited completion")
                decision=Decision.model_validate(parse(txt))
                return decision,{"ok":True,**last_meta}
            except Exception as e:
                last_err=e
                if r is not None:
                    try:
                        last_text=r.text[:1600]
                    except Exception:
                        pass

        kind="AI_CONTRACT_ERROR" if isinstance(last_err,(ValueError,KeyError,TypeError)) or "validation error" in str(last_err).lower() else "AI_PROVIDER_ERROR"
        return Decision(
            action="HOLD",confidence=0,stop_loss_pct=None,take_profit_pct=None,
            thesis=f"AI fail-safe: {type(last_err).__name__}",
            invalidation="No valid AI decision",horizon_hours=1
        ),{"ok":False,"error_kind":kind,"error":repr(last_err),"response":last_text,"last_meta":last_meta}
