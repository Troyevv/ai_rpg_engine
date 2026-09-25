from canonical_fixture import canonical, fixture_sequence
import json
from unittest.mock import patch
import pytest
import engine
from test_engine import db,CONFIG,NARRATIVE,result
from test_runtime import generate
from test_pov_documents import generate_background
from backend.services.timeline import current_time,label,parse_time
from backend.services.pov import transition


def intro(storage,sid,actor,source=None,bad=False):
    jid=storage.begin_job(sid,'','pov',{**CONFIG,'actor_id':actor,'source_turn_id':source})
    def stream(**kw):
        if kw.get('response_format'):
            payload=result()
            block=next(m['content'] for m in kw['messages'] if m['content'].startswith('Текущая сцена'))
            scene=json.loads(block.split('\n',1)[1]);payload['scene'].update(scene['scene_meta']);payload['scene']['text']=scene['scene']
            payload['events']=[e for e in payload.get('events',[]) if set(e['character_ids'])<=set(payload['scene']['present_ids'])]
            if bad:payload['choices']=[]
            yield json.dumps(canonical(payload,fixture_sequence(storage,jid)),ensure_ascii=False)
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
    assert state['pov_transition']['source_node_id']==background['node_id']
    assert current_time(state)==1105
    jid=intro(repo,sid,'character_1')
    assert repo.get_job(jid)['status']=='saved'
    state=repo.get_save(sid)['state']
    assert state['scene_meta']['location']=='Кухня' and state['scene_meta']['time']=='День 1 (Пн) 18:25'
    assert state['actor_scenes']['character_3']['meta']['location']=='Подвал'
    assert all('character_1' not in f['known_by'] for f in state['facts'])


def test_pov_regeneration_pins_actor_and_pre_transition_snapshot(db):
    repo,_,sid=db;generate(repo,sid,'start');intro(repo,sid,'character_2')
    original=repo.latest_job(sid);first=repo.list_turns(sid)[-1]
    jid=repo.begin_job(sid,'','regenerate',CONFIG)
    job=repo.get_job(jid)
    assert job['kind']=='pov' and job['pov_actor_id']=='character_2'
    assert job['before_json']==original['before_json']
    assert job['context_json']==original['context_json']
    assert json.loads(job['memory_before_json'])['controlled_actor_id']=='character_2'


def test_clock_cannot_rewind_across_pov(db):
    from backend.services.timeline import advance
    repo,_,sid=db;state=repo.get_save(sid)['state']
    state['world_clock']={'last_event_time':'Пт 20:30'}
    state['actor_scenes']={'character_2':{'text':'Ждёт','meta':{'time':'Пт 19:50','location':'Дом','present_ids':['character_2']}}}
    next_state=transition(state,'character_2')
    assert next_state['scene_meta']['time']=='День 5 (Пт) 20:30'
    assert next_state['pov_transition']['anchor']['meta']['time']=='Пт 19:50'
    with pytest.raises(ValueError,match='раньше'):
        advance(next_state,{}, {'time':'Пт 19:50'})
    assert parse_time('День 6 00:10')>current_time(next_state)
