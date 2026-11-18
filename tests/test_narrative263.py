"""Production contract controls. Café prose/input are recorded; the new extraction is authored."""
import json
import sqlite3
from copy import deepcopy
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from jsonschema import Draft202012Validator

import engine
from backend.repositories.preparation import Repository
from backend.runtime_v3.context import build_context
from backend.runtime_v3.scene_repair import SceneCandidate
from backend.runtime_v3.scene_steps import compile_scene
from backend.runtime_v3.suggestions import MARKER, split_suggestions
from backend.services.world_delta_errors import StructuralDeltaError
from test_berezovsk_followup248 import LTA
from test_group152 import group
from test_integrated_repair247 import seed
from test_scene_steps255 import fixture
from test_spatial256 import original
from test_structured_extraction255 import events

pytestmark = pytest.mark.extraction_current


def test_annotation_boundary_and_relative_order():
    state, _ = fixture()
    talk = dict(kind='interaction', actor_id='b', target_ids=['a'], outcome='completed',
                text='Садись рядом.', evidence=None, timing='uncertain')
    payload = dict(scene={}, scene_steps=[talk], diagnostics={'events':['never execute']})
    before = deepcopy(payload)
    raw = compile_scene(payload,state,talk['text'],1,version=9)
    assert len(raw.records['events']) == 1 and payload == before
    assert {w.get('field') or w['section'] for w in raw.warnings} == {'timing','evidence','diagnostics'}
    with pytest.raises(StructuralDeltaError):
        compile_scene(dict(payload, new_world_changes=[{}]),state,'',1,version=9)
    with pytest.raises(StructuralDeltaError, match='порядок'):
        compile_scene(dict(payload,scene_steps=[dict(talk),dict(talk)]),state,'',1,version=9)
    with pytest.raises(StructuralDeltaError):
        compile_scene(payload,state,'',1,version=8)


def test_same_listeners_do_not_make_other_conversation_editable():
    state,_ = fixture()
    steps = [dict(id=name, kind='interaction', actor_id='b', target_ids=['a'],
                  outcome='completed', text=name) for name in ('tea','film')]
    candidate = SceneCandidate(state,'Два разговора.','Слушаю.',1,version=9)
    candidate.parse(dict(scene={},scene_steps=steps))
    feedback = json.loads(candidate.feedback([dict(section='scene_steps',index=0,code='scene_step_invalid')],None))
    assert feedback['scope']['step_ids'] == ['tea']
    with pytest.raises(StructuralDeltaError) as err:
        candidate.parse(dict(candidate_hash=feedback['candidate_hash'], replacements=[dict(steps[1],text='changed')],
                             sections={}, reason='edit'))
    assert err.value.code == 'scene_repair_scope'


def test_remote_planner_outage_and_cancellation():
    from backend.runtime_v3.remote_initiative import stage
    state,_ = group()
    def outage(*args,**kwargs):
        raise RuntimeError('unavailable')
    result = stage(state,outage,'first')
    assert result['_remote_batch']['state_changes'][0]['kind'] == 'remote_deferred'
    assert result['world_state']['remote_events'] == state['world_state']['remote_events']
    from llm import ProviderGenerationError
    with pytest.raises(RuntimeError, match='unavailable'):
        stage(state,outage,'integrity',provider_errors=(ProviderGenerationError,))
    cancelled = Event()
    cancelled.set()
    with pytest.raises(RuntimeError):
        stage(state,outage,'second',cancelled=cancelled)
    def disk_failure(*args,**kwargs):
        raise sqlite3.OperationalError('disk')
    with pytest.raises(sqlite3.OperationalError):
        stage(state,disk_failure,'third')


def test_private_menu_never_streams_even_when_marker_splits():
    prose = '1. Обычный список в записке.\n2. Ещё один пункт.'
    full = prose+'\n'+MARKER+'["Секрет"]'
    for end in range(len(prose)+1,len(full)+1):
        visible, suggestions = split_suggestions(full[:end])
        assert visible.rstrip() == prose and not suggestions
    assert split_suggestions(full, complete=True) == (prose,['Секрет'])
    assert split_suggestions(prose, complete=True) == (prose,[])


