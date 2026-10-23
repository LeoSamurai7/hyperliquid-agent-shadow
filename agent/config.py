
import os
from dataclasses import dataclass
def b(n,d): return os.getenv(n,str(d)).strip().lower() in {"1","true","yes","on"}
def f(n,d):
    try:return float(os.getenv(n,str(d)))
    except:return d
def i(n,d):
    try:return int(os.getenv(n,str(d)))
    except:return d
@dataclass(frozen=True)
class Config:
    api_key:str; base_url:str; model:str; shadow:bool; execution:bool; network:str; symbol:str
    equity:float; risk_pct:float; daily_loss_pct:float; max_notional_pct:float
    min_conf:int; max_trades_day:int; min_stop_pct:float; max_stop_pct:float; min_rr:float
    fee_bps:float; slippage_bps:float; loop_seconds:int; ai_minutes:int; data_dir:str; kill:bool
def load():
    c=Config(
      os.getenv("OPENROUTER_API_KEY","").strip(),
      os.getenv("OPENROUTER_BASE_URL","https://openrouter.ai/api/v1").rstrip("/"),
      os.getenv("OPENROUTER_MODEL","qwen/qwen3.8-27b:free").strip(),
      b("SHADOW_MODE",True),b("EXECUTION_ENABLED",False),
      os.getenv("HL_DATA_NETWORK","mainnet").strip().lower(),
      os.getenv("SYMBOLS","BTC").split(",")[0].strip().upper(),
      f("STARTING_EQUITY_USD",1000),f("RISK_PER_TRADE_PCT",0.25),f("MAX_DAILY_LOSS_PCT",1.5),
      f("MAX_NOTIONAL_PCT",100),i("MIN_CONFIDENCE",75),i("MAX_TRADES_PER_DAY",6),
      f("MIN_STOP_PCT",0.4),f("MAX_STOP_PCT",4.0),f("MIN_RR",1.5),
      f("FEE_BPS_PER_SIDE",4.5),f("SLIPPAGE_BPS_PER_SIDE",1.0),
      i("MARKET_LOOP_SECONDS",300),i("AI_EVAL_INTERVAL_MINUTES",60),
      os.getenv("DATA_DIR","/data"),b("KILL_SWITCH",False))
    if not c.shadow: raise RuntimeError("SHADOW_MODE must be true")
    if c.execution: raise RuntimeError("HARD LOCK: EXECUTION_ENABLED must be false")
    allowed_paid_models={"nvidia/nemotron-3.5-lightning"}
    if not (c.model.endswith(":free") or c.model=="openrouter/free" or c.model in allowed_paid_models):
        raise RuntimeError("MODEL LOCK: only :free models, openrouter/free, or explicitly approved paid models are allowed")
    if c.network!="mainnet": raise RuntimeError("V1 uses Hyperliquid mainnet PUBLIC DATA only")
    if not c.api_key: raise RuntimeError("OPENROUTER_API_KEY missing")
    return c
