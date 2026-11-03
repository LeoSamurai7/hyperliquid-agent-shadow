import json
from agent.config import load
from agent.store import Store
from agent.runtime import Runtime

def main():
    c=load()
    st=Store(c.data_dir,c.equity)
    rt=Runtime(c,st)
    rt.cycle()
    print(json.dumps({
        "runtime": rt.status(),
        "candidate": rt.candidate_status(),
        "risk": rt.risk(),
        "latest_execution": st.execution_latest(),
        "events": st.events(20),
    }, default=str))

if __name__=="__main__":
    main()
