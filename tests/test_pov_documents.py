from runtime_v3_fixture import wire
import json
from copy import deepcopy
from threading import Event
from unittest.mock import patch

import pytest
import engine
from canonical_fixture import canonical, fixture_sequence
from backend.repositories.preparation import Repository
from backend.services.pov import controlled
from backend.services.memory import compact
from context_builder import build_context
from test_engine import db, CONFIG, NARRATIVE, result, run
from test_runtime import generate
from test_worlds import summary

SECRET = 'Персонаж 3 передал персонажу 4 тайный ключ от подвала.'


def background():
    return {'scene':{'text':'Тайная встреча у подвала.','time':'18:25','location':'Подвал','present_ids':['character_3','character_4']},
            'facts':[{'text':'Тайный ключ передан.','known_by':['character_3','character_4'],'evidence':SECRET}],
            'events':[{'text':'Передача ключа.','character_ids':['character_3','character_4'],'evidence':SECRET}],
            'relationships':[{'source_id':'character_3','target_id':'character_4','text':'Доверяет ключ.','direction':'up','aspect':'доверие','reason':'Передача ключа','evidence':SECRET}],
            'choices':[]}


def generate_background(storage,sid,kind='background'):
    job=storage.begin_job(sid,'',kind,CONFIG)
    def stream(**kw):
        yield json.dumps(wire(canonical(background(),fixture_sequence(storage,job)),SECRET,json.loads(storage.get_job(job)['before_json'])),ensure_ascii=False) if kw.get('response_format') else SECRET
    with patch('engine.find_loaded_model',return_value={'config':{}}),patch('engine.chat_stream',side_effect=stream):
        engine.run_job(storage.path,job,engine.Worker())
    assert storage.get_job(job)['status']=='saved',storage.get_job(job)['error']
    return job


def test_versions_delete_restore_and_save_independence(tmp_path):
    repo=Repository(tmp_path/'game.db')
    w=repo.create_workspace('Сценарий');wid=w['id']
    original=repo.document_history('summary',wid)['active_id']
    first=repo.change_document('summary',wid,summary(),original)['active_id']
    world=repo.save_world('Мир',summary());save=repo.create_save(world,'Прохождение')
    before=repo.get_save(save)
    removed=repo.change_document('summary',wid,'',first)['active_id']
    assert not repo.workspace(wid)['summary_complete']
    restored=repo.change_document('summary',wid,'',removed,first)
    assert len(restored['versions'])==4
    assert restored['versions'][0]['source_version_id']==first
    assert repo.workspace(wid)['summary']==summary()
    with pytest.raises(ValueError,match='изменилась'):
        repo.change_document('summary',wid,'',first)
    repo.remove_workspace(wid,repo.workspace(wid)['revision'])
    assert repo.list_workspaces()==[]
    assert repo.list_workspaces(True)[0]['id']==wid
    repo.remove_workspace(wid,repo.workspace(wid)['revision'],False)
    repo.remove_world(world)
    assert repo.list_worlds()==[]
    assert repo.get_save(save)==before
    assert repo.save_world('Мир',summary())==world
    assert len(repo.list_worlds())==1
    assert Repository(repo.path).document_history('summary',wid)==restored


def test_prompt_versions_pinned_for_running_job_and_regeneration(db):
    storage,_,sid=db
    prompts=storage.prompt_snapshot();name='game_system_prompt.md'
    job=storage.begin_job(sid,'','start',CONFIG)
    edited=storage.change_document('prompt',name,'Новые правила.',prompts[name]['id'])
    calls=run(storage,job)
    assert prompts[name]['content'] in calls[0]['messages'][0]['content']
    replacement=storage.begin_job(sid,'','regenerate',CONFIG)
    assert json.loads(storage.get_job(replacement)['config_json'])['_prompts']==prompts
    run(storage,replacement)
    rolled=storage.change_document('prompt',name,'',edited['active_id'],prompts[name]['id'])
    assert len(rolled['versions'])==3
    assert storage.prompt_snapshot()[name]['content']==prompts[name]['content']
    assert rolled['active_id']!=prompts[name]['id']


