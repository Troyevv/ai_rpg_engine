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
             endpoint='loc_cafe'),
        dict(kind='information',source_actor_id=b,target_ids=[a],medium='conversation',
             claims=[dict(fact=dict(id='tamara-work',text=statement,visibility='public'),assertion='testimony',status='known',perceived_by=[a])])],
        choices=[dict(index=i,grounding=dict(fact_ids=[fid],from_scene=False)) for i,fid in enumerate(('tamara-work','secret-unknown'))])
    class Stream(list):
        def close(self): pass
    def reply(text):
        return Stream([SimpleNamespace(usage=None,choices=[SimpleNamespace(finish_reason='stop',delta=SimpleNamespace(content=text))])])
    cfg = dict(provider='deepseek',model='deepseek-flash',context_length=131072,max_tokens=2400,update_tokens=8192)
    jid = repo.begin_job(sid,player,'turn',cfg)
    assert json.loads(repo.get_job(jid)['config_json'])['_extraction_contract']==10
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
        assert wire['text']['format']['name'] == 'extraction_v10'
        Draft202012Validator(wire['text']['format']['schema']).validate(payload)
        assert MARKER not in job['narrative'] and job['narrative']==recorded['narrative']
        assert not any(m['content'].startswith('JSON Schema\n') for m in wire['input'])
    fresh=Repository(repo.path)
    after=fresh.get_snapshot(sid)
    state=after['world_state']
    assert all(state['characters'][cid]['location_id']=='loc_cafe' for cid in (a,b))
    fact, = [k for k,row in state['facts'].items() if row['text']==statement]
    assert [k['actor_id'] for k in state['knowledge'].values() if k['fact_id']==fact]==[a]
    from backend.runtime_v3.camera import transition
    from backend.runtime_v3.selectors import ui_view
    from backend.runtime_v3.models import assert_world_state_v3_invariants
    with fresh.connect() as db:
        stored = json.loads(db.execute('SELECT state_json FROM saves WHERE id=?',(sid,)).fetchone()[0])
    assert stored['world_state']['facts'][fact]['visibility'] == 'secret'
    # A historical reply could explicitly mark exactly the same claim public.
    legacy = deepcopy(after)
    legacy['world_state']['facts'][fact]['visibility'] = 'public'
    restored = assert_world_state_v3_invariants(legacy['world_state'])
    assert legacy['world_state']['facts'][fact]['visibility'] == 'public'
    assert restored['facts'][fact]['visibility'] == 'secret'
    assert all(restored['facts'][fid] == row for fid,row in state['facts'].items() if fid != fact)
    assert fact in ui_view(legacy)['world']['facts']
    absent = transition(legacy, 'char_olga')
    assert statement not in json.dumps(ui_view(absent), ensure_ascii=False)
    absent_context = build_context(absent, [], 'Вспоминаю Тамару.', 'turn', 65536, 2400)
    assert statement not in str(absent_context)
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
    last_input = json.loads(messages[-1]['content'].split('\n', 1)[1])
    assert ('<action_suggestions>' in last_input.get('response_format', '')) == (mode=='ordinary')
    if mode == 'ordinary':
        assert 'output only literary prose' not in messages[0]['content']
        from backend.services.structured_extraction import request_schema
        def schema(proposals):
            msgs = build_context(snapshot, [], '', 'turn', 65536, 4096, extraction_text='Светало.', suggestions=proposals)
            return request_schema(msgs)['properties']
        assert 'choices' not in schema([]) and 'choices' in schema(['Открыть окно'])
    choices = [c['action'] for c in CHOICE_EXAMPLES]
    raw = compile_scene(dict(scene=dict(elapsed_minutes=1),scene_steps=[],
        choices=[dict(index=0,grounding=dict(fact_ids=[],from_scene=True))]),
        state,'Тихо.',1,version=9,suggestions=choices)
    resolved = StateResolver(state,'Тихо.','Осматриваюсь.',mode=kind,
        **resolver_options(state,'Осматриваюсь.',kind,contract_version=9)).resolve(raw)
    assert bool(resolved.choices) == (mode=='ordinary')


