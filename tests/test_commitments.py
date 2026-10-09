"""#66: evidence-bound scheduled plans on the #37 clock, not time-driven facts."""
from copy import deepcopy
import json
import pytest
from hypothesis import given, strategies as st
from backend.runtime_v3.calendar import scheduled_window, commitment_view, calendar_range
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.scope import RelevanceResolver
from backend.runtime_v3.director import plan, interval_candidates
from backend.runtime_v3.time_skip import plan_skip, TimeSkipRequest
from backend.runtime_v3.models import assert_world_state_v3_invariants
from test_calendar_v2 import state, snapshot

PROOF = 'Я согласен: в пятницу вечером после работы едем, в воскресенье возвращаемся.'


def change(s, records, text=PROOF, player=PROOF, **kwargs):
    records = deepcopy(records)
    for r in records:
        r.setdefault('evidence', text)
        if player:
            r.setdefault('player_evidence', player)
            r.setdefault('player_assertion', 'explicit_choice')
    return StateResolver(s, text, player, **kwargs).resolve(dict(
        final_scene=dict(location_id=s['camera']['location_id'],present_character_ids=s['camera']['present_character_ids']),
        scheduled_event_changes=records))


def trip(**kwargs):
    return dict(id='trip', description='Поездка в коттедж', character_ids=['ilya','sonya'],
                temporal=dict(weekday=4,day_period='evening'), condition='После работы', assertion='agreed', **kwargs)


def plans():
    return change(state(), [trip(), dict(id='return',description='Возвращение домой',character_ids=['ilya'],
        temporal=dict(weekday=6,day_period='evening'),depends_on=['trip'],assertion='agreed')]).state


def test_thursday_plan_window_due_overdue_and_evidence_outcome():
    s=plans(); e=s['scheduled_events']['trip']; w=scheduled_window(s,e)
    assert (w['start_minute'],w['end_minute'],w['precision'],w['exact_time'])==(2520,2759,'period',None)
    assert w['condition']=='После работы' and e['status']=='pending'
    s['meta']['world_time']=2520
    assert scheduled_window(s,e)['relevance']=='due' and e['status']=='pending'
    s['meta']['world_time']=2800
    assert commitment_view(s,e)['context_category']=='OVERDUE PLAN'
    before=deepcopy(s)
    refused=change(s,[dict(id='trip',assertion='occurred',evidence='Другой текст')]).state
    assert refused['scheduled_events']==s['scheduled_events']
    done=change(s,[dict(id='trip',assertion='occurred')],text='Они приехали в коттедж.',player='').state
    assert done['scheduled_events']['trip']['status']=='resolved'
    assert done['scheduled_events']['return']['status']=='pending'
    assert done['relationships']==s['relationships'] and s==before


def test_reschedule_one_id_and_projection_moves_then_cancellation_cascades():
    s=plans()
    s=change(s,[dict(id='trip',assertion='rescheduled',temporal=dict(weekday=5,day_period='morning'))]).state
    assert len(s['scheduled_events'])==2
    assert calendar_range(s,'2026-10-09','2026-10-09')['scheduled']['items']==[]
    assert calendar_range(s,'2026-10-10','2026-10-10')['scheduled']['items'][0]['id']=='trip'
    s=change(s,[dict(id='trip',assertion='cancelled')]).state
    assert s['scheduled_events']['return']['outcome']=='dependency_cancelled'
    assert calendar_range(s,'2026-10-10','2026-10-10')['scheduled']['items'][0]['status']=='cancelled'


def test_obstacle_keeps_plan_missed_is_not_success_and_no_relationship_penalty():
    s=plans()
    blocked=change(s,[dict(id='trip',assertion='blocked')],text='Машина сломалась.',player='').state
    assert blocked['scheduled_events']['trip']['status']=='pending'
    assert blocked['scheduled_events']['return']['status']=='pending'
    assert blocked['scheduled_events']['trip']['outcome']=='blocked'
    missed=change(blocked,[dict(id='trip',assertion='missed')],text='Соня не пришла, поездка не состоялась.',player='').state
    assert missed['scheduled_events']['trip']['status']=='cancelled'
    assert missed['scheduled_events']['trip']['outcome']=='missed'
    assert missed['relationships']==s['relationships']


