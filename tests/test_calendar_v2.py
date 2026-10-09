from copy import deepcopy
from datetime import date, timedelta
import json

import pytest
from hypothesis import given, strategies as st
from backend.runtime_v3.models import WorldStateV3, Calendar, ScheduledEvent, assert_world_state_v3_invariants
from backend.runtime_v3.calendar import (current_time, calendar_label, calendar_range, nearby_calendar,
    age_on, day_period, scheduled_time, ordinal, from_ordinal)
from backend.runtime_v3.context import build_context
from backend.runtime_v3.scope import RelevanceResolver, CharacterContextClassifier, ACTIVE_REFERENCED
from backend.runtime_v3.director import plan, background_candidate, interval_candidates
from backend.runtime_v3.time_skip import TimeSkipRequest, plan_skip
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.selectors import ui_view


def state(start='2026-10-08', clock=1242, weekday=3, profile=None):
    return WorldStateV3(meta=dict(world_time=clock,calendar=dict(start_minute=clock,start_weekday=weekday,start_date=start,profile=profile or {})),
        camera=dict(location_id='home',present_character_ids=['ilya'],controlled_actor_id='ilya'),
        locations={'home':dict(id='home',name='Дом'),'remote':dict(id='remote',name='Другое место')},
        characters={'ilya':dict(id='ilya',location_id='home'), 'sonya':dict(id='sonya',location_id='remote')}).model_dump()


def snapshot(s):
    return dict(schema_version=3,world_state=s,campaign={},character_cards=[dict(id=cid,name=cid,fields={}) for cid in s['characters']])


def context(s, extraction=False):
    messages=build_context(snapshot(s), [], '', 'turn', 32768, 2000, extraction_text='Пауза.' if extraction else None)
    return json.loads(next(m['content'].split('\n',1)[1] for m in messages if m['content'].startswith('Текущее состояние / GM-only\n')))


def test_same_canonical_time_ui_narrative_extraction_and_day_one():
    s=state()
    n=context(s); e=context(s,True); ui=ui_view(snapshot(s))
    assert n['current_time']==e['current_time']==ui['world_clock']['projection']
    assert n['current_time']['weekday_name']=='thursday'
    assert n['current_time']['time']=='20:42' and n['current_time']['day_period']=='evening'
    assert n['current_time']['day']==1 and '20:42' in ui['scene_meta']['time']
    assert 'calendar' not in n['meta']
    p=current_time(s,1440)
    assert (p['date'],p['day'],p['time'],p['weekday_name'])==('2026-10-09',2,'00:00','friday')


@pytest.mark.parametrize('start,result',[('2024-02-28','2024-02-29'),('2024-02-29','2024-03-01'),('2025-02-28','2025-03-01'),('2026-12-31','2027-01-01'),('2026-10-11','2026-10-12')])
def test_boundaries(start,result):
    s=state(start,1439)
    assert current_time(s,1440)['date']==result
    if start=='2026-10-11': assert current_time(s,1440)['weekday_name']=='monday'


@pytest.mark.parametrize('minute,period',[(0,'night'),(359,'night'),(360,'morning'),(719,'morning'),(720,'afternoon'),(1079,'afternoon'),(1080,'evening'),(1319,'evening'),(1320,'night'),(1439,'night')])
def test_period_boundaries(minute,period):
    assert day_period(minute)==period


def test_age_and_unknown_birthdays():
    assert age_on('2000-10-09','2026-10-08')==25
    assert age_on('2000-10-09','2026-10-09')==26
    assert age_on('2000-02-29','2025-02-28')==24
    assert age_on('2000-02-29','2025-03-01')==25
    assert age_on(None,'2026-10-08') is None
    assert age_on('2000-01-01',None) is None
    assert age_on('2027-01-01','2026-10-08') is None


def test_setting_observances_birthdays_bounded_read_only():
    s=state(profile=dict(id='fiction',observances=[dict(id=f'holiday{i}',name=f'Праздник {i}',month=10,day=8) for i in range(40)]))
    s['characters']['ilya']['birth_date']='2000-10-09'
    s['characters']['sonya']['birth_date']='2001-10-08'
    before=deepcopy(s)
    nearby=nearby_calendar(s,{'ilya'})
    assert len(nearby)==12
    full=calendar_range(s,'2026-10-01','2026-10-31')
    assert len(full['days'])==31 and full['days'][0]['weekday']==3
    assert len([e for e in full['events'] if e['kind']=='birthday'])==2
    assert s==before and not s['scheduled_events']
    assert calendar_range(s,'2026-10-01','2026-10-31')==full
    assert len(context(s)['calendar_context'])==12
    assert 'observances' not in json.dumps(context(s))
    with pytest.raises(ValueError): calendar_range(s,'2026-01-01','2028-01-01')


