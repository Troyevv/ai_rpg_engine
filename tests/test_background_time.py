"""Background clock ownership through the same QA world/import/runtime as #78."""
from copy import deepcopy
import json
from threading import Event
from unittest.mock import patch

import pytest

import engine
from backend.repositories.preparation import Repository
from backend.runtime_v3.calendar import current_time
from backend.runtime_v3.camera import observe
from backend.runtime_v3.migration import migrate_v2
from backend.runtime_v3.models import WorldHistoryV3
from backend.runtime_v3.repository import read_history
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.simulation import simulate
from backend.runtime_v3.time_skip import TimeSkipRequest, plan_skip
from backend.services.world_delta_errors import StructuralDeltaError
from devtools.narrative_test_world import ACTOR_ID, build_fixture, load_fixture
from test_narrative_test_world import CONFIG, ordinary_job

NARRATIVE = 'Олег закончил сверку карты и прочитал записку.'
NPC = 'qa_oleg'


def fixture():
    return migrate_v2(build_fixture('calendar-evening')).snapshot


def payload(camera, elapsed, background=True):
    raw = dict(final_scene=dict(location_id=camera['location_id'],
        present_character_ids=camera['present_character_ids'], elapsed_minutes=elapsed))
    if background:
        raw.update(character_changes=[dict(id=NPC,situation='Закончил сверку карты.',evidence=NARRATIVE)],
            facts=[dict(id='qa_note',text='В записке указан номер листа карты.',evidence=NARRATIVE)],
            events=[dict(id='note',text=NARRATIVE,participants=[NPC],witnesses=[NPC,ACTOR_ID],
                fact_ids=['qa_note'],medium='discovery',evidence=NARRATIVE)],
            knowledge_gained=[dict(actor_id=cid,fact_id='qa_note',source_event_id='note',evidence=NARRATIVE)
                             for cid in [NPC,ACTOR_ID]])
    return raw


def simulate_skip(elapsed, damage=None, always_bad=False):
    before=fixture();after=deepcopy(before)
    request=TimeSkipRequest(before['world_state']['meta']['world_time'],before['world_state']['meta']['world_time']+240)
    after['last_time_skip']=plan_skip(before['world_state'],request)
    after['world_state']['meta'].update(world_time=request.target_minute,turn_id=1)
    source=deepcopy(after)
    calls=[];repairs=[];warnings=[]
    def generate(stage,messages,*args,**kwargs):
        calls.append(stage)
        if stage=='world_simulation': return [NARRATIVE]
        camera=json.loads(next(m['content'].split('\n',1)[1] for m in messages
                              if m['content'].startswith('Текущее состояние / GM-only\n')))['camera']
        raw=payload(camera,elapsed)
        if damage and (stage=='world_simulation_delta' or always_bad): damage(raw)
        return [json.dumps(raw)]
    result,history=simulate(before,after,WorldHistoryV3().to_dict(),32768,CONFIG,generate,Event(),warnings,repairs.append)
    # Simulation enriches last_time_skip diagnostics in place, but must not
    # leak resolved state (including failed repair attempts) into its input.
    assert after['world_state']==source['world_state']
    return source,result,history,calls,repairs,warnings


@pytest.mark.parametrize('elapsed',[0,15])
def test_simulation_fixed_time_preserves_npc_history_knowledge_and_agency(elapsed):
    before,after,history,calls,repairs,warnings=simulate_skip(elapsed)
    now=before['world_state']['meta']['world_time']
    assert calls==['world_simulation','world_simulation_delta'] and not repairs
    assert after['world_state']['meta']['world_time']==now
    assert after['world_state']['camera']==before['world_state']['camera']
    assert after['world_state']['characters'][ACTOR_ID]==before['world_state']['characters'][ACTOR_ID]
    assert after['world_state']['characters'][NPC]['situation']=='Закончил сверку карты.'
    assert NPC+':qa_note' in after['world_state']['knowledge']
    assert ACTOR_ID+':qa_note' not in after['world_state']['knowledge']
    assert all(row['actor_id']!=ACTOR_ID for row in history['knowledge_acquisitions'])
    assert history['events'][0]['recorded_minute']==now
    assert history['turns'][0]['world_time']==history['turns'][0]['game_time_before']==now
    if elapsed:
        assert len(warnings)==1
        assert warnings[0]['code']=='background_elapsed_ignored'
        assert warnings[0]['stage']=='background_simulation'
        assert (warnings[0]['proposed_minutes'],warnings[0]['applied_minutes'])==(15,0)
    else: assert not warnings


@pytest.mark.parametrize('mode,observed,advance',[('turn',True,15),('turn',False,15),('background',False,0)])
def test_resolver_time_mode_is_explicit_not_inferred_from_camera_or_visibility(mode,observed,advance):
    snap=observe(fixture(),actor_id=NPC,allow_protagonist=True)
    s=snap['world_state'];now=s['meta']['world_time'];raw=payload(s['camera'],15)
    original=deepcopy(raw)
    result=StateResolver(s,NARRATIVE,'',mode=mode,observed=observed).resolve(raw)
    assert result.state['meta']['world_time']==now+advance
    assert result.history['events'][0]['recorded_minute']==now+advance
    assert result.patch.meta['world_time']==now+advance
    assert result.history['turns'][0]['world_time']==now+advance
    assert s['meta']['world_time']==now and raw==original
    replay=StateResolver(s,NARRATIVE,'',mode=mode,observed=observed).resolve(raw)
    assert replay.state==result.state and replay.history==result.history