@pytest.mark.parametrize('break_trip', [None, 'nontraveller', 'arrival', 'local_exit', 'different_origin'])
def test_conversation_after_shared_departure(break_trip):
    from backend.runtime_v3.player_actions import resolver_options
    from backend.runtime_v3.resolver import StateResolver
    state, _ = fixture()
    state['meta']['world_time'] = 100
    action = 'Иду с мамой в парк.'
    proof = dict(quote=action, meaning='preserved')
    listener = 'c' if break_trip == 'nontraveller' else 'a'
    steps = [
        dict(id='out', kind='movement', actor_ids=['a','b'], assertion='departure',
             input_source=proof, text='Они вышли.', minute=0),
        dict(id='talk', kind='information', text='О книге.', source_actor_id='b', target_ids=[listener], during_step_id='out',
             medium='conversation', claims=[dict(fact=dict(text='Она вернула книгу.'),
             assertion='testimony', perceived_by=[listener], status='known')]),
        dict(id='arrive', kind='movement', actor_ids=['a','b'], assertion='completed_arrival',
             endpoint='park', input_source=proof, text='Они пришли.', minute=12),
    ]
    if break_trip in ('arrival','local_exit'):
        steps.insert(1,dict(id='apart', kind='movement', actor_ids=['b'], text='Она ушла отдельно.',
                            assertion='completed_arrival' if break_trip=='arrival' else 'local_exit',
                            endpoint='park' if break_trip=='arrival' else None))
    if break_trip == 'different_origin':
        state['characters']['b']['location_id'] = 'park'
        state['camera']['present_character_ids'] = ['a']
    payload = dict(scene=dict(elapsed_minutes=12),scene_steps=steps)
    def resolve(version):
        return StateResolver(state, 'Разговор в пути.', action, turn_id=1,
                             **resolver_options(state,action,contract_version=version)).resolve(payload)
    with pytest.raises(StructuralDeltaError) as legacy:
        resolve(8)
    assert 'scene_route_invalid' in {r['code'] for r in legacy.value.diagnostics('test')}
    if break_trip:
        with pytest.raises(StructuralDeltaError) as err:
            resolve(9)
        assert {row['code'] for row in err.value.diagnostics('test')} & {'event_presence_invalid','scene_route_invalid'}
        return
    result = resolve(9)
    assert [result.state['characters'][a]['location_id'] for a in ('a','b')]==['park','park']
    assert [k['actor_id'] for k in result.history['knowledge_acquisitions']]==['a']
    assert [e['minute'] for e in (result.history['events'][0],result.history['events'][-1])]==[100,112]
    assert result.state['meta']['world_time']==112
    assert steps[0]['minute']==0 and steps[-1]['minute']==12


@pytest.mark.parametrize('minutes,kind,valid', [
    ([102,110],'interaction',True), ([0,7],'interaction',False),
    ([2,12],'interaction',False), ([0,13,12],'interaction',False),
    ([0,105,12],'interaction',False), ([0,12],'occurrence',False),
])
def test_preserve_absolute_clock_and_reject_ambiguous_offsets(minutes,kind,valid):
    from backend.runtime_v3.player_actions import resolver_options
    from backend.runtime_v3.resolver import StateResolver
    state,_=fixture()
    state['meta']['world_time']=100
    event = (dict(kind=kind,actor_ids=['b']) if kind=='occurrence' else
             dict(kind=kind,actor_id='b',target_ids=['a'],outcome='completed'))
    payload=dict(scene=dict(elapsed_minutes=12),scene_steps=[
        dict(event,text='Событие.',minute=m) for m in minutes])
    resolver=StateResolver(state,'Прошла сцена.','Жду.',turn_id=1,
                           **resolver_options(state,'Жду.',contract_version=9))
    if valid:
        assert [e['minute'] for e in resolver.resolve(payload).history['events']]==minutes
    else:
        with pytest.raises(StructuralDeltaError) as err:
            resolver.resolve(payload)
        assert 'event_minute_invalid' in {r['code'] for r in err.value.diagnostics('test')}


