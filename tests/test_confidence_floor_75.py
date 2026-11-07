"""Explicit regression for agreed 75% AI entry gate (no exchange calls)."""
from agent.ai import Decision
from agent.config import load
from agent.risk import entry_gate


def test_default_confidence_gate_is_75(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'offline-test')
    monkeypatch.setenv('SHADOW_MODE','true')
    monkeypatch.setenv('EXECUTION_ENABLED','false')
    monkeypatch.setenv('HL_DATA_NETWORK','mainnet')
    monkeypatch.setenv('KILL_SWITCH','false')
    monkeypatch.delenv('MIN_CONFIDENCE',raising=False)
    c=load()
    assert c.min_conf==75
    below=Decision(action='SHORT',confidence=74,stop_loss_pct=1.0,
                   take_profit_pct=2.0,thesis='test',invalidation='x',horizon_hours=1)
    threshold=Decision(action='SHORT',confidence=75,stop_loss_pct=1.0,
                       take_profit_pct=2.0,thesis='test',invalidation='x',horizon_hours=1)
    low=entry_gate(below,100,1000,0,0,c)
    ok=entry_gate(threshold,100,1000,0,0,c)
    assert not low.ok and low.reason=='CONFIDENCE'
    assert ok.ok


def test_explicit_override_does_not_silently_change(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY','offline-test')
    monkeypatch.setenv('MIN_CONFIDENCE','80')
    monkeypatch.setenv('SHADOW_MODE','true')
    monkeypatch.setenv('EXECUTION_ENABLED','false')
    monkeypatch.setenv('HL_DATA_NETWORK','mainnet')
    assert load().min_conf==80
