import json,requests
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
        if self.action=="HOLD":
            if self.confidence != 0:
                raise ValueError("HOLD must use confidence 0")
            if self.stop_loss_pct is not None or self.take_profit_pct is not None:
                raise ValueError("HOLD must use null SL/TP")
        if self.action=="CLOSE" and self.confidence != 0:
            raise ValueError("CLOSE uses confidence 0")
        return self

SYS="""You are the final decision layer of a crypto trading agent running in TEST/SHADOW mode.
A deterministic signal engine has already emitted a candidate. You are a veto/confirmation layer, not a signal generator.
Never place orders yourself.

Rules:
- If candidate.kind=ENTRY and there is no open position: choose candidate.side or HOLD only. Never reverse it.
- If candidate.kind=POSITION_REVIEW and a position is open: choose HOLD or CLOSE only.
- Prefer HOLD when evidence is mixed.
- Use only supplied market/risk/candidate data.
- LONG/SHORT require confidence 1-100, positive stop_loss_pct and take_profit_pct, normally stop 0.4-4.0%, reward/risk >=1.5.
- HOLD/CLOSE use confidence 0 and null stop/take-profit.
- horizon_hours must be 1-168.
Submit exactly one decision through the submit_trade_decision tool."""

SCHEMA={"type":"object","properties":{
    "action":{"type":"string","enum":["LONG","SHORT","HOLD","CLOSE"]},
    "confidence":{"type":"integer","minimum":0,"maximum":100},
    "stop_loss_pct":{"anyOf":[{"type":"number","exclusiveMinimum":0},{"type":"null"}]},
    "take_profit_pct":{"anyOf":[{"type":"number","exclusiveMinimum":0},{"type":"null"}]},
    "thesis":{"type":"string","minLength":1,"maxLength":600},
    "invalidation":{"type":"string","minLength":1,"maxLength":400},
    "horizon_hours":{"type":"integer","minimum":1,"maximum":168}},
    "required":["action","confidence","stop_loss_pct","take_profit_pct","thesis","invalidation","horizon_hours"],
    "additionalProperties":False}

class Trader:
    def __init__(self,key,base,model):
        self.key=key; self.base=base; self.model=model; self.s=requests.Session()

    def _body(self,user):
        return {
            "model":self.model,
            "temperature":0.10,
            "max_tokens":700,
            "reasoning":{"effort":"low"},
            "tools":[{
                "type":"function",
                "function":{
                    "name":"submit_trade_decision",
                    "description":"Return the single validated trading decision for the supplied candidate.",
                    "parameters":SCHEMA
                }
            }],
            "tool_choice":{"type":"function","function":{"name":"submit_trade_decision"}},
            "parallel_tool_calls":False,
            "messages":[{"role":"system","content":SYS},{"role":"user","content":user}]
        }

    def decide(self,snap,pos,risk,recent,candidate):
        user=json.dumps({
            "candidate":candidate,
            "market":snap,
            "virtual_position":pos,
            "risk":risk,
            "recent_closed":recent[-3:]
        },separators=(",",":"))
        r=None
        raw=""
        try:
            r=self.s.post(
                self.base+"/chat/completions",
                headers={"Authorization":f"Bearer {self.key}","Content-Type":"application/json"},
                json=self._body(user),timeout=60
            )
            r.raise_for_status()
            data=r.json()
            choice=data["choices"][0]
            msg=choice.get("message") or {}
            calls=msg.get("tool_calls") or []
            if not calls:
                raise ValueError("missing tool_call")
            fn=(calls[0].get("function") or {})
            if fn.get("name")!="submit_trade_decision":
                raise ValueError("wrong tool_call")
            args=fn.get("arguments")
            obj=json.loads(args) if isinstance(args,str) else args
            d=Decision.model_validate(obj)

            if candidate.get("kind")=="ENTRY" and d.action not in {candidate.get("side"),"HOLD"}:
                raise ValueError("candidate direction mismatch")
            if candidate.get("kind")=="POSITION_REVIEW" and d.action not in {"HOLD","CLOSE"}:
                raise ValueError("position review action mismatch")

            meta={
                "ok":True,
                "model":data.get("model"),
                "provider":data.get("provider"),
                "usage":data.get("usage"),
                "finish_reason":choice.get("finish_reason"),
                "native_finish_reason":choice.get("native_finish_reason"),
                "tool_call":"submit_trade_decision"
            }
            return d,meta
        except Exception as e:
            if r is not None:
                try: raw=r.text[:1600]
                except Exception: pass
            kind="AI_CONTRACT_ERROR" if isinstance(e,(ValueError,KeyError,TypeError,json.JSONDecodeError)) or "validation error" in str(e).lower() else "AI_PROVIDER_ERROR"
            return Decision(
                action="HOLD",confidence=0,stop_loss_pct=None,take_profit_pct=None,
                thesis=f"AI fail-safe: {type(e).__name__}",
                invalidation="No valid AI decision",horizon_hours=1
            ),{"ok":False,"error_kind":kind,"error":repr(e),"response":raw}
