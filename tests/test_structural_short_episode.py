"""Future structural short episode scaffold: never changes legacy BUY behavior."""
from agent.candidate import Candidate, episode_step


def test_legacy_same_side_short_episode_is_still_suppressed():
    first=Candidate('ENTRY','SHORT','MTF_TREND_MOMENTUM','ENTRY:SHORT:100')
    _,ep=episode_step(None,first,100,1_000_000)
    later=Candidate('ENTRY','SHORT','MTF_TREND_MOMENTUM','ENTRY:SHORT:200')
    action,ep2=episode_step(ep,later,200,1_900_000)
    assert action=='SUPPRESS' and ep2['key']=='ENTRY:SHORT'


def test_structural_short_arms_only_once_for_each_breakout():
    old=Candidate('ENTRY','SHORT','MTF_TREND_MOMENTUM','ENTRY:SHORT:100')
    _,ep=episode_step(None,old,100,1_000_000)
    br=Candidate('ENTRY','SHORT','BREAKDOWN_RETEST','ENTRY:SHORT:200',
                 setup_key='SHORT_BREAK:200')
    action,ep=episode_step(ep,br,200,1_900_000)
    assert action=='OPEN' and ep['key']=='ENTRY:SHORT:SHORT_BREAK:200'
    repeated=Candidate('ENTRY','SHORT','BREAKDOWN_RETEST','ENTRY:SHORT:300',
                       setup_key='SHORT_BREAK:200')
    action,ep=episode_step(ep,repeated,300,2_800_000)
    assert action=='SUPPRESS'
    assert ep['key']=='ENTRY:SHORT:SHORT_BREAK:200'
    fresh=Candidate('ENTRY','SHORT','BREAKDOWN_RETEST','ENTRY:SHORT:400',
                    setup_key='SHORT_BREAK:400')
    action,ep=episode_step(ep,fresh,400,3_700_000)
    assert action=='OPEN'
    assert ep['key']=='ENTRY:SHORT:SHORT_BREAK:400'


def test_plain_short_followup_does_not_rearm_after_structural_setup():
    br=Candidate('ENTRY','SHORT','BREAKDOWN_RETEST','fp',setup_key='SHORT_BREAK:200')
    _,ep=episode_step(None,br,200,1_000_000)
    legacy=Candidate('ENTRY','SHORT','MTF_TREND_MOMENTUM','new-bar')
    action,ep=episode_step(ep,legacy,300,1_900_000)
    assert action=='SUPPRESS'
    assert ep['key']=='ENTRY:SHORT:SHORT_BREAK:200'


def test_existing_buy_episodes_ignore_setup_ids():
    b1=Candidate('ENTRY','LONG','MTF_TREND_MOMENTUM','long-100',setup_key='SHORT_BREAK:200')
    _,ep=episode_step(None,b1,100,1_000_000)
    b2=Candidate('ENTRY','LONG','MTF_TREND_MOMENTUM','long-200',setup_key='SHORT_BREAK:400')
    action,ep=episode_step(ep,b2,200,1_900_000)
    assert action=='SUPPRESS'
    assert ep['key']=='ENTRY:LONG'


def test_malformed_structural_setup_id_cannot_force_new_episode():
    original=Candidate('ENTRY','SHORT','MTF_TREND_MOMENTUM','short-100')
    _,ep=episode_step(None,original,100,1_000_000)
    not_struct=Candidate('ENTRY','SHORT','BREAKDOWN_RETEST','short-200',
                         setup_key='SHORT_BREAK:invalid')
    action,ep=episode_step(ep,not_struct,200,1_900_000)
    assert action=='SUPPRESS' and ep['key']=='ENTRY:SHORT'