def test_custom_calendar_seasons_and_personal_anniversary():
    profile=dict(id='realm',system='custom',month_lengths=[20,25],month_names=['Свет','Тень'],
                 weekday_names=['А','Б','В','Г','Д'],seasons=[dict(name='Сухой сезон',month=1,day=1),dict(name='Дожди',month=2,day=1)],
                 observances=[dict(id='oath',name='Годовщина клятвы',month=2,day=1,character_ids=['ilya'])])
    s=state('0042-01-20',1439,4,profile)
    p=current_time(s,1440)
    assert (p['date'],p['weekday_name'],p['season'])==('0042-02-01','А','Дожди')
    assert calendar_range(s,'0042-01-20','0042-02-02')['events'][0]['kind']=='personal'
    assert current_time(s,1440*26)['date']=='0043-01-01'
    assert not current_time(state())['season']


@given(st.dates(min_value=date(1900,1,1),max_value=date(2200,1,1)),st.integers(0,10000))
def test_gregorian_projection_matches_stdlib(start,days):
    s=state(start.isoformat(),1242)
    p=current_time(s,1242+days*1440)
    assert p['date']==(start+timedelta(days=days)).isoformat()
    assert p['day']==days+1
    assert ordinal(from_ordinal(ordinal(start.isoformat(),{}),{}),{})==start.toordinal()


def test_thursday_friday_future_does_not_activate_sonya_or_background():
    s=state(clock=1257)
    event=ScheduledEvent(id='trip',description='Поездка на дачу',character_ids=['ilya','sonya'],due_minute=0,condition='В пятницу вечером').model_dump()
    s['scheduled_events']['trip']=event
    before=deepcopy(s)
    assert scheduled_time(s,event)==dict(status='future',due_minute=1440+1080)
    scope=RelevanceResolver().resolve(snapshot(s),'Поездка на дачу')
    assert 'trip' not in scope.acting_scheduled_event_ids
    assert CharacterContextClassifier().classify('sonya',scope)!=ACTIVE_REFERENCED
    assert 'sonya' not in plan(s,'turn',scope=scope)['acting_actor_ids']
    later=deepcopy(s);later['meta']['world_time']+=1
    assert background_candidate(s,later) is None
    assert not interval_candidates(s,later)[0]
    assert s==before
    s['meta']['world_time']=1440+1100
    assert scheduled_time(s,event)['status']=='due'
    assert event['status']=='pending'  # due is not happened


def test_unresolved_sentinel_and_structured_temporal_reference():
    s=state()
    assert scheduled_time(s,dict(due_minute=0,condition='Когда получится'))['status']=='unresolved'
    event=dict(due_minute=0,temporal=dict(day_offset=1,time='18:00'),time_reference_minute=1242)
    assert scheduled_time(s,event)['due_minute']==2520
    s['meta']['world_time']+=7*1440
    assert scheduled_time(s,event)['due_minute']==2520  # never moves on reads


def test_time_skip_interrupts_at_resolved_time_and_context_is_updated():
    s=state()
    s['scheduled_events']['trip']=ScheduledEvent(id='trip',description='Trip',character_ids=['ilya'],due_minute=0,
        condition='Friday evening',interrupts=True).model_dump()
    skip=plan_skip(s,TimeSkipRequest(1242,1242+2*1440))
    assert skip['actual_target']==2520 and skip['interrupted']
    s['meta']['world_time']=skip['actual_target']
    assert context(s)['current_time']['time']=='18:00'
    assert context(s)['current_time']['weekday_name']=='friday'


def test_birth_date_requires_explicit_evidence_and_cannot_rewrite_known_date():
    s=state(); text='Дата рождения Ильи 2000-10-09.'
    raw=dict(final_scene=dict(location_id='home',present_character_ids=['ilya']),
        character_changes=[dict(id='ilya',birth_date='2000-10-09',evidence=text)])
    result=StateResolver(s,text,'').resolve(raw)
    assert result.state['characters']['ilya']['birth_date']=='2000-10-09'
    bad=deepcopy(raw);bad['character_changes'][0]['birth_date']='2000-01-01'
    assert StateResolver(s,text,'').resolve(bad).state['characters']['ilya']['birth_date'] is None