def test_current_and_recorded_edited_prompt_and_supporting_knowledge():
    from long_world_fixture import long_world
    snapshot, turns, history = long_world()
    prompts = {'state_update_prompt.md':{'content':'legacy Movement + Event instructions\nCUSTOM'},
               'extraction_author.md':{'content':'Удели внимание разговору.'}}
    args = (snapshot,turns,'Что с конвертом?','turn',32768,4096)
    opts = dict(extraction_text='Тимур отвечает про конверт.', prompts=prompts, world_history=history)
    new = build_context(*args,**opts)
    old = build_context(*args,extraction_contract=8,**opts)
    assert 'CUSTOM' not in str(new) and 'Удели внимание' in str(new)
    assert 'Choice context / controlled actor' not in str(new)
    assert 'CUSTOM' in str(old) and 'Удели внимание' not in str(old)
    for name in ('facts','knowledge'):
        counts = new.selection['sections'][name]
        assert counts['included'] == counts['selected'] > 0


def test_current_cafe_wire_commit_reload_and_rollback(tmp_path):
    recorded = original('cafe')
    player = recorded['player_input']
    with patch('backend.runtime_v3.player_actions.EXTRACTION_VERSION',5):
        repo = Repository(tmp_path/'cafe.sqlite')
        sid = seed(repo,dict(before=recorded['snapshot']['world_state']))['save']
    snapshot = deepcopy(LTA['snapshot'])
    snapshot.update(world_state=deepcopy(recorded['snapshot']['world_state']), history_head=repo.get_snapshot(sid)['history_head'])
    with repo.connect() as db:
        db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(snapshot),sid))
    a,b = 'char_alexey','char_galina'
    statement = 'После закрытия Тамара работает с бумагами или ставит тесто на утро.'
    proposal = 'Спросить Тамару о её работе.'
    hidden = 'Спросить о чужом секрете.'
    payload = dict(scene=dict(elapsed_minutes=3),scene_steps=[
        dict(kind='movement',id='route',actor_ids=[a,b],assertion='completed_arrival',
             endpoint='loc_cafe',text='Они дошли до кафе.',input_source=dict(quote='Направляюсь от берега к «Берёзке»',meaning='preserved')),
        dict(kind='information',during_step_id='route',source_actor_id=b,target_ids=[a],medium='conversation',
             claims=[dict(fact=dict(id='tamara-work',text=statement),assertion='testimony',status='known',perceived_by=[a])])],
        choices=[dict(index=i,grounding=dict(fact_ids=[fid],from_scene=False)) for i,fid in enumerate(('tamara-work','secret-unknown'))])
    class Stream(list):
        def close(self): pass
    def reply(text):
        return Stream([SimpleNamespace(usage=None,choices=[SimpleNamespace(finish_reason='stop',delta=SimpleNamespace(content=text))])])
    cfg = dict(provider='deepseek',model='deepseek-flash',context_length=131072,max_tokens=2400,update_tokens=8192)
    jid = repo.begin_job(sid,player,'turn',cfg)
    assert json.loads(repo.get_job(jid)['config_json'])['_extraction_contract']==9
    with patch('llm.OpenAI') as sdk:
        def chat(**kwargs):
            if kwargs.get('response_format'):
                return reply('{"action":null}')
            return reply(recorded['narrative']+'\n'+MARKER+json.dumps([proposal,hidden],ensure_ascii=False))
        sdk.return_value.chat.completions.create.side_effect=chat
        sdk.return_value.responses.create.return_value=Stream(events(json.dumps(payload)))
        engine.run_job(repo.path,jid,engine.Worker(api_key='offline',epoch=0))
        job=repo.get_job(jid)
        assert job['status']=='saved', job['error']
        requests=sdk.return_value.responses.create.call_args_list
        assert len(requests)==1
        wire=requests[0].kwargs
        assert wire['text']['format']['name'] == 'extraction_v9'
        Draft202012Validator(wire['text']['format']['schema']).validate(payload)
        assert MARKER not in job['narrative'] and job['narrative']==recorded['narrative']
        assert not any(m['content'].startswith('JSON Schema\n') for m in wire['input'])
    fresh=Repository(repo.path)
    after=fresh.get_snapshot(sid)
    state=after['world_state']
    assert all(state['characters'][cid]['location_id']=='loc_cafe' for cid in (a,b))
    fact, = [k for k,row in state['facts'].items() if row['text']==statement]
    assert [k['actor_id'] for k in state['knowledge'].values() if k['fact_id']==fact]==[a]
    assert [c['action'] for c in json.loads(fresh.list_turns(sid)[-1]['choices_json'])]==[proposal]
    next_job=fresh.begin_job(sid,'Говорю с Тамарой о работе.','turn',cfg)
    with patch('llm.OpenAI') as sdk:
        sdk.return_value.chat.completions.create.side_effect=chat
        sdk.return_value.responses.create.return_value=Stream(events('{"scene":{"elapsed_minutes":1},"scene_steps":[]}'))
        engine.run_job(fresh.path,next_job,engine.Worker(api_key='offline',epoch=0))
        assert fresh.get_job(next_job)['status']=='saved'
        following=json.loads(fresh.get_job(next_job)['context_json'])
        assert statement in str(following) and fact in str(following)
    fresh.rollback_last(sid)
    fresh.rollback_last(sid)
    assert fact not in fresh.get_snapshot(sid)['world_state']['facts']


