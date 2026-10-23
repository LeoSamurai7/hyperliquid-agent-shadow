import sqlite3,json,time
from pathlib import Path

class Store:
    def __init__(self,d,e):
        p=Path(d)
        try:p.mkdir(parents=True,exist_ok=True)
        except:p=Path("./data");p.mkdir(exist_ok=True)
        self.path=p/"shadow.db";self.init(e)

    def conn(self):
        c=sqlite3.connect(self.path,timeout=20)
        c.row_factory=sqlite3.Row
        return c

    def init(self,e):
        with self.conn() as c:
            c.executescript("""CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY,v TEXT);
            CREATE TABLE IF NOT EXISTS decisions(
              id INTEGER PRIMARY KEY,ts_ms INTEGER,action TEXT,confidence INTEGER,
              approved INTEGER,gate_reason TEXT,payload TEXT);
            CREATE TABLE IF NOT EXISTS trades(
              id INTEGER PRIMARY KEY,side TEXT,entry_ts INTEGER,exit_ts INTEGER,
              entry_price REAL,exit_price REAL,qty REAL,notional REAL,stop_price REAL,tp_price REAL,
              entry_fee REAL,exit_fee REAL,pnl REAL,r_multiple REAL,status TEXT,exit_reason TEXT,
              thesis TEXT,invalidation TEXT);
            CREATE TABLE IF NOT EXISTS system_events(
              id INTEGER PRIMARY KEY,ts_ms INTEGER,event_type TEXT,severity TEXT,payload TEXT);""")
            if not c.execute("SELECT 1 FROM kv WHERE k='equity'").fetchone():
                c.execute("INSERT INTO kv VALUES('equity',?)",(str(e),))

    def equity(self):
        with self.conn() as c:return float(c.execute("SELECT v FROM kv WHERE k='equity'").fetchone()["v"])

    def seteq(self,x):
        with self.conn() as c:
            c.execute("INSERT INTO kv VALUES('equity',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",(str(float(x)),))

    def setkv(self,k,v):
        with self.conn() as c:
            c.execute("INSERT INTO kv VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",(k,json.dumps(v)))

    def getkv(self,k,d=None):
        with self.conn() as c:r=c.execute("SELECT v FROM kv WHERE k=?",(k,)).fetchone()
        if not r:return d
        try:return json.loads(r["v"])
        except:return r["v"]

    def position(self):
        with self.conn() as c:r=c.execute("SELECT * FROM trades WHERE status='OPEN' ORDER BY id DESC LIMIT 1").fetchone()
        return dict(r) if r else None

    def recent(self,n=10):
        with self.conn() as c:r=c.execute("SELECT * FROM trades WHERE status='CLOSED' ORDER BY id DESC LIMIT ?",(n,)).fetchall()
        return [dict(x) for x in reversed(r)]

    def trades(self,n=100):
        with self.conn() as c:r=c.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?",(n,)).fetchall()
        return [dict(x) for x in r]

    def stats(self):
        st=int((time.time()-time.time()%86400)*1000)
        with self.conn() as c:
            r=c.execute("SELECT COALESCE(SUM(pnl),0) p,COUNT(*) n FROM trades WHERE status='CLOSED' AND exit_ts>=?",(st,)).fetchone()
            o=c.execute("SELECT COUNT(*) n FROM trades WHERE entry_ts>=?",(st,)).fetchone()
        return {"daily_pnl":float(r["p"] or 0),"closed_today":int(r["n"]),"trades_today":int(o["n"])}

    def decision(self,ts,d,ok,reason,payload):
        with self.conn() as c:
            c.execute("INSERT INTO decisions VALUES(NULL,?,?,?,?,?,?)",
                      (ts,d.action,d.confidence,int(ok),reason,json.dumps(payload)))

    def decisions(self,n=50,include_invalid=False):
        # Fetch extra rows because historical API failures were once stored as HOLD decisions.
        fetch_n=min(max(n*10,n),2000)
        with self.conn() as c:
            rows=c.execute("SELECT * FROM decisions ORDER BY id DESC LIMIT ?",(fetch_n,)).fetchall()
        out=[]
        for row in rows:
            item=dict(row)
            if include_invalid:
                out.append(item)
            else:
                try:
                    p=json.loads(item.get("payload") or "{}")
                    if p.get("meta",{}).get("ok") is True:
                        out.append(item)
                except Exception:
                    pass
            if len(out)>=n:break
        return out

    def event(self,ts,event_type,payload,severity="WARN"):
        with self.conn() as c:
            c.execute("INSERT INTO system_events VALUES(NULL,?,?,?,?)",
                      (ts,event_type,severity,json.dumps(payload)))

    def events(self,n=100):
        with self.conn() as c:
            rows=c.execute("SELECT * FROM system_events ORDER BY id DESC LIMIT ?",(n,)).fetchall()
        return [dict(x) for x in rows]

    def open_trade(self,side,ts,entry,qty,notional,stop,tp,fee,d):
        with self.conn() as c:
            c.execute("""INSERT INTO trades(side,entry_ts,entry_price,qty,notional,stop_price,tp_price,entry_fee,pnl,status,thesis,invalidation)
            VALUES(?,?,?,?,?,?,?,?,0,'OPEN',?,?)""",(side,ts,entry,qty,notional,stop,tp,fee,d.thesis,d.invalidation))

    def close_trade(self,id,ts,exitp,fee,pnl,r,reason):
        with self.conn() as c:
            c.execute("""UPDATE trades SET exit_ts=?,exit_price=?,exit_fee=?,pnl=?,r_multiple=?,status='CLOSED',exit_reason=? WHERE id=?""",
                      (ts,exitp,fee,pnl,r,reason,id))
