"""Read-only causal diagnostics for a specified missed bearish trading window.

No secrets, AI requests, or orders. This tests the RESEARCH detector only;
it cannot reconstruct the old AI HOLD thesis (not historically stored).
"""
import argparse
from bisect import bisect_right
from collections import Counter
from datetime import datetime, timezone
import json
import time
import requests

from agent.short_research import evaluate_short_break_retest
from scripts.research_short_replay import fetch_closed_bars, ema_context


def to_ms(value):
    return int(datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()*1000)


def incident_diagnostics(m15,h1,h4,start_ms,end_ms):
    h1ctx=ema_context(h1);h4ctx=ema_context(h4)
    h1times=[x['close_time'] for x in h1]
    h4times=[x['close_time'] for x in h4]
    reasons=Counter()
    rows=[]
    for i in range(80,len(m15)):
        ts=m15[i]['close_time']
        if not start_ms<=ts<=end_ms:
            continue
        a=bisect_right(h1times,ts)-1
        b=bisect_right(h4times,ts)-1
        if a<0 or b<0 or h1ctx[a] is None or h4ctx[b] is None:
            reason='HTF_WARMUP_MISSING'; eligible=False; key=None
            h1trend=None;h4trend=None
        else:
            result=evaluate_short_break_retest(m15[:i+1],h1ctx[a],h4ctx[b],ts)
            reason=result.reason;eligible=result.eligible;key=result.setup_id
            h1trend=h1ctx[a]['trend'];h4trend=h4ctx[b]['trend']
        reasons[reason]+=1
        rows.append({'utc':datetime.fromtimestamp(ts/1000,timezone.utc).isoformat(),
                     'm15_close':m15[i]['close'],
                     'h1_trend':h1trend,'h4_trend':h4trend,
                     'eligible':eligible,'research_reason':reason,
                     'setup_id':key})
    return {
        'research_only':True,'orders_sent':0,
        'window':{'start_utc':datetime.fromtimestamp(start_ms/1000,timezone.utc).isoformat(),
                  'end_utc':datetime.fromtimestamp(end_ms/1000,timezone.utc).isoformat(),
                  'bars_checked':len(rows)},
        'reasons':dict(reasons),'observations':rows,
        'limits':'Research-only filter, NOT the historical OpenRouter veto. No archived AI rationale exists; no future bars used.'
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--start',default='2026-11-05T23:30:00Z')
    p.add_argument('--end',default='2026-11-06T09:00:00Z')
    args=p.parse_args()
    start_ms=to_ms(args.start);end_ms=to_ms(args.end)
    if end_ms<=start_ms or end_ms-start_ms>48*3600*1000:
        p.error('incident window must be positive and <=48 hours')
    now=int(time.time()*1000)
    with requests.Session() as sess:
        m15=fetch_closed_bars(sess,'15m',now-45*86_400_000,now)
        h1=fetch_closed_bars(sess,'1h',now-70*86_400_000,now)
        h4=fetch_closed_bars(sess,'4h',now-120*86_400_000,now)
    result=incident_diagnostics(m15,h1,h4,start_ms,end_ms)
    if not result['window']['bars_checked']:
        raise SystemExit('NO_BARS_IN_FOCUS_WINDOW')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