def test_new_actor_card_and_presence_survive_unrelated_invalid_proposal():
    from backend.runtime_v3.consequences import resolve_consequences
    from backend.runtime_v3.player_actions import resolver_options
    from backend.runtime_v3.resolver import StateResolver
    state, _ = fixture()
    def resolve(raw):
        return StateResolver(state, 'Лада вошла.', 'Здороваюсь.',
                             **resolver_options(state, 'Здороваюсь.', contract_version=10)).resolve(raw)
    for fields in ({'fields':{'Роль':'Соседка','Неверное поле':True}}, {}):
        payload = dict(scene=dict(visible_character_ids=['a','lada']), life_changes=[dict(id='absent',life_status='dead')],
                       promotions=[dict(id='lada',name='Лада',**fields)])
        _, result = resolve_consequences(payload, state, 'Лада вошла.', 1, [], resolve)
        assert 'lada' in result.state['camera']['present_character_ids']
        assert result.cards[0]['id'] == 'lada'
        assert 'absent' not in result.state['characters']
        assert result.pending_reviews['lada']['card']['fields']['Роль'] == fields.get('fields', {}).get('Роль', '')


def test_birth_and_experience_need_no_duplicate_scene_step_or_sex_assessment():
    from backend.runtime_v3.player_actions import resolver_options
    from backend.runtime_v3.resolver import StateResolver
    from test_reproduction import conceive
    state = conceive().state
    pregnancy = next(iter(state['pregnancies'].values()))
    child = pregnancy['children'][0]['id']
    payload = dict(scene=dict(elapsed_minutes=pregnancy['due_minute']-state['meta']['world_time']),
                   births=[dict(pregnancy_id=pregnancy['id'],assertion='birth_completed',perceived_by=['a'],location_id='home')],
                   development_evidence=[dict(actor_id='b', meaning='Умеет выслушать', perceived_by=['a'])])
    result = StateResolver(state, 'Ребёнок родился.', 'Остаюсь рядом.',
                           **resolver_options(state,'Остаюсь рядом.',contract_version=10)).resolve(payload)
    assert result.state['characters'][child]['birth_date']=='2026-01-02'
    assert result.state['pregnancies'][pregnancy['id']]['status']=='born'
    assert len(result.cards)==1
    assert 'a:'+pregnancy['count_fact_id'] in result.state['knowledge']
    assert 'b:'+pregnancy['count_fact_id'] not in result.state['knowledge']
    assert 'a:'+pregnancy['sex_fact_ids'][child] not in result.state['knowledge']
    evidence = next(iter(result.state['characters']['b']['personality']['evidence'].values()))
    assert evidence['meaning']=='Умеет выслушать' and evidence['witnesses']==['a']


def test_consent_uses_one_player_quote_and_does_not_infer_it_from_the_scene():
    from test_reproduction import state, service
    from backend.runtime_v3.player_actions import resolver_options
    from backend.runtime_v3.resolver import StateResolver
    before=state()
    action='Мы оба решаем провести ночь вместе без предохранения.'
    row=service(player_evidence=action)
    for key in ('source_event_id','player_assertion','evidence','parent_ids'):
        row.pop(key)
    for quote,accepted in ((action,True),('Ничего такого игрок не говорил.',False),('',False)):
        proposal=dict(reproductive_events=[dict(row,player_evidence=quote)])
        result=StateResolver(before,action,action,**resolver_options(before,action,contract_version=10)).resolve(proposal)
        assert bool(result.state['pregnancies'])==accepted
        if accepted:
            assert set(next(iter(result.state['pregnancies'].values()))['parent_ids'])=={'a','b'}


