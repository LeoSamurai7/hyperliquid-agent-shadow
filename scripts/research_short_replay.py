"""Causal, read-only historical probe for the SHORT breakdown/retest hypothesis.

No API keys, AI requests, signing, or orders. This is a research smoke test,
NOT a verified trading backtest and NOT evidence of profitability.

Usage: PYTHONPATH=. python scripts/research_short_replay.py --days 30
"""
import argparse
from bisect import bisect_right
from collections import Counter
from datetime import datetime, timezone
import json
import time
import requests

from agent.short_research import evaluate_short_break_retest

API = 'https://api.hyperliquid.xyz/info'
PERIOD_MS = {'15m': 900_000, '1h': 3_600_000, '4h': 14_400_000}


def fetch_closed_bars(session, tf, start_ms, end_ms):
    response = session.post(API, json={
        'type': 'candleSnapshot',
        'req': {'coin': 'BTC', 'interval': tf,
                'startTime': int(start_ms), 'endTime': int(end_ms)}}, timeout=30)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        raise ValueError('UNEXPECTED_CANDLE_RESPONSE')
    rows=[]
    for candle in data:
        close_time = int(candle['T'])
        if close_time > end_ms:
            continue
        rows.append({
            'open_time': int(candle['t']), 'close_time': close_time,
            'open': float(candle['o']), 'high': float(candle['h']),
            'low': float(candle['l']), 'close': float(candle['c']),
        })
    rows.sort(key=lambda r: r['close_time'])
    if len({x['close_time'] for x in rows}) != len(rows):
        raise ValueError(f'DUPLICATE_{tf}_BARS')
    if not rows:
        raise ValueError(f'NO_{tf}_BARS')
    if any(b['close_time']-a['close_time'] > 2*PERIOD_MS[tf]
           for a,b in zip(rows,rows[1:])):
        raise ValueError(f'MISSING_{tf}_CANDLE_GAP')
    return rows


def ema_context(rows):
    es={9:None,21:None,55:None}
    out=[]
    for i,bar in enumerate(rows):
        c=bar['close']
        for n in es:
            es[n]= c if es[n] is None else (2/(n+1))*c+(1-2/(n+1))*es[n]
        if i < 54:
            out.append(None)
            continue
        trend=('DOWN' if es[9]<es[21]<es[55] else
               'UP' if es[9]>es[21]>es[55] else 'MIXED')
        out.append({'close':c,'ema21':es[21],'trend':trend,'close_time':bar['close_time']})
    return out


def simulate_short(bars, signal_idx, signal, horizon=32, fee_bps=4.5, slip_bps=1.0):
    # Decision occurs only at close of signal_idx; fill no earlier than NEXT open.
    n=len(bars)
    if signal_idx+1 >= n:
        return None
    enter_idx=signal_idx+1
    raw_open=bars[enter_idx]['open']
    # Lower sell price is worse; higher buy-to-cover price is worse.
    entry=raw_open*(1-slip_bps/10000)
    stop=signal.stop_reference
    target=signal.target_reference
    if entry>=stop or entry<=target:
        return {'r':None,'exit_idx':enter_idx,'status':'GAP_OR_INVALID_FILL'}
    risk=stop-entry
    end_idx=min(n-1,signal_idx+horizon)
    reason='TIME'
    exit_price=bars[end_idx]['close']*(1+slip_bps/10000)
    exit_idx=end_idx
    for j in range(enter_idx,end_idx+1):
        bar=bars[j]
        # Conservative: if stop and TP hit on same candle, stop first.
        if bar['high']>=stop:
            exit_price=stop*(1+slip_bps/10000)
            exit_idx=j
            reason='STOP'
            break
        if bar['low']<=target:
            exit_price=target*(1+slip_bps/10000)
            exit_idx=j
            reason='TARGET'
            break
    fees=(entry+exit_price)*fee_bps/10000
    return {'r':round((entry-exit_price-fees)/risk,4),'exit_idx':exit_idx,'status':reason}


def summarize(trades):
    valid=[t['r'] for t in trades if t['r'] is not None]
    return {
        'trades':len(trades), 'priced_trades':len(valid),
        'wins':sum(x>0 for x in valid), 'losses':sum(x<=0 for x in valid),
        'net_r':round(sum(valid),3),
        'avg_r':round(sum(valid)/len(valid),3) if valid else None,
        'stops':sum(t['status']=='STOP' for t in trades),
        'targets':sum(t['status']=='TARGET' for t in trades),
        'time_exits':sum(t['status']=='TIME' for t in trades),
    }


def replay(m15,h1,h4,days=30):
    h1_ctx=ema_context(h1)
    h4_ctx=ema_context(h4)
    h1_times=[x['close_time'] for x in h1]
    h4_times=[x['close_time'] for x in h4]
    sample_start=m15[-1]['close_time']-days*24*3600*1000
    cutoff=int(sample_start+(m15[-1]['close_time']-sample_start)*0.70)
    trades=[]
    reason_count=Counter()
    seen_setup=set()
    busy_until=-1
    for i in range(80,len(m15)-33):
        ts=m15[i]['close_time']
        if ts < sample_start or i<=busy_until:
            continue
        h1i=bisect_right(h1_times,ts)-1
        h4i=bisect_right(h4_times,ts)-1
        if h1i < 0 or h4i < 0 or h1_ctx[h1i] is None or h4_ctx[h4i] is None:
            reason_count['HTF_WARMUP_MISSING']+=1
            continue
        result=evaluate_short_break_retest(m15[:i+1],h1_ctx[h1i],h4_ctx[h4i],ts)
        if not result.eligible:
            reason_count[result.reason]+=1
            continue
        if result.setup_id in seen_setup:
            reason_count['SAME_BREAKOUT_DEDUPED']+=1
            continue
        seen_setup.add(result.setup_id)
        sim=simulate_short(m15,i,result)
        if sim is None:
            continue
        trades.append({**sim,'signal_utc':datetime.fromtimestamp(ts/1000,timezone.utc).isoformat(),
                       'split':'OOS' if ts>=cutoff else 'DEVELOPMENT',
                       'setup_id':result.setup_id,
                       'reference_risk_pct':result.risk_pct})
        busy_until=sim['exit_idx']
    return {
        'research_only':True, 'execution_enabled':False,
        'dataset':{'m15_bars':len(m15),'h1_bars':len(h1),'h4_bars':len(h4),
                   'days_requested':days,'sample_cutoff_utc':datetime.fromtimestamp(cutoff/1000,timezone.utc).isoformat()},
        'development':summarize([t for t in trades if t['split']=='DEVELOPMENT']),
        'oos':summarize([t for t in trades if t['split']=='OOS']),
        'top_rejection_reasons':reason_count.most_common(12),
        'trades':trades,
        'limitations':'15m OHLC proxy fills; stop-first intrabar; fixed costs; no baseline parity, funding, outages, market impact, or independent final OOS. Not deployable.'
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--days',type=int,default=30)
    args=p.parse_args()
    if not 7 <= args.days <= 35:
        p.error('days must be between 7 and 35 (API 5000-bar cap)')
    end_ms=int(time.time()*1000)
    with requests.Session() as sess:
        # 45 days m15 < 5000 bars; longer 1h/4h history warms up EMA55.
        m15=fetch_closed_bars(sess,'15m',end_ms-45*86_400_000,end_ms)
        h1=fetch_closed_bars(sess,'1h',end_ms-70*86_400_000,end_ms)
        h4=fetch_closed_bars(sess,'4h',end_ms-120*86_400_000,end_ms)
    print(json.dumps(replay(m15,h1,h4,args.days),ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
