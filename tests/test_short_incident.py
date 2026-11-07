from scripts.research_short_incident import incident_diagnostics, to_ms


def test_incident_never_makes_trade_and_respects_window():
    b=[{'open':100,'close':100,'high':100.4,'low':99.6,'close_time':(i+1)*900000} for i in range(110)]
    h1=[{'close':100,'close_time':(i+1)*3600000} for i in range(70)]
    h4=[{'close':100,'close_time':(i+1)*14400000} for i in range(70)]
    z=incident_diagnostics(b,h1,h4,100*900000,106*900000)
    assert z['orders_sent']==0 and z['research_only']
    assert z['window']['bars_checked']==7
    assert all(100*900000 <= int(to_ms(x['utc'])) <= 106*900000 for x in z['observations'])
