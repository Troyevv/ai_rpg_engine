from canonical_fixture import canonical, fixture_sequence
import json
from unittest.mock import patch
import pytest
import engine
from test_engine import db,CONFIG,NARRATIVE,result
from test_runtime import generate
from test_pov_documents import generate_background
from backend.services.timeline import current_time,label,parse_time


def intro(storage,sid,actor,source=None,bad=False):
    jid=storage.begin_job(sid,'','pov',{**CONFIG,'actor_id':actor,'source_turn_id':source})
    def stream(**kw):
        if kw.get('response_format'):
            block=next(m['content'] for m in kw['messages'] if m['content'].startswith('Текущее состояние / GM-only'))
            current=json.loads(block.split('\n',1)[1]);camera=current['camera']
            payload=dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=['missing'] if bad else camera['present_character_ids'],situation=camera['situation'],elapsed_minutes=0),
                choices=[dict(action='Действие '+str(i),speech='') for i in range(6)])
            yield json.dumps(payload,ensure_ascii=False)
        else:yield NARRATIVE
    with patch('engine.find_loaded_model',return_value={'config':{}}),patch('engine.chat_stream',side_effect=stream):
        engine.run_job(storage.path,jid,engine.Worker())
    return jid


def test_pov_intro_commits_actor_and_choices_atomically(db):
    repo,_,sid=db;generate(repo,sid,'start');before=repo.get_save(sid)
    failed=intro(repo,sid,'character_2',bad=True)
    assert repo.get_job(failed)['status']=='error'
    assert repo.get_save(sid)==before
    jid=intro(repo,sid,'character_2')
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    save=repo.get_save(sid);turn=repo.list_turns(sid)[-1]
    assert save['state']['controlled_actor_id']=='character_2'
    assert turn['kind']=='pov' and turn['pov_actor_id']=='character_2'
    assert len(json.loads(turn['choices_json']))==6
    repo.rollback_last(sid)
    assert repo.get_save(sid)['state']==before['state']


def test_background_participant_anchor_and_return_time(db):
    repo,_,sid=db;generate(repo,sid,'start');generate_background(repo,sid)
    background=repo.list_turns(sid)[-1]
    jid=intro(repo,sid,'character_3',background['id'])
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    state=repo.get_save(sid)['state']
    assert state['scene_meta']['location']=='Подвал'
    assert repo.get_job(jid)['kind']=='pov'
    assert json.loads(repo.get_job(jid)['config_json'])['source_node_id']==background['node_id']
    assert current_time(state)==1105
    jid=intro(repo,sid,'character_1')
    assert repo.get_job(jid)['status']=='saved'
    state=repo.get_save(sid)['state']
    assert state['scene_meta']['location']=='Кухня' and state['scene_meta']['time']=='День 1 · Пн · 18:25'
    assert state['world']['characters']['character_3']['location']=='Подвал'
    assert all('character_1' not in f['known_by'] for f in state['facts'])


def test_pov_regeneration_pins_actor_and_pre_transition_snapshot(db):
    repo,_,sid=db;generate(repo,sid,'start');intro(repo,sid,'character_2')
    original=repo.latest_job(sid);first=repo.list_turns(sid)[-1]
    jid=repo.begin_job(sid,'','regenerate',CONFIG)
    job=repo.get_job(jid)
    assert job['kind']=='pov' and job['pov_actor_id']=='character_2'
    assert job['before_json']==original['before_json']
    assert job['context_json']==original['context_json']
    assert json.loads(job['memory_before_json'])['world_state']['camera']['controlled_actor_id']=='character_2'


def test_clock_cannot_rewind_across_pov(db):
    from backend.runtime_v3.camera import transition
    from backend.runtime_v3.models import assert_world_state_v3_invariants
    repo,_,sid=db;state=repo.get_snapshot(sid)
    state['world_state']['meta']['world_time']=6990
    next_state=transition(state,'character_2')
    assert next_state['world_state']['meta']['world_time']==6990
    assert_world_state_v3_invariants(next_state['world_state'],state['world_state'])
