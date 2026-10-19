
def ef(side,p,bps):
    s=bps/10000;return p*(1+s) if side=="LONG" else p*(1-s)
def xf(side,p,bps):
    s=bps/10000;return p*(1-s) if side=="LONG" else p*(1+s)
def openv(st,side,mark,g,d,c,ts):
    fill=ef(side,mark,c.slippage_bps);fee=g.qty*fill*c.fee_bps/10000;st.seteq(st.equity()-fee)
    sl=d.stop_loss_pct/100;tp=d.take_profit_pct/100
    stop=fill*(1-sl) if side=="LONG" else fill*(1+sl);target=fill*(1+tp) if side=="LONG" else fill*(1-tp)
    st.open_trade(side,ts,fill,g.qty,g.qty*fill,stop,target,fee,d)
def closev(st,p,raw,c,ts,reason):
    fill=xf(p["side"],raw,c.slippage_bps);fee=p["qty"]*fill*c.fee_bps/10000
    gross=p["qty"]*(fill-p["entry_price"]) if p["side"]=="LONG" else p["qty"]*(p["entry_price"]-fill)
    risk=p["qty"]*abs(p["entry_price"]-p["stop_price"]);pnl=gross-p["entry_fee"]-fee
    st.seteq(st.equity()+gross-fee);st.close_trade(p["id"],ts,fill,fee,pnl,pnl/risk if risk>0 else None,reason);return pnl
def stops(st,p,bar,c):
    h=float(bar["high"]);l=float(bar["low"]);ts=int(bar["close_time"])
    if p["side"]=="LONG":
        if l<=p["stop_price"]:return closev(st,p,p["stop_price"],c,ts,"STOP")
        if h>=p["tp_price"]:return closev(st,p,p["tp_price"],c,ts,"TAKE_PROFIT")
    else:
        if h>=p["stop_price"]:return closev(st,p,p["stop_price"],c,ts,"STOP")
        if l<=p["tp_price"]:return closev(st,p,p["tp_price"],c,ts,"TAKE_PROFIT")