def test_switch_actor_roles_and_stale_revision(db):
    storage,_,sid=db
    generate(storage,sid,'start')
    state=storage.get_save(sid)
    storage.switch_actor(sid,'character_2',state['revision'])
    switched=storage.get_save(sid)
    assert controlled(switched['state'])=='character_2'
    assert switched['state']['protagonist_id']=='character_1'
    with pytest.raises(ValueError,match='изменился'):
        storage.switch_actor(sid,'character_1',state['revision'])
    payload=result();payload['characters']=[{'id':'character_2','goal':'Новая цель','evidence':NARRATIVE}]
    from backend.runtime_v3.resolver import StateResolver
    snapshot=storage.get_snapshot(sid)
    resolved=StateResolver(snapshot['world_state'],NARRATIVE,'').resolve(wire(payload,NARRATIVE,snapshot))
    assert resolved.state['characters']['character_2']['goals']==snapshot['world_state']['characters']['character_2']['goals']
    assert any(w.get('field')=='goals' for w in resolved.warnings)
    payload['characters'][0]['id']='character_1'
    resolved=StateResolver(snapshot['world_state'],NARRATIVE,'').resolve(wire(payload,NARRATIVE,snapshot))
    from backend.runtime_v3.lifecycle import active_texts
    assert active_texts(resolved.state['characters']['character_1']['goals'])==['Новая цель']
    storage.switch_actor(sid,'character_1',switched['revision'])
    assert storage.get_snapshot(sid)['world_state']['characters']['character_1']['location_id']==storage.get_snapshot(sid)['world_state']['camera']['location_id']


def test_backstage_is_canonical_and_regenerates_without_leaking_history(db):
    storage,_,sid=db
    generate(storage,sid,'start')
    scene=storage.get_save(sid)['state']['scene']
    original=generate_background(storage,sid)
    state=storage.get_save(sid)['state'];turn=storage.list_turns(sid)[-1]
    assert turn['kind']=='background' and turn['pov_actor_id'] is None
    assert json.loads(turn['audience_json'])==['character_3','character_4']
    assert state['scene']=='Тайная встреча у подвала.' and state['world_clock']['last_event_time']=='День 1 · Пн · 18:25'
    assert json.loads(storage.get_job(original)['before_json'])['world_state']['camera']['situation']==scene
    assert controlled(state) is None
    assert state['facts'][-1]['known_by']==['character_3','character_4']
    assert 'change' not in state['relationships'][-1]  # New dimensions have no numeric baseline.
    messages=build_context(storage.get_snapshot(sid),storage.list_turns(sid),'Продолжить','turn',32768,2000)
    assert SECRET not in [m['content'] for m in messages if m['role']=='assistant']
    pov=next(m['content'] for m in messages if m['content'].startswith('Знания POV'))
    assert 'Тайный ключ передан.' not in pov
    newer=generate_background(storage,sid,'regenerate')
    assert storage.get_job(original)['context_json']==storage.get_job(newer)['context_json']
    assert len(storage.variants(turn['node_id']))==2
    storage.select_variant(sid,turn['id'],turn['active_variant_id'],storage.get_save(sid)['revision'])
    assert storage.get_save(sid)['state']==state
    storage.switch_actor(sid,'character_3',storage.get_save(sid)['revision'])
    assert storage.get_save(sid)['state']['scene_meta']['location']=='Подвал'
    assert storage.get_save(sid)['state']['controlled_actor_id']=='character_3'


def test_default_world_camera_excludes_protagonist(db):
    from backend.runtime_v3.camera import observe
    storage,_,sid=db;snapshot=storage.get_snapshot(sid)
    with pytest.raises(ValueError):observe(snapshot,actor_id='character_1')
    explicit=observe(snapshot,actor_id='character_1',allow_protagonist=True)
    assert explicit['world_state']['camera']['controlled_actor_id'] is None


def test_memory_compaction_scopes_inputs_to_witnesses(db):
    storage,_,sid=db
    generate(storage,sid,'start');generate_background(storage,sid)
    from test_pov_transitions import intro
    intro(storage,sid,'character_1')
    job=storage.begin_job(sid,'Пауза','turn',CONFIG)
    captured={}
    def summarize(messages):
        data=json.loads(messages[-1]['content']);captured[data['POV']]=data
        yield 'Память '+data['POV']
    state=compact(storage,storage.get_job(job),storage.get_save(sid)['state'],storage.list_turns(sid),
                  {**CONFIG,'recent_turns':1,'memory_batch':4},summarize,Event())
    assert SECRET not in json.dumps(captured['character_1'],ensure_ascii=False)
    assert 'Тайный ключ передан.' in json.dumps(captured['character_3'],ensure_ascii=False)
    assert SECRET not in json.dumps(captured['character_3'],ensure_ascii=False)
    assert SECRET in json.dumps(captured['Объективная память ведущего'],ensure_ascii=False)
    assert state['memory']['per_actor']['character_1']['summary']=='Память character_1'