@pytest.mark.parametrize('text,assertion', [('Может быть съездим.',None),('Мы ездили год назад.','discussed_past'),('Я мечтаю о поездке.','wish'),('Поехали?', 'proposal')])
def test_hypothetical_past_and_unconfirmed_proposal_do_not_create(text,assertion):
    r=trip();r['assertion']=assertion
    result=change(state(),[r],text=text,player='')
    assert not result.state['scheduled_events'] and result.warnings


def test_player_agency_npc_cancellation_and_background_protection():
    result=change(state(),[trip()],player='')
    assert not result.state['scheduled_events']
    s=plans()
    cancelled=change(s,[dict(id='trip',assertion='cancelled',decision_actor_id='sonya')],player='').state
    assert cancelled['scheduled_events']['trip']['status']=='cancelled'
    result=change(s,[dict(id='trip',assertion='occurred')],player='',mode='background',protected_actor_id='ilya')
    assert result.state['scheduled_events']==s['scheduled_events']
    assert result.warnings[0]['code']=='background_commitment_protected'


def test_skip_future_and_already_due_controlled_commitment_without_interrupt_flag():
    s=plans()
    skip=plan_skip(s,TimeSkipRequest(1242,5000))
    assert skip['actual_target']==2520 and skip['interrupted']
    s['meta']['world_time']=2800
    skip=plan_skip(s,TimeSkipRequest(2800,5000))
    assert skip['actual_target']==2800 and skip['elapsed_minutes']==0 and skip['interrupted']


def test_interval_planned_active_completed_not_travel_and_school_role_retained():
    s=state();s['characters']['sonya']['situation']='Учится в университете.'
    r=dict(id='break',description='Каникулы',character_ids=['sonya'],type='school_break',
           temporal=dict(date='2026-10-09'),end_temporal=dict(date='2026-10-24'),assertion='agreed')
    s=change(s,[r],player='').state
    before=deepcopy(s['characters']);s['meta']['world_time']=1440
    assert commitment_view(s,s['scheduled_events']['break'])['interval_state']=='planned'
    s=change(s,[dict(id='break',assertion='started')],player='').state
    s=json.loads(json.dumps(s))
    assert commitment_view(s,s['scheduled_events']['break'])['interval_state']=='active'
    assert s['characters']==before
    s['meta']['world_time']=17*1440
    assert s['scheduled_events']['break']['status']=='pending'
    s=change(s,[dict(id='break',assertion='ended')],player='').state
    assert commitment_view(s,s['scheduled_events']['break'])['interval_state']=='completed'
    assert s['characters']==before


def test_current_vacation_can_be_established_and_end_interrupts():
    s=state()
    r=dict(id='leave',description='Отпуск',character_ids=['ilya'],type='leave',assertion='started',
        temporal=dict(day_offset=0),end_temporal=dict(day_offset=2))
    s=change(s,[r],text='Я уже в отпуске до субботы.',player='').state
    assert s['scheduled_events']['leave']['started_minute']==1242
    assert plan_skip(s,TimeSkipRequest(1242,6000))['actual_target']==4319


def test_gvozd_meeting_resolved_does_not_reactivate_or_close_cottage_plan():
    s=plans();s['facts']['gvozd']=dict(id='gvozd',text='Договорились встретиться в Гвозде.',visibility='public',character_ids=['ilya','sonya'])
    r=dict(id='gvozd',description='Встреча в Гвозде',character_ids=['ilya','sonya'],temporal=dict(day_offset=0,time='21:00'),assertion='agreed')
    s=change(s,[r]).state
    s=change(s,[dict(id='gvozd',assertion='occurred')],text='Встретились, поговорили и разошлись.',player='').state
    s=json.loads(json.dumps(s))
    scope=RelevanceResolver().resolve(snapshot(s),'Встреча в Гвозде')
    assert 'gvozd' in scope.scheduled_event_ids and 'gvozd' not in scope.acting_scheduled_event_ids
    assert 'gvozd' not in plan(s,'turn',scope=scope)['due_event_ids']
    from backend.runtime_v3.context import canonical_slice
    assert next(e for e in canonical_slice(s,scope)['scheduled_events'] if e['id']=='gvozd')['context_category']=='FACT'
    duplicate=dict(r,id='gvozd2')
    result=change(s,[r,duplicate])
    assert 'gvozd2' not in result.state['scheduled_events']
    assert result.state['scheduled_events']['gvozd']['status']=='resolved'
    assert result.state['scheduled_events']['trip']['status']=='pending'
    assert result.state['facts']==s['facts']