def test_literary_tail_and_selected_archive_respect_actor_view():
    from long_world_fixture import long_world
    snapshot, turns, history = long_world()
    turns = [dict(turns[0], sequence=i, assistant_text=f'Литературная сцена {i}.') for i in range(20,40)]
    history['events'] = [dict(history['events'][-1], source_sequence=i, witnesses=['a'],
                              id=f'letter-{i}') for i in (4,5,6)]
    def read(sequences):
        assert set(sequences) == {4,5,6}
        return [dict(turns[0], sequence=4, assistant_text='Тимур сложил конверт вчетверо.'),
                dict(turns[0], sequence=5, pov_actor_id='b', audience_json='["b"]',
                     assistant_text='Секретная сцена Веры.'),
                dict(turns[0], sequence=6, pov_actor_id='b', audience_json='["a","b"]',
                     assistant_text='Внутренний монолог Тимура.')]
    history['_literary_sources'] = read
    messages = build_context(snapshot,turns,'Что с конвертом?','turn',131072,4096,world_history=history,
                             recent_turns=15,target_context_budget=50000)
    assert len([m for m in messages if m['role']=='assistant']) == 15
    assert 'Тимур сложил конверт вчетверо.' in str(messages)
    assert 'Секретная сцена Веры.' not in str(messages) and 'Внутренний монолог Тимура.' not in str(messages)


