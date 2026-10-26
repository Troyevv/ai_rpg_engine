from copy import deepcopy
import json
import pytest
from hypothesis import given, strategies as st
from test_calendar_v2 import state, snapshot, context
from backend.runtime_v3.player_calendar import player_calendar
from backend.runtime_v3.weather import weather_at
from backend.runtime_v3.models import WeatherProfile, ScheduledEvent, Fact, Knowledge
from backend.runtime_v3.selectors import ui_view


def weather_state():
    s=state()
    s['meta']['weather']=WeatherProfile(seed='test',regions={'home':{'climate':'temperate','hemisphere':'north'}}).model_dump()
    return s


def test_calendar_filters_before_events_markers_and_counts():
    s=state();s['characters']['sonya']['birth_date']='2000-10-09'
    s['scheduled_events']['secret']=ScheduledEvent(id='secret',description='Secret plan',character_ids=['sonya'],temporal={'date':'2026-10-09'}).model_dump()
    s['meta']['calendar']['profile']['observances']=[dict(id='private-anniversary',name='Hidden anniversary',month=10,day=9,character_ids=['sonya'])]
    from backend.runtime_v3.models import Observance
    Observance.model_validate(s['meta']['calendar']['profile']['observances'][0])
    before=deepcopy(s)
    assert not ui_view(snapshot(s))['world_clock']['calendar']['profile']['observances']
    view=player_calendar(s,'2026-10-01','2026-10-31')
    assert not view['events'] and not view['scheduled']['items']
    assert 'Secret plan' not in json.dumps(view)
    assert s==before
    for fid,subject,predicate in [('dob','sonya','birth_date'),('plan','secret','scheduled_event')]:
        s['facts'][fid]=Fact(id=fid,text='Learned',claim={'subject_id':subject,'predicate':predicate,'value':'known'}).model_dump()
        s['knowledge']['ilya:'+fid]=Knowledge(actor_id='ilya',fact_id=fid).model_dump()
    view=player_calendar(s,'2026-10-01','2026-10-31')
    assert len(view['events'])==len(view['scheduled']['items'])==1
    s['camera']['controlled_actor_id']=None
    view=player_calendar(s,'2026-10-01','2026-10-31')
    assert not view['events'] and not view['scheduled']['items']


def test_calendar_status_reschedule_and_cancellation_are_live():
    s=state();s['scheduled_events']['own']=ScheduledEvent(id='own',description='Meet',character_ids=['ilya'],commitment=True,temporal={'date':'2026-10-09'}).model_dump()
    def events():return player_calendar(s,'2026-10-01','2026-10-31')['scheduled']['items']
    assert events()[0]['date']=='2026-10-09'
    s['scheduled_events']['own']['temporal']['date']='2026-10-10'
    assert len(events())==1 and events()[0]['date']=='2026-10-10'
    s['scheduled_events']['own']['status']='cancelled'
    assert events()[0]['status']=='cancelled'


@given(st.integers(min_value=0,max_value=60_000_000))
def test_weather_is_bounded_deterministic_and_region_specific(minute):
    s=weather_state();s['meta']['world_time']=minute;before=deepcopy(s)
    assert weather_at(s)==weather_at(json.loads(json.dumps(s)))
    assert weather_at(s,'remote') is None
    assert weather_at(s,minute=minute+1440) is None
    assert s==before


def test_weather_same_in_ui_context_calendar_and_rollback():
    s=weather_state();before=deepcopy(s)
    view=ui_view(snapshot(s))
    assert view['scene_meta']['weather']==context(s)['weather']==weather_at(s)
    day=player_calendar(s,'2026-10-08','2026-10-08')['days'][0]
    assert day['weather']==weather_at(s)
    s['meta']['world_time']+=500_000
    assert weather_at(before)==weather_at(json.loads(json.dumps(before)))
    assert s['characters']==before['characters']
    s['meta']['weather']=None
    assert weather_at(s) is None


def test_weather_configuration_is_atomic_persistent_and_does_not_rewrite_history(tmp_path):
    from backend.api.app import create_app
    from fastapi.testclient import TestClient
    from devtools.narrative_test_world import load_fixture
    app=create_app(tmp_path/'weather.db');repo=app.state.repository
    sid=load_fixture(repo,'calendar-evening')['save']
    before=repo.get_snapshot(sid);revision=repo.get_save(sid)['revision']
    lid=before['world_state']['camera']['location_id']
    client=TestClient(app)
    body={'revision':revision,'profile':{'seed':'stable','regions':{lid:{'climate':'temperate','hemisphere':'north'}}}}
    result=client.put(f'/api/saves/{sid}/weather',json=body)
    assert result.status_code==200,result.text
    after=repo.get_snapshot(sid)
    assert after['world_state']['characters']==before['world_state']['characters']
    assert after['world_state']['meta']['world_time']==before['world_state']['meta']['world_time']
    assert after['world_state']['meta']['weather']['since_minute']==before['world_state']['meta']['world_time']
    from backend.repositories.preparation import Repository
    assert Repository(repo.path).get_snapshot(sid)==after
    assert weather_at(before['world_state']) is None
    day=player_calendar(after['world_state'],'2026-10-08','2026-10-08')['days'][0]
    assert day['weather']==result.json()['state']['scene_meta']['weather']
    assert client.put(f'/api/saves/{sid}/weather',json=body).status_code>=400
    assert repo.get_snapshot(sid)==after
