import json,requests,time
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

SYS="""You are the final veto/confirmation layer of a TEST/SHADOW crypto agent.
Do not explain your reasoning in prose. Immediately call submit_trade_decision exactly once.

Rules:
- ENTRY: choose candidate.side or HOLD only; never reverse.
- POSITION_REVIEW: choose HOLD or CLOSE only.
- Prefer HOLD when evidence is mixed.
- Use only supplied data.
- LONG/SHORT: confidence 1-100, SL/TP positive, stop normally 0.4-4.0%, RR >=1.5.
- HOLD/CLOSE: confidence 0 and null SL/TP.
- horizon_hours 1-168.
Never place orders yourself."""

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

    def _body(self,user,retry=False):
        return {
            "model":self.model,
            "temperature":0.05,
            "max_tokens":520 if retry else 620,
            "reasoning":{"max_tokens":64 if retry else 128,"exclude":True},
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


    def smoke(self):
        """Read-only OpenRouter/tool-contract smoke test. Never reaches risk or execution."""
        user=json.dumps({
            "smoke_test":True,
            "instruction":"Connectivity/contract test only. Return HOLD with confidence 0, null stop_loss_pct, null take_profit_pct, a short thesis, invalidation='N/A', horizon_hours=1. Do not infer or propose any trade.",
            "candidate":{"kind":"ENTRY","side":"LONG","reason":"SMOKE_ONLY","fingerprint":"SMOKE_ONLY"},
            "market":{"coin":"BTC","smoke_only":True},
            "virtual_position":None,
            "risk":{"smoke_only":True}
        },separators=(",",":"))
        r=None
        raw=""
        started=time.perf_counter()
        try:
            body=self._body(user)
            r=self.s.post(
                self.base+"/chat/completions",
                headers={"Authorization":f"Bearer {self.key}","Content-Type":"application/json"},
                json=body,timeout=45
            )
            status=int(getattr(r,"status_code",0) or 0)
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
            if d.action!="HOLD":
                raise ValueError("smoke test must return HOLD")
            return d,{
                "ok":True,
                "http_status":status,
                "latency_ms":round((time.perf_counter()-started)*1000),
                "model":data.get("model"),
                "provider":data.get("provider"),
                "usage":data.get("usage"),
                "finish_reason":choice.get("finish_reason"),
                "native_finish_reason":choice.get("native_finish_reason"),
                "tool_call":"submit_trade_decision",
                "smoke_only":True
            }
        except Exception as e:
            if r is not None:
                try: raw=r.text[:1600]
                except Exception: pass
            return Decision(
                action="HOLD",confidence=0,stop_loss_pct=None,take_profit_pct=None,
                thesis=f"AI smoke fail-safe: {type(e).__name__}",
                invalidation="N/A",horizon_hours=1
            ),{
                "ok":False,
                "http_status":int(getattr(r,"status_code",0) or 0) if r is not None else None,
                "latency_ms":round((time.perf_counter()-started)*1000),
                "error":repr(e),
                "response":raw,
                "model_requested":self.model,
                "smoke_only":True
            }