def test_bounded_history_honors_jump_and_regeneration_cutoff(tmp_path):
    repo = Repository(tmp_path/'jump.sqlite')
    recorded = original('cafe')
    with patch('backend.runtime_v3.player_actions.EXTRACTION_VERSION',5):
        sid = seed(repo,dict(before=recorded['snapshot']['world_state']))['save']
    snapshot = repo.get_snapshot(sid)
    actor = snapshot['world_state']['camera']['controlled_actor_id']
    encoded = json.dumps(snapshot, ensure_ascii=False)
    ids = []
    with repo.connect() as db:
        first = db.execute('SELECT max(sequence) FROM turns WHERE save_id=?',(sid,)).fetchone()[0] + 1
        for i in range(12):
            changes = dict(context_situation_changes=[actor] if i==1 else [],
                           presentation=dict(surface='physical'))
            ids.append(db.execute("""INSERT INTO turns(save_id,sequence,user_text,assistant_text,before_json,
                after_json,kind,changes_json,pov_actor_id,audience_json) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (sid,first+i,'Ход',f'Сцена {i}',encoded,encoded,'long_term' if i==0 else 'turn',
                 json.dumps(changes),actor,json.dumps([actor]))).lastrowid)
    rows, next_sequence = repo.context_history(sid, ids[10], 3, actor, actor)
    assert next_sequence == first+10
    assert [row['id'] for row in rows] == [ids[0],*ids[7:10]]
    assert rows[0]['_temporal_only'] and rows[0]['_refreshed_situations'] == {actor}
    assert all(not r['_temporal_only'] for r in rows[1:])


def test_first_remote_provider_failure_commits_only_foreground(tmp_path):
    from llm import ProviderGenerationError
    from backend.runtime_v3.repository import read_history
    snapshot, _ = group()
    repo = Repository(tmp_path/'remote.sqlite')
    with patch('backend.runtime_v3.player_actions.EXTRACTION_VERSION',5):
        sid = seed(repo,dict(before=snapshot['world_state']))['save']
    snapshot['history_head'] = repo.get_snapshot(sid)['history_head']
    with repo.connect() as db:
        db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(snapshot),sid))
    config = dict(model='authored',provider='local',context_length=131072,max_tokens=1200,update_tokens=8192)
    jid = repo.begin_job(sid,'Смотрю в окно.','turn',config)
    def provider(*,messages,**kwargs):
        if any(m['content'].startswith('completed_narrative\n') for m in messages):
            yield '{"scene":{"elapsed_minutes":1},"scene_steps":[]}'
        elif kwargs.get('response_format'):
            raise ProviderGenerationError('Remote planner unavailable')
        else:
            yield 'За окном идёт дождь.'
    with patch('engine.find_loaded_model',return_value={'config':{'context_length':131072}}), patch('engine.chat_stream',provider):
        engine.run_job(repo.path,jid,engine.Worker())
    fresh = Repository(repo.path)
    assert fresh.get_job(jid)['status'] == 'saved', fresh.get_job(jid)['error']
    attempts = fresh.request_log(job_id=jid)
    assert [(a['stage'],a['status']) for a in reversed(attempts)] == [
        ('remote_initiative','error'),('narrative','complete'),('extraction','complete')]
    after = fresh.get_snapshot(sid)
    assert after['world_state']['remote_events'] == snapshot['world_state']['remote_events']
    with fresh.connect() as db:
        past,_ = read_history(db,after['history_head'])
    assert any(row.get('kind')=='remote_deferred' for row in past['state_changes'])
    assert fresh.list_turns(sid)[-1]['assistant_text'] == 'За окном идёт дождь.'


@pytest.mark.parametrize('mode',['ordinary','observer','background','blocked'])
def test_current_menu_owner_and_actor_availability(mode):
    from test_narrative_choices import initial, CHOICE_EXAMPLES
    from backend.runtime_v3.camera import observe
    from backend.runtime_v3.suggestions import NARRATIVE_INSTRUCTION
    from backend.runtime_v3.player_actions import resolver_options
    from backend.runtime_v3.resolver import StateResolver
    snapshot = initial()
    if mode == 'observer':
        snapshot = observe(snapshot,'b',allow_protagonist=True)
    state = snapshot['world_state']
    if mode == 'blocked':
        state['characters']['a']['capabilities']['can_act'] = False
    kind = 'background' if mode == 'background' else 'turn'
    messages = build_context(snapshot,[],'Осматриваюсь.',kind,65536,4096)
    assert (NARRATIVE_INSTRUCTION in messages[0]['content']) == (mode=='ordinary')
    choices = [c['action'] for c in CHOICE_EXAMPLES]
    raw = compile_scene(dict(scene=dict(elapsed_minutes=1),scene_steps=[],
        choices=[dict(index=0,grounding=dict(fact_ids=[],from_scene=True))]),
        state,'Тихо.',1,version=9,suggestions=choices)
    resolved = StateResolver(state,'Тихо.','Осматриваюсь.',mode=kind,
        **resolver_options(state,'Осматриваюсь.',kind,contract_version=9)).resolve(raw)
    assert bool(resolved.choices) == (mode=='ordinary')