@pytest.mark.parametrize('bad',[True,'15',-1,10081])
def test_malformed_duration_is_still_repairable(bad):
    s=observe(fixture(),actor_id=NPC,allow_protagonist=True)['world_state']
    original=deepcopy(s)
    with pytest.raises(StructuralDeltaError) as exc:
        StateResolver(s,NARRATIVE,'',mode='background',observed=False).resolve(payload(s['camera'],bad))
    assert exc.value.code=='invalid_time' and exc.value.repairable
    assert s==original


def change_controlled(raw):
    raw['character_changes'].append(dict(id=ACTOR_ID,situation='Ушёл из дома.',emotion='Злится.',evidence=NARRATIVE))


def invalid_location(raw):
    raw['final_scene']['location_id']='missing_location'


@pytest.mark.parametrize('damage,code',[(change_controlled,'background_agency_invalid'),(invalid_location,'camera_location_invalid')])
def test_real_invalid_changes_still_trigger_repair(damage,code):
    before,after,history,calls,repairs,warnings=simulate_skip(15,damage)
    assert calls==['world_simulation','world_simulation_delta','world_simulation_repair']
    assert [r['repair_error_code'] for r in repairs]==[code]
    assert after['world_state']['characters'][ACTOR_ID]==before['world_state']['characters'][ACTOR_ID]
    assert after['world_state']['meta']['world_time']==before['world_state']['meta']['world_time']
    assert len(history['events'])==1 and len(history['turns'])==1
    with pytest.raises(StructuralDeltaError) as exc:
        simulate_skip(15,damage,always_bad=True)
    assert exc.value.code==code  # Never silently accept protected-actor mutations.


@pytest.mark.parametrize('elapsed',[0,15])
def test_qa_time_skip_job_reload_regenerate_rollback_and_repeat(tmp_path,elapsed):
    repo=Repository(tmp_path/'background.sqlite');sid=load_fixture(repo,'calendar-evening')['save']
    ordinary_job(repo,sid,'start')
    before=repo.get_snapshot(sid);start=before['world_state']['meta']['world_time']
    def run(kind='turn'):
        config=dict(CONFIG,time_skip=dict(duration=240,reason='Проверка фоновой сверки карты')) if kind=='turn' else CONFIG
        jid=repo.begin_job(sid,'Жду четыре часа.' if kind=='turn' else '',kind,config)
        calls=[]
        def stream(**kwargs):
            calls.append(kwargs)
            if not kwargs.get('response_format'): yield NARRATIVE;return
            current=json.loads(next(m['content'].split('\n',1)[1] for m in kwargs['messages']
                                    if m['content'].startswith('Текущее состояние / GM-only\n')))
            hidden=current['camera']['mode']=='observer'
            # The main extraction's 15 minutes is overridden by Time Skip, while
            # the background extraction deliberately proposes another duration.
            yield json.dumps(payload(current['camera'],elapsed if hidden else 15,hidden))
        with patch('engine.find_loaded_model',return_value={'config':{'context_length':32768}}),patch('engine.chat_stream',side_effect=stream):
            engine.run_job(repo.path,jid,engine.Worker())
        job=repo.get_job(jid)
        assert job['status']=='saved',job['error']
        assert len(calls)==4  # Two main + two background calls, zero time repairs.
        after=repo.get_snapshot(sid)
        assert after['world_state']['meta']['world_time']==start+240
        assert after['world_state']['characters'][ACTOR_ID]==before['world_state']['characters'][ACTOR_ID]
        assert after['world_state']['characters'][NPC]['situation']=='Закончил сверку карты.'
        assert after['last_time_skip']['living_world_llm_calls']==2
        with repo.connect() as db: history,_=read_history(db,after['history_head'])
        hidden=[t for t in history['turns'] if not t['player_observed']]
        assert hidden and all(t['world_time']==t['game_time_before']==start+240 for t in hidden)
        hidden_events=[e for e in history['events'] if e.get('local_id')=='note']
        assert len(hidden_events)==1 and hidden_events[0]['recorded_minute']==start+240
        return after
    after=run()
    repo=Repository(repo.path)
    assert repo.get_snapshot(sid)==after
    turn=repo.list_turns(sid)[-1]
    assert run('regenerate')['world_state']==after['world_state']
    repo.select_variant(sid,turn['id'],turn['active_variant_id'],repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)==after
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)==before
    again=run()
    assert again['world_state']==after['world_state']
    assert current_time(again['world_state'])==current_time(after['world_state'])
    ordinary_job(Repository(repo.path),sid)  # Next ordinary playable turn after reload.
    assert repo.get_snapshot(sid)['world_state']['meta']['world_time']==start+241