def test_dependencies_reject_unknown_cycle_and_preserve_old_plan():
    s=plans()
    result=change(s,[dict(id='trip',assertion='rescheduled',depends_on=['return'])])
    assert result.state['scheduled_events']==s['scheduled_events']
    result=change(state(),[trip(depends_on=['missing'])])
    assert not result.state['scheduled_events']


def test_read_projection_bounded_stable_and_wedding_due_is_not_marriage():
    s=plans();r=trip();r.update(id='wedding',description='Свадьба',type='wedding')
    s=change(s,[r]).state;s['meta']['world_time']=2600
    before=deepcopy(s)
    result=calendar_range(s,'2026-01-01','2026-12-31')['scheduled']
    assert len(result['items'])==3 and all(e['status']=='pending' for e in result['items'])
    assert s==before and not s['relationships']
    with pytest.raises(ValueError):calendar_range(s,'2026-01-01','2028-01-01')
    for n in range(510):s['scheduled_events'][str(n)]={**s['scheduled_events']['trip'],'id':str(n)}
    result=calendar_range(s,'2026-10-01','2026-10-31')['scheduled']
    assert len(result['items'])==500 and result['truncated']


@given(st.integers(min_value=0,max_value=100000))
def test_clock_alone_never_completes_or_mutates_plans(minute):
    s=plans();s['meta']['world_time']=minute;before=deepcopy(s)
    for e in s['scheduled_events'].values():commitment_view(s,e)
    plan(s,'turn');interval_candidates(before,s)
    assert s==before and all(e['status']=='pending' for e in s['scheduled_events'].values())


def test_existing_unresolved_legacy_plan_can_be_cancelled_with_evidence():
    from backend.runtime_v3.models import ScheduledEvent
    s=state();s['scheduled_events']['old']=ScheduledEvent(id='old',description='Когда-нибудь',character_ids=['sonya'],due_minute=0).model_dump()
    result=change(s,[dict(id='old',assertion='cancelled')],player='')
    assert result.state['scheduled_events']['old']['status']=='cancelled'


def test_malformed_optional_records_do_not_crash_turn():
    for bad in (3,{},'ilya',None):
        r=trip();r['character_ids']=bad
        result=change(state(),[r],mode='background')
        assert not result.state['scheduled_events'] and result.warnings