def test_manual_social_phases_share_revision_history_visibility_and_reload(tmp_path):
    from devtools.narrative_test_world import load_fixture
    from backend.runtime_v3.kinship import visible_relations
    from backend.runtime_v3.residence import visible_social_state
    repo=Repository(tmp_path/'social.sqlite')
    sid=load_fixture(repo,'residence-roles')['save']
    actor, other, observer='qa_timur','qa_marina','qa_kirill'
    original=repo.get_snapshot(sid)
    def apply(action, **fields):
        s=repo.get_snapshot(sid)['world_state']
        repo.update_scene_meta(sid,dict(time='',location='',present_ids=s['camera']['present_character_ids'],
            social=dict(action=action,actor_id=actor,description='Сообщено лично.',known_by=[observer],**fields)),
            repo.get_save(sid)['revision'])
        return Repository(repo.path).get_snapshot(sid)['world_state']
    apply('engaged',other_id=other)
    w=apply('spouse',other_id=other)
    assert {r['kind']:r['status'] for r in visible_relations(w,observer)}=={'engaged':'closed','spouse':'active'}
    assert not visible_relations(w,'qa_zoya')
    w=apply('divorce',other_id=other)
    assert {r['outcome'] for r in visible_relations(w,observer)}=={'superseded','divorced'}
    before=repo.get_save(sid)['revision']
    with pytest.raises(ValueError, match='действующий брак'):
        apply('divorce',other_id=other)
    assert repo.get_save(sid)['revision']==before
    w=apply('move',location_id='qa_room')
    assert w['characters'][actor]['location_id']==original['world_state']['characters'][actor]['location_id']
    w=apply('hire',title='Хранитель фонда')
    job=next(r for r in visible_social_state(w,observer)['roles'] if r['actor_id']==actor)
    w=apply('leave_job',phase_id=job['id'])
    assert w['roles'][job['id']]['outcome']=='resigned'
    assert w['meta']['turn_id']==original['world_state']['meta']['turn_id']
    assert repo.get_snapshot(sid)['history_head']!=original['history_head']


def test_objective_employment_does_not_require_a_second_player_decision():
    from test_residence_roles import state
    from backend.runtime_v3.player_actions import resolver_options
    from backend.runtime_v3.resolver import StateResolver
    before=state()
    record=dict(id='contract',kind='employment',actor_id='a',organization_id='guild',title='Хранитель')
    def apply(row):
        return StateResolver(before,'Назначение оформлено.','Читаю приказ.',
            **resolver_options(before,'Читаю приказ.',contract_version=10)).resolve(dict(role_changes=[row]))
    assert apply(record).state['roles']['contract']['status']=='active'
    with pytest.raises(StructuralDeltaError):
        apply(dict(record,transition='voluntary',decision_actor_id='a'))


def test_repeated_sections_preserve_independent_records_without_last_write_wins():
    from backend.runtime_v3.structured_payload import consequence_payload, object_payload
    wire='{"facts":[{"id":"one"}],"facts":[{"id":"a","id":"b"},{"id":"two"}],"scene":{"elapsed_minutes":4}}'
    with pytest.raises(ValueError):
        object_payload(wire)
    parsed, _, warnings=consequence_payload(wire, ('facts',))
    assert parsed=={'facts':[{'id':'one'},{'id':'two'}],'scene':{'elapsed_minutes':4}}
    assert {row['code'] for row in warnings}=={'repeated_section','duplicate_record_key'}
    ambiguous='{"scene":{"elapsed_minutes":4,"elapsed_minutes":8},"facts":[{"id":"safe"}]}'
    assert consequence_payload(ambiguous, ('facts',))[0]=={'facts':[{'id':'safe'}]}
    assert next(row['index'] for row in warnings if 'index' in row) == 1
    steps = '{"scene_steps":[{"id":"x","id":"y"}],"scene_steps":[{"kind":"movement"}]}'
    assert consequence_payload(steps, ('scene_steps',))[0]['scene_steps'] == [None, {'kind':'movement'}]

def test_life_status_with_direct_observers_survives_an_unknown_recipient():
    from backend.runtime_v3.dossier import details
    from backend.runtime_v3.player_actions import resolver_options
    from backend.runtime_v3.resolver import StateResolver
    from test_life_social import state
    before = state()
    resolver = StateResolver(before, 'Павел умер.', 'Остаюсь рядом.',
        **resolver_options(before, 'Остаюсь рядом.', contract_version=10))
    result = resolver.resolve(dict(life_changes=[dict(id='b', life_status='dead',
        perceived_by=['a','absent'], assertion='established')]))
    assert details(result.state,'b')['life_status'] == 'dead'
    fid = result.state['characters']['b']['life_fact_id']
    assert 'a:'+fid in result.state['knowledge'] and 'c:'+fid not in result.state['knowledge']
    assert any(w['code']=='invalid_status_recipient' for w in result.warnings)
