"""Regression: AI veto rationale is persisted without changing execution behavior."""
import json
from types import SimpleNamespace

from agent.ai import Decision
from agent.candidate import Candidate
from agent.runtime import Runtime
from agent.store import Store


def test_ai_hold_veto_rationale_is_persisted_without_execution(tmp_path):
    st = Store(str(tmp_path), 1000.0)
    d = Decision(
        action="HOLD", confidence=0,
        stop_loss_pct=None, take_profit_pct=None,
        thesis="No clean risk-adjusted entry after breakdown",
        invalidation="Wait for a fresh entry setup", horizon_hours=1,
    )
    rt = Runtime.__new__(Runtime)
    rt.st = st
    rt.c = SimpleNamespace(ai_daily_limit=40, execution=False, model="free-test")
    rt.ai = SimpleNamespace(decide=lambda *args: (d, {"ok": True, "tool_call": "submit_trade_decision"}))
    rt.last_attempt = 0
    rt.last_success = 0
    rt.ai_err = None
    cand = Candidate("ENTRY", "SHORT", "MTF_TREND_MOMENTUM", "ENTRY:SHORT:test")
    rt._run_ai(
        snap={}, p=None,
        rs={"equity": 1000.0, "daily_pnl": 0.0, "trades_today": 0},
        ts=1793923200000, mark=75000.0, cand=cand,
    )
    row = st.decisions(1, include_invalid=True)[0]
    payload = json.loads(row["payload"])
    assert row["action"] == "HOLD"
    assert row["gate_reason"] == "AI_VETO_HOLD"
    assert row["approved"] == 0
    assert payload["candidate"]["side"] == "SHORT"
    assert payload["ai_decision"] == d.model_dump()
    assert st.execution_attempts() == []
    assert st.trades() == []