def test_optional_malformed_dates_degrade_locally_without_rewriting_source():
    s=state();s['meta']['calendar']['start_date']='not-a-date'
    s['characters']['ilya']['birth_date']=42
    s['meta']['calendar']['profile']['observances']=[dict(id='valid',name='Valid',month=10,day=8),dict(id='invalid',name='Invalid',month=2,day=31)]
    original=deepcopy(s)
    value=assert_world_state_v3_invariants(s)
    assert current_time(value)['date'] is None
    assert value['characters']['ilya']['birth_date'] is None
    assert len(value['meta']['calendar']['profile']['observances'])==1
    assert s==original


def test_calendar_api_bounded_browsing_does_not_mutate_game(tmp_path):
    from fastapi.testclient import TestClient
    from backend.api.app import create_app
    from devtools.narrative_test_world import load_fixture
    app=create_app(tmp_path/'calendar.sqlite');repo=app.state.repository
    loaded=load_fixture(repo,'calendar-evening');sid=loaded['save']
    before=repo.get_snapshot(sid);revision=repo.get_save(sid)['revision']
    with TestClient(app) as client:
        current=client.get(f'/api/saves/{sid}/calendar').json()['current']
        assert current['date']=='2026-10-08' and current['time']=='20:42'
        future=client.get(f'/api/saves/{sid}/calendar?start_date=2027-10-01&end_date=2027-10-31')
        assert future.status_code==200
        assert len(future.json()['days'])==31
        assert {e['kind'] for e in future.json()['events']}=={'birthday','observance'}
        assert client.get(f'/api/saves/{sid}/calendar?start_date=2026-01-01&end_date=2030-01-01').status_code==409
        assert client.get(f'/api/saves/{sid}/calendar?minute=999999').status_code==409
    assert repo.get_snapshot(sid)==before and repo.get_save(sid)['revision']==revision


def test_legacy_fixture_migration_load_turn_remains_relative(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import build_fixture
    from test_narrative_test_world import ordinary_job
    fixture=build_fixture()
    fixture['world_clock'].pop('calendar')
    fixture['world']['characters']['qa_vera'].pop('birth_date')
    repo=Repository(tmp_path/'legacy.sqlite')
    workspace=repo.create_workspace('legacy')
    repo.import_draft(workspace['id'],json.dumps(fixture),workspace['revision'],format='json')
    draft=repo.draft(workspace['id'],author=True)
    sid=repo.confirm_draft(workspace['id'],draft['revision'],draft['version_id'])['save']
    ordinary_job(repo,sid,'start')
    ordinary_job(Repository(repo.path),sid)
    after=repo.get_snapshot(sid)['world_state']
    assert current_time(after)['date'] is None and after['characters']['qa_vera']['birth_date'] is None


def test_real_engine_leap_skip_reload_next_turn_and_rollback(tmp_path):
    from unittest.mock import patch
    import engine
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    from test_narrative_test_world import ordinary_job, CONFIG
    repo=Repository(tmp_path/'leap.sqlite');sid=load_fixture(repo,'calendar-leap')['save']
    # Start stays at 23:59 to make the one-minute skip cross the leap boundary.
    before=repo.get_snapshot(sid)
    camera=before['world_state']['camera']
    seen=[]
    def stream(**kwargs):
        current=json.loads(next(m['content'].split('\n',1)[1] for m in kwargs['messages'] if m['content'].startswith('Текущее состояние / GM-only\n')))
        seen.append(current)
        yield json.dumps(dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids'],elapsed_minutes=0),choices=[])) if kwargs.get('response_format') else 'Прошла минута.'
    def run(kind, config):
        jid=repo.begin_job(sid,'Жду одну минуту.' if kind=='turn' else '',kind,config)
        with patch('engine.find_loaded_model',return_value={'config':{'context_length':32768}}),patch('engine.chat_stream',side_effect=stream):
            engine.run_job(repo.path,jid,engine.Worker())
        assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    run('start',CONFIG)
    initial=repo.get_snapshot(sid)
    assert age_on(initial['world_state']['characters']['qa_vera']['birth_date'],current_time(initial['world_state'])['date'])==31
    run('turn',dict(CONFIG,time_skip=dict(duration=1,reason='Проверка полуночи')))
    skipped=repo.get_snapshot(sid)
    assert current_time(skipped['world_state'])['date']=='2024-02-29'
    assert seen[-1]['time_skip_target']==seen[-2]['time_skip_target']
    assert seen[-1]['time_skip_target']['date']=='2024-02-29'
    ordinary_job(Repository(repo.path),sid)
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)==skipped
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)==initial
    assert current_time(repo.get_snapshot(sid)['world_state'])['date']=='2024-02-28'