def test_qa_start_turn_reload_next_turn_skip_variants_and_meeting_regression(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture, ACTOR_ID
    from test_narrative_test_world import ordinary_job, CONFIG
    from runtime_v3_fixture import execute
    from backend.runtime_v3.repository import read_history
    repo=Repository(tmp_path/'commitments.sqlite'); sid=load_fixture(repo,'commitments')['save']
    ordinary_job(repo,sid,'start'); ordinary_job(repo,sid)
    repo=Repository(repo.path); ordinary_job(repo,sid)
    initial=repo.get_snapshot(sid)
    assert initial['world_state']['scheduled_events']['qa_sunday_return']['depends_on']==['qa_friday_trip']
    def run(records, text, kind='turn', config=None):
        camera=repo.get_snapshot(sid)['world_state']['camera']
        payload=dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids'],elapsed_minutes=1),
                     scheduled_event_changes=[dict(r,evidence=text,player_evidence=text,player_assertion='explicit_choice') for r in records])
        jid=repo.begin_job(sid,text if kind=='turn' else '',kind,config or CONFIG)
        execute(repo,jid,payload,text)
        assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
        return repo.get_snapshot(sid)
    agreed=run([dict(id='qa_meeting',description='Встреча с Тимуром у карты',character_ids=[ACTOR_ID,'qa_timur'],
                    temporal=dict(day_offset=0,time='21:00'),assertion='agreed')], 'Договорились встретиться у карты в 21:00.')
    done=run([dict(id='qa_meeting',assertion='occurred')], 'Встретились у карты, поговорили и разошлись.')
    turn=repo.list_turns(sid)[-1]
    ordinary_job(repo,sid)
    reloaded=Repository(repo.path).get_snapshot(sid)
    assert reloaded['world_state']['scheduled_events']['qa_meeting']['status']=='resolved'
    assert reloaded['world_state']['scheduled_events']['qa_friday_trip']['status']=='pending'
    repo.rollback_last(sid)
    run([dict(id='qa_meeting',assertion='occurred')], 'Встретились у карты, поговорили и разошлись.',kind='regenerate')
    repo.select_variant(sid,turn['id'],turn['active_variant_id'],repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)==done
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)==agreed
    run([dict(id='qa_meeting',assertion='occurred')], 'Встретились у карты, поговорили и разошлись.')
    # Cancel only the trip before skipping, so the already resolved meeting and
    # dependent return do not interrupt or get narrated as new pending tasks.
    run([dict(id='qa_friday_trip',assertion='cancelled')], 'Поездку отменяем.')
    before=repo.get_snapshot(sid)
    skipped=run([], 'Жду минуту.', config=dict(CONFIG,time_skip=dict(duration=1)))
    assert skipped['world_state']['meta']['world_time']==before['world_state']['meta']['world_time']+1
    ordinary_job(Repository(repo.path),sid)
    with repo.connect() as db: history,_=read_history(db,repo.get_snapshot(sid)['history_head'])
    assert any('qa_meeting' in h.get('before_scheduled_events',{}) for h in history['state_changes'])
    # Read-only bounded API projection uses the same canonical records after reload.
    from fastapi.testclient import TestClient
    from backend.api.app import create_app
    client=TestClient(create_app(repo.path)); revision=repo.get_save(sid)['revision']
    response=client.get(f'/api/saves/{sid}/calendar?start_date=2026-10-01&end_date=2026-10-31')
    assert response.status_code==200
    projected={e['source_id']:e for e in response.json()['scheduled']['items']}
    assert projected['qa_meeting']['status']=='resolved'
    assert projected['qa_sunday_return']['outcome']=='dependency_cancelled'
    assert projected['qa_school_break']['interval_state']=='planned'
    assert repo.get_save(sid)['revision']==revision


def test_active_interval_is_context_not_repeated_due_action_and_legacy_actor_plan_interrupts():
    from backend.runtime_v3.models import ScheduledEvent
    s=state()
    s=change(s,[dict(id='leave',description='Отпуск',character_ids=['ilya'],assertion='started',
                    temporal=dict(day_offset=0),end_temporal=dict(day_offset=2))],player='').state
    scope=RelevanceResolver().resolve(snapshot(s),'')
    assert 'leave' in scope.scheduled_event_ids
    assert 'leave' not in plan(s,'turn',scope=scope)['due_event_ids']
    s['scheduled_events']['legacy']=ScheduledEvent(id='legacy',description='Встреча',character_ids=['ilya'],due_minute=1500).model_dump()
    assert plan_skip(s,TimeSkipRequest(1242,2000))['actual_target']==1500


def test_exact_time_and_malformed_interval_local_salvage():
    s=change(state(),[dict(id='meeting',description='Встреча',character_ids=['sonya'],assertion='agreed',temporal=dict(weekday=4,time='18:30'))],player='').state
    assert scheduled_window(s,s['scheduled_events']['meeting'])['start_minute']==2550
    s['scheduled_events']['meeting'].update(end_temporal={'time':'wrong'},outcome='invented',depends_on=3)
    original=deepcopy(s)
    loaded=assert_world_state_v3_invariants(s)
    assert loaded['scheduled_events']['meeting']['end_temporal'] is None
    assert loaded['scheduled_events']['meeting']['outcome']==''
    assert loaded['scheduled_events']['meeting']['depends_on']==[]
    assert s==original


def test_import_rejects_dependency_cycle_and_legacy_read_degrades_locally():
    from devtools.narrative_test_world import build_fixture
    from backend.services.draft_world import validate
    fixture=build_fixture('commitments')
    fixture['world']['scheduled_events']['qa_friday_trip']['depends_on']=['qa_sunday_return']
    assert validate(fixture)['errors']
    s=plans();s['scheduled_events']['trip']['depends_on']=['missing']
    original=deepcopy(s)
    loaded=assert_world_state_v3_invariants(s)
    assert loaded['scheduled_events']['trip']['depends_on']==[] and s==original
