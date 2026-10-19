
from dataclasses import dataclass
@dataclass
class Gate:
    ok:bool; reason:str; qty:float=0; notional:float=0
def entry_gate(d,price,equity,daily_pnl,trades_today,c):
    if c.kill:return Gate(False,"KILL_SWITCH")
    if d.confidence<c.min_conf:return Gate(False,"CONFIDENCE")
    if trades_today>=c.max_trades_day:return Gate(False,"MAX_TRADES_DAY")
    if daily_pnl<=-equity*c.daily_loss_pct/100:return Gate(False,"DAILY_LOSS")
    if d.stop_loss_pct is None or d.take_profit_pct is None:return Gate(False,"MISSING_SL_TP")
    if not c.min_stop_pct<=d.stop_loss_pct<=c.max_stop_pct:return Gate(False,"STOP_RANGE")
    if d.take_profit_pct/d.stop_loss_pct<c.min_rr:return Gate(False,"RR")
    risk=equity*c.risk_pct/100; qty=risk/(price*d.stop_loss_pct/100)
    notional=min(qty*price,equity*c.max_notional_pct/100); qty=notional/price
    if notional<10:return Gate(False,"MIN_NOTIONAL")
    return Gate(True,"APPROVED",qty,notional)