def test_structured_temporal_claim_is_runtime_anchored_and_survives_reload():
    from backend.runtime_v3.migration import migrate_v2
    s=state(clock=1257)
    text='В пятницу вечером едем на дачу.'
    raw=dict(final_scene=dict(location_id='home',present_character_ids=['ilya'],elapsed_minutes=1),
        scheduled_event_changes=[dict(id='trip',description='Поездка',character_ids=['ilya','sonya'],due_minute=0,
            temporal=dict(weekday=4,day_period='evening'),time_reference_minute=999999,evidence=text,assertion='agreed',player_assertion='explicit_choice',player_evidence=text)])
    result=StateResolver(s,text,text).resolve(raw)
    event=result.state['scheduled_events']['trip']
    assert event['time_reference_minute']==1257
    reloaded=migrate_v2(json.loads(json.dumps(snapshot(result.state)))).snapshot['world_state']
    assert scheduled_time(reloaded,event)==dict(status='future',due_minute=2520)
    reloaded['meta']['world_time']=3000
    assert scheduled_time(reloaded,event)==dict(status='due',due_minute=2520)
    assert event['status']=='pending'


def test_custom_calendar_property_and_unknown_dates():
    profile=dict(system='custom',month_lengths=[35,27,20],weekday_names=['A','B','C','D'])
    s=state('0042-01-35',1439,3,profile)
    for delta in (0,1,27,28,47,48,82,820):
        projected=current_time(s,1439+delta*1440)
        assert ordinal(projected['date'],profile)==ordinal('0042-01-35',profile)+delta
        assert projected['weekday']==(3+delta)%4
    relative=state(None)
    assert nearby_calendar(relative,{'ilya'})==[]
    assert current_time(relative)['date'] is None


def test_leap_observance_not_fabricated_and_no_unknown_birthday_event():
    s=state('2025-02-28')
    s['characters']['ilya']['birth_date']='2000-02-29'
    assert calendar_range(s,'2025-02-01','2025-03-01')['events']==[]
    assert [e['character_ids'] for e in calendar_range(s,'2024-02-01','2024-03-01')['events']]==[['ilya']]


def test_bad_optional_temporal_does_not_break_load_or_activate_unknown_event():
    s=state()
    s['scheduled_events']['x']=ScheduledEvent(id='x',description='Unknown',due_minute=0).model_dump()
    s['scheduled_events']['x']['temporal']={'time':'invalid'}
    s['scheduled_events']['x']['time_reference_minute']='bad'
    loaded=assert_world_state_v3_invariants(s)
    assert scheduled_time(loaded,loaded['scheduled_events']['x'])['status']=='unresolved'


def test_repeated_unchanged_schedule_claim_does_not_roll_relative_deadline():
    s=state()
    text='Завтра вечером едем на дачу.'
    raw=dict(final_scene=dict(location_id='home',present_character_ids=['ilya'],elapsed_minutes=1),
        scheduled_event_changes=[dict(id='trip',description='Поездка',character_ids=['ilya','sonya'],
            temporal=dict(day_offset=1,day_period='evening'),evidence=text,assertion='agreed',player_assertion='explicit_choice',player_evidence=text)])
    first=StateResolver(s,text,text).resolve(raw).state
    first['meta']['world_time']+=1440
    second=StateResolver(first,text,text).resolve(raw).state
    assert second['scheduled_events']['trip']['time_reference_minute']==s['meta']['world_time']
    assert scheduled_time(second,second['scheduled_events']['trip'])['due_minute']==2520


def test_legacy_sqlite_migration_preserves_explicit_calendar(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import build_fixture, load_fixture
    repo=Repository(tmp_path/'explicit-calendar.sqlite')
    sid=load_fixture(repo)['save']
    legacy=build_fixture('calendar-evening')
    with repo.connect() as db:
        db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(legacy),sid))
        db.execute("DELETE FROM schema_migrations WHERE name='runtime_v3'")
    loaded=Repository(repo.path).get_snapshot(sid)['world_state']
    assert current_time(loaded)['date']=='2026-10-08'
    assert loaded['meta']['calendar']['profile']['id']=='two-shores'
    assert loaded['characters']['qa_vera']['birth_date']=='1993-10-09'
