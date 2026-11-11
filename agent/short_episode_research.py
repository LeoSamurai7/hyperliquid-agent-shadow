"""Research-only structural episode gate. Never wired into production."""
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class EpisodeEvent:
    side: str
    kind: str
    setup_key: Optional[str] = None

def step(active, event):
    """Return (action, state); stable identity across repeated polling."""
    if event is None:
        return ('HOLD' if active else 'EMPTY'), active
    base = f'{event.kind}:{event.side}'
    structural = event.kind == 'ENTRY' and event.side == 'SHORT' and isinstance(event.setup_key, str) and (
        event.setup_key.startswith('SHORT:BREAKDOWN_RETEST:') or event.setup_key.startswith('SHORT:LIQUIDITY_SWEEP:'))
    if structural:
        suffix = event.setup_key.rsplit(':', 1)[-1]
        structural = suffix.isdigit() and int(suffix) > 0
    if structural:
        key = f'{base}:{event.setup_key}'
    elif event.kind == 'ENTRY' and event.side == 'SHORT' and active and active.startswith('ENTRY:SHORT:SHORT:'):
        key = active
    else:
        key = base
    return ('SUPPRESS', active) if active == key else ('OPEN', key)
