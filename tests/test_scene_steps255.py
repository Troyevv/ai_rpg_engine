"""Authored semantic controls, never a replay of the missing 16-turn session."""
from copy import deepcopy
import pytest
from backend.runtime_v3.scene_steps import compile_scene, validate, input_schema
from backend.runtime_v3.models import Location
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.player_actions import resolver_options
from backend.services.world_delta_errors import StructuralDeltaError
from test_reproduction import state

pytestmark = pytest.mark.extraction_v6

INPUT='Прощаюсь с b, иду в парк и приветствую c.'


def fixture():
    s=state();s['locations']['park']=Location(id='park',name='Парк').model_dump()
    s['characters']['c']['location_id']='park'
    p=dict(scene=dict(elapsed_minutes=5),scene_steps=[
        dict(id='bye',kind='interaction',actor_id='a',target_ids=['b'],outcome='completed',text='Попрощался.',input_source=dict(quote='Прощаюсь с b',meaning='preserved')),
        dict(id='walk',kind='movement',actor_id='a',endpoint='park',assertion='completed_arrival',text='Пришёл.',input_source=dict(quote='иду в парк',meaning='preserved')),
        dict(id='hello',kind='interaction',actor_id='a',target_ids=['c'],outcome='completed',text='Приветствовал.',input_source=dict(quote='приветствую c',meaning='preserved'))])
    return s,p


def resolve(s,p,player=INPUT):
    return StateResolver(s,'Авторская проза.',player,turn_id=1,**resolver_options(s,player,contract_version=6)).resolve(p)


def test_goodbye_arrival_greeting_one_axis():
    s,p=fixture(); before=deepcopy(s)
    r=resolve(s,p)
    assert r.state['characters']['a']['location_id']=='park'
    assert r.state['characters']['b']['location_id']=='home'
    assert r.state['camera']['present_character_ids']==['a']
    assert [e['location_id'] for e in r.history['events']]==['home','park','park']
    assert not r.state['knowledge'] and s==before
    assert resolve(s,p).history==r.history


def test_contact_before_arrival_rejected():
    s,p=fixture();p['scene_steps'][1:]=reversed(p['scene_steps'][1:])
    with pytest.raises(StructuralDeltaError):resolve(s,p)


@pytest.mark.parametrize('assertion',['intent','preparation','attempt'])
def test_plan_never_moves(assertion):
    s,p=fixture();p['scene_steps']=p['scene_steps'][1:2];p['scene_steps'][0]['assertion']=assertion
    assert resolve(s,p).state['characters']['a']['location_id']=='home'


def test_departure_no_invented_endpoint():
    s,p=fixture();p['scene_steps']=p['scene_steps'][1:2];p['scene_steps'][0].update(assertion='departure',endpoint=None)
    assert resolve(s,p).state['characters']['a']['location_id'] is None


def test_no_full_snapshot_or_provider_bookkeeping():
    _,p=fixture()
    for field,value in [('final_scene',{}),('events',[]),('semantic_compiled',True)]:
        with pytest.raises(StructuralDeltaError):validate(dict(p,**{field:value}))


def test_no_false_visibility_arrival_or_blank_success():
    s,p=fixture();p['scene_steps']=[];p['scene']['visible_character_ids']=['a','c']
    with pytest.raises(StructuralDeltaError):resolve(s,p)
    with pytest.raises(StructuralDeltaError):validate({})


def test_stable_source_ids_on_neighbor_edit():
    s,p=fixture();a=compile_scene(p,s,'Проза',1)
    p['scene_steps'][0]['text']='Иначе сформулированное прощание.'
    b=compile_scene(p,s,'Проза',1)
    assert [e['id'] for e in a.records['events']]==[e['id'] for e in b.records['events']]


def test_information_perceiver_and_fact_repeat_scope():
    s,p=fixture();p['scene_steps']=[]
    info=dict(id='tell',kind='information',source_actor_id='b',target_ids=['a'],medium='conversation',text='Сообщил.',claims=[dict(fact=dict(id='f',text='Первое'),assertion='testimony',status='known',perceived_by=['a'])])
    p['scene_steps']=[info]
    r=resolve(s,p)
    assert len(r.history['knowledge_acquisitions'])==1
    assert {k['actor_id'] for k in r.state['knowledge'].values()}=={'a'}
    assert not any(k['actor_id']=='b' for k in r.state['knowledge'].values())


def test_targeted_repair_keeps_independent_proposal_and_rejects_stale():
    import json
    from backend.runtime_v3.scene_repair import SceneCandidate
    s,p=fixture(); p['facts']=[dict(id='independent',text='Неизменное утверждение.',evidence='')]
    broken=deepcopy(p);broken['scene_steps'][1]['endpoint']='missing'
    candidate=SceneCandidate(s,'Проза',INPUT,1)
    raw=candidate.parse(broken)
    with pytest.raises(StructuralDeltaError) as error:
        StateResolver(s,'Проза',INPUT,**resolver_options(s,INPUT,contract_version=6)).resolve(raw)
    feedback=json.loads(candidate.feedback(error.value.diagnostics('repair'),broken))
    patch=dict(candidate_hash=feedback['candidate_hash'],replacements=[p['scene_steps'][1]],sections={},reason='Исправлен неверный endpoint, смысл прибытия сохранён.')
    repaired=candidate.parse(patch)
    assert repaired.semantic_candidate['facts']==p['facts']
    assert repaired.semantic_candidate['scene_steps'][0]==broken['scene_steps'][0]
    assert StateResolver(s,'Проза',INPUT,**resolver_options(s,INPUT,contract_version=6)).resolve(repaired).state['characters']['a']['location_id']=='park'
    with pytest.raises(StructuralDeltaError):candidate.parse(dict(patch,candidate_hash='stale'))
    with pytest.raises(StructuralDeltaError):candidate.parse(dict(patch,sections={'facts':[dict(id='independent',text='Подмена')]}))


def test_full_repair_invalid_root_and_no_patch_without_base():
    import json
    from backend.runtime_v3.scene_repair import SceneCandidate
    s,p=fixture();candidate=SceneCandidate(s,'Проза',INPUT,1)
    with pytest.raises(StructuralDeltaError) as error:candidate.parse(' ')
    assert json.loads(candidate.feedback(error.value.diagnostics('repair'),' '))['repair_mode']=='full'
    assert candidate.parse(p).semantic_candidate==p


def test_current_production_job_commit_reload_next_turn(tmp_path):
    import json
    from unittest.mock import patch
    import engine
    from backend.repositories.preparation import Repository
    from test_integrated_repair247 import seed, archived, execute, history, CONFIG
    # The imported world is historical; seeding uses its recorded v5 setup.
    with patch('backend.runtime_v3.player_actions.EXTRACTION_VERSION',5):
        data=archived('knowledge');repo=Repository(tmp_path/'scene.sqlite');sid=seed(repo,data)['save']
    data['narrative']='Кирилл попрощался и дошёл до парка.'
    data['player_input']='Прощаюсь и иду в парк.'
    s=repo.get_snapshot(sid)['world_state'];actor=s['camera']['controlled_actor_id']
    p=dict(scene=dict(elapsed_minutes=5),locations=[dict(id='new-park',name='Парк',evidence='Парк')],scene_steps=[
        dict(id='walk',kind='movement',actor_id=actor,endpoint='new-park',assertion='completed_arrival',text='Дошёл до парка.',input_source=dict(quote='иду в парк',meaning='preserved'))])
    job,calls=execute(repo,sid,data,[p],legacy=False,contract_version=6,config=CONFIG)
    assert job['status']=='saved',job['error']
    assert len(calls)==2
    fresh=Repository(repo.path);after=fresh.get_snapshot(sid)
    assert after['world_state']['characters'][actor]['location_id']=='new-park'
    assert after['world_state']['camera']['present_character_ids']==[actor]
    assert json.loads(job['config_json'])['_extraction_contract']==6
    next_data=dict(data,player_input='Осматриваюсь.',narrative='Кирилл осматривается.')
    next_job,calls=execute(fresh,sid,next_data,[dict(scene=dict(elapsed_minutes=1),scene_steps=[])],legacy=False,config=CONFIG)
    assert next_job['status']=='saved',next_job['error']
    fresh.rollback_last(sid)
    assert fresh.get_snapshot(sid)['world_state']==after['world_state']


def test_v6_background_and_lta_keep_authority_and_namespace():
    import json
    from threading import Event
    from backend.runtime_v3.models import WorldHistoryV3, Thread
    from backend.runtime_v3.simulation import simulate
    from backend.runtime_v3.long_term import plan,run
    from test_background_time import fixture as background_world
    from test_reproduction import snap
    cfg=dict(model='test',context_length=65536,max_tokens=2000,update_tokens=8192,_extraction_contract=6)
    before=background_world();after=deepcopy(before)
    after['world_state']['meta']['world_time']+=240;after['world_state']['meta']['turn_id']+=1
    calls=[]
    def generate(stage,messages,*args,**kwargs):
        calls.append(stage)
        if stage=='world_simulation':return ['Олег пришёл в новую комнату.']
        return [json.dumps(dict(scene={},scene_steps=[dict(id='arrival',kind='movement',actor_id='qa_oleg',text='Пришёл.',assertion='completed_arrival',endpoint='room')],locations=[dict(id='room',name='Комната',evidence='')]))]
    result,batch=simulate(before,after,WorldHistoryV3().to_dict(),65536,cfg,generate,Event(),[],lambda _:None)
    assert calls==['world_simulation','world_simulation_delta']
    assert result['world_state']['characters']['qa_oleg']['location_id']=='room'
    assert result['world_state']['camera']==after['world_state']['camera']
    assert len(batch['movements'])==1
    before=snap(state());before['world_state']['threads']['education']=Thread(id='education',description='Учёба',character_ids=['c'],relevance=1).model_dump()
    candidate=next(c for c in plan(before,dict(amount=5,unit='years')).candidates if c.source_id=='education')
    def lta(stage,messages,*args,**kwargs):
        if stage=='long_term_narrative':return ['Он пришёл учиться.']
        return [json.dumps(dict(scene={},scene_steps=[dict(id='arrival',kind='movement',actor_id='c',text='Пришёл.',assertion='completed_arrival',endpoint='school',advance_candidate_ids=[candidate.id])],locations=[dict(id='school',name='Школа',evidence='')]))]
    result,batch,report=run(before,dict(amount=5,unit='years',max_llm_calls=2),generate=lta,config=cfg)
    assert report['accepted'],report['diagnostics']
    assert result['world_state']['characters']['c']['location_id']=='school'
    assert len(batch['movements'])==1 and report['llm_calls']==2


@pytest.mark.parametrize('damage',['source','decision','endpoint','visible','unknown_actor'])
def test_v6_substantive_negatives(damage):
    s,p=fixture()
    if damage=='source':p['scene_steps'][0]['input_source']['quote']='Нет такого ввода.'
    if damage=='decision':p['agency_findings']=[dict(narrative_evidence='Он согласился.',classification='unauthorized_choice')]
    if damage=='endpoint':p['scene_steps'][1]['endpoint']='unknown'
    if damage=='visible':p['scene']['visible_character_ids']=['a','b']
    if damage=='unknown_actor':p['scene_steps'][0]['actor_id']='unknown'
    before=deepcopy(s)
    with pytest.raises(StructuralDeltaError):resolve(s,p)
    assert s==before


def test_exact_fact_repeated_but_privacy_conflict_rejected():
    s,p=fixture();p['scene_steps']=[]
    row=dict(id='same',text='Утверждение.',evidence='')
    p['facts']=[row,deepcopy(row)]
    assert len(resolve(s,p).state['facts'])==1
    p['facts'][1]['visibility']='secret'
    with pytest.raises(StructuralDeltaError):resolve(s,p)


@pytest.mark.parametrize('mode',['targeted','full','out_of_scope','repeat_error','departure_endpoint','departure_repeat'])
def test_production_one_repair_atomic_reload_and_recorded_schema(tmp_path,mode):
    import json
    from unittest.mock import patch
    import engine
    from backend.repositories.preparation import Repository
    from test_integrated_repair247 import seed,archived,CONFIG
    with patch('backend.runtime_v3.player_actions.EXTRACTION_VERSION',5):
        data=archived('knowledge');repo=Repository(tmp_path/'repair.sqlite');sid=seed(repo,data)['save']
    before=repo.get_snapshot(sid);actor=before['world_state']['camera']['controlled_actor_id']
    good=dict(id='walk',kind='movement',actor_id=actor,text='Пришёл.',assertion='completed_arrival',endpoint='park',input_source=dict(quote='Иду в парк.',meaning='preserved'))
    p=dict(scene=dict(elapsed_minutes=1),scene_steps=[dict(good,endpoint='missing')],locations=[dict(id='park',name='Парк',evidence='')],facts=[dict(id='untouched',text='Независимое утверждение.',evidence='')])
    if mode.startswith('departure_'):
        # Reduced control for the real provider smoke: departure carried a
        # known endpoint. It must be rejected, but allow the one existing repair.
        p['scene_steps'][0].update(assertion='departure',endpoint='park')
    calls=[]
    def stream(**kwargs):
        calls.append(kwargs)
        if not kwargs.get('response_format'):yield 'Кирилл дошёл до парка.';return
        schema=json.loads(next(m['content'].split('\n',1)[1] for m in kwargs['messages'] if m['content'].startswith('JSON Schema\n')))
        if len(calls)==2:yield '{}' if mode=='full' else json.dumps(p);return
        if mode=='full':reply=dict(p,scene_steps=[good])
        else:
            assert 'candidate_hash' in schema['properties']
            reply=dict(candidate_hash=schema['properties']['candidate_hash']['const'],replacements=[p['scene_steps'][0] if mode in ('repeat_error','departure_repeat') else good],sections={},reason='Уточнение ошибочного endpoint.')
            if mode=='out_of_scope':reply['sections']={'facts':[dict(id='untouched',text='Подмена')]}
        yield json.dumps(reply)
    jid=repo.begin_job(sid,'Иду в парк.','turn',CONFIG)
    with patch('engine.find_loaded_model',return_value={'config':{}}),patch('engine.chat_stream',side_effect=stream):
        engine.run_job(repo.path,jid,engine.Worker())
    job=repo.get_job(jid);fresh=Repository(repo.path)
    assert len(calls)==3
    if mode in ('targeted','full','departure_endpoint'):
        assert job['status']=='saved',job['error']
        assert fresh.get_snapshot(sid)['world_state']['characters'][actor]['location_id']=='park'
        assert fresh.get_snapshot(sid)['world_state']['facts']['untouched']['text']=='Независимое утверждение.'
    else:
        assert job['status']=='error'
        assert fresh.get_snapshot(sid)==before
    logs=repo.request_log(job_id=jid)
    assert len(logs)==3 and all(r['response_text'] for r in logs)
    extraction=[r for r in logs if r['stage'].startswith('extraction')]
    assert all(r['extraction_contract']==6 for r in extraction)
    assert all(r['diagnostics']['extraction_candidate']['contract']==6 for r in extraction)
    if mode in ('targeted','full','departure_endpoint'):
        audit=next(r for r in extraction if r['stage']=='extraction_repair')['diagnostics']['extraction_candidate']
        assert audit['compiled']['semantic_candidate']['scene_steps']==[good]
        assert audit['candidate']['facts']==p['facts']


def test_v6_saturated_32k_context_and_wire_schema_budget(tmp_path):
    import json
    from unittest.mock import patch
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    from test_narrative_test_world import ordinary_job,NARRATIVE
    from backend.runtime_v3.context import build_context
    from backend.runtime_v3.repository import read_history
    from backend.services.structured_extraction import request_schema
    from context_builder import estimate
    repo=Repository(tmp_path/'saturated.sqlite');sid=load_fixture(repo,'newborn-triplets')['save']
    with patch('backend.runtime_v3.player_actions.EXTRACTION_VERSION',5):
        for _ in range(2):ordinary_job(repo,sid)
    snapshot=repo.get_snapshot(sid)
    with repo.connect() as db:history,_=read_history(db,snapshot['history_head'])
    messages=build_context(snapshot,repo.list_turns(sid,context=True),'Осматриваю фотографии.','turn',32768,4096,
        extraction_text=NARRATIVE,extraction_contract=6,world_history=history)
    assert estimate(messages)<=32768-4096-256
    sent=request_schema(messages)
    assert set(sent['required'])=={'scene','scene_steps'}
    assert not {'final_scene','events','movements','information_events','player_agency'}&sent['properties'].keys()
    assert json.loads(next(m['content'].split('\n',1)[1] for m in messages if m['content'].startswith('completed_narrative\n')))==NARRATIVE
    current=json.loads(next(m['content'].split('\n',1)[1] for m in messages if m['content'].startswith('Текущее состояние / GM-only\n')))
    assert len(current['pregnancies'][0]['children'])==3
    assert current['reproductive_knowledge']
    from backend.runtime_v3.scene_repair import SceneCandidate
    candidate=SceneCandidate(snapshot['world_state'],NARRATIVE,'Осматриваю фотографии.',3)
    payload=dict(scene=dict(elapsed_minutes=1),scene_steps=[dict(id='inspect',kind='occurrence',
        actor_ids=[snapshot['world_state']['camera']['controlled_actor_id']],text='Рассмотрел фотографии.',
        input_source=dict(quote='Осматриваю фотографии.',meaning='preserved'))])
    candidate.parse(payload)
    feedback=candidate.feedback([dict(section='scene_steps',index=0,code='authored_budget_control')],payload)
    repair=build_context(snapshot,repo.list_turns(sid,context=True),'Осматриваю фотографии.','turn',32768,4096,
        extraction_text=NARRATIVE,extraction_contract=6,world_history=history,validation_feedback=feedback)
    assert estimate(repair)<=32768-4096-256
    assert 'candidate_hash' in request_schema(repair)['required']
    assert json.loads(next(m['content'].split('\n',1)[1] for m in repair if m['content'].startswith('completed_narrative\n')))==NARRATIVE
    repair_current=json.loads(next(m['content'].split('\n',1)[1] for m in repair if m['content'].startswith('Текущее состояние / GM-only\n')))
    assert len(repair_current['pregnancies'][0]['children'])==3 and repair_current['reproductive_knowledge']


def test_unusable_step_ids_get_full_repair_without_crashing():
    import json
    from backend.runtime_v3.scene_repair import SceneCandidate
    s=state();candidate=SceneCandidate(s,'Проза','',1)
    with pytest.raises(StructuralDeltaError) as exc:candidate.parse(dict(scene={},scene_steps=[{}]))
    assert json.loads(candidate.feedback(exc.value.diagnostics('repair'),{}))['repair_mode']=='full'


@pytest.mark.parametrize('case,acquisitions',[('family_birth',10),('knowledge',6),('campaign',9),('social',0)])
def test_authored_v6_on_original_254_domain_sources(case,acquisitions):
    """Original before/prose, explicitly authored representation; not live PASS."""
    from test_acceptance254 import recorded
    data,old=recorded(case);p=deepcopy(old)
    actions={a['id']:a for a in p.pop('player_agency',{}).get('actions',[])}
    events=p.pop('events',[]);infos=p.pop('information_events',[])
    p['scene']=p.pop('final_scene');p['scene'].pop('location_id')
    p['scene']['visible_character_ids']=p['scene'].pop('present_character_ids')
    steps=[]
    for event in events:
        actor=event.get('actor_id')
        if case=='knowledge' and actor!=data['before']['camera']['controlled_actor_id']:
            # Human-authored consolidation: NPC reply and its perceptions are
            # the same semantic source. Retain its domain reference ID once.
            infos[0]['id']=event['id'];continue
        if case=='family_birth':
            step=dict(kind='occurrence',id=event['id'],text=event['text'],actor_ids=event['participants'],witnesses=event['witnesses'])
            p['births'][0]['sex_observations'][0]['source_assertion']='direct_observation'
        else:
            step=dict(kind='interaction',id=event['id'],text=event['text'],actor_id=actor,target_ids=event.get('target_ids',[]),outcome='completed')
        action=actions.get(event.get('player_action_id'))
        if action:step['input_source']=dict(quote=action['player_evidence'],meaning=action['meaning'])
        steps.append(step)
    for info in infos:
        step={k:v for k,v in info.items() if k not in ('location_id','order','player_action_id')}
        steps.append(dict(step,kind='information'))
    p['scene_steps']=steps
    selection=data['selection']['5']
    result=StateResolver(data['before'],data['narrative'],data['player_input'],
        **resolver_options(data['before'],data['player_input'],contract_version=6),
        chronology_events=data['world_history'].get('events',[]),pacing_decision=selection.get('pacing'),
        initiative_decision=selection.get('initiative'),continuity_decision=selection.get('continuity')).resolve(p)
    assert len(result.history['knowledge_acquisitions'])==acquisitions
    if case=='family_birth':
        assert 'character_827f657aa87adc1fb374' in result.state['characters']
        assert len(result.state['characters'])==len(data['before']['characters'])+1


def test_route_return_intermediate_information_and_stable_chronology():
    s,p=fixture()
    p['scene_steps']=[p['scene_steps'][1],dict(id='listen',kind='information',source_actor_id='c',target_ids=['a'],medium='conversation',text='Сообщил в парке.',claims=[dict(fact=dict(id='news',text='Новость'),assertion='testimony',status='known',perceived_by=['a'])]),dict(id='back',kind='movement',actor_id='a',text='Вернулся.',assertion='completed_arrival',endpoint='home',input_source=dict(quote='Возвращаюсь домой.',meaning='preserved'))]
    r=resolve(s,p,INPUT+' Возвращаюсь домой.')
    assert r.state['characters']['a']['location_id']=='home'
    assert [e['order'] for e in r.history['events']]==[0,1,2]
    assert [e['location_id'] for e in r.history['events']]==['park','park','home']
    assert len(r.history['knowledge_acquisitions'])==1
    assert r.state['characters']['b']['location_id']=='home'


def test_uncertain_order_and_simultaneous_contact_not_sorted_into_a_meeting():
    s,p=fixture();p['scene_steps'][1]['timing']='uncertain'
    with pytest.raises(StructuralDeltaError) as exc:resolve(s,p)
    assert exc.value.code=='scene_order_ambiguous'
    p['scene_steps'][1]['timing']='after_previous';p['scene_steps'][2]['timing']='simultaneous'
    with pytest.raises(StructuralDeltaError):resolve(s,p)


@pytest.mark.parametrize('failure',['sqlite','stale','cancel'])
def test_v6_job_publication_failures_leave_canon_unchanged(tmp_path,failure):
    import json,sqlite3
    from unittest.mock import patch
    import engine
    from backend.repositories.preparation import Repository
    from test_integrated_repair247 import seed,archived,CONFIG
    with patch('backend.runtime_v3.player_actions.EXTRACTION_VERSION',5):
        data=archived('knowledge');repo=Repository(tmp_path/'atomic.sqlite');sid=seed(repo,data)['save']
    before=repo.get_snapshot(sid);turns=repo.list_turns(sid)
    jid=repo.begin_job(sid,'Осматриваюсь.','turn',CONFIG);worker=engine.Worker(epoch=0)
    def stream(**kw):
        if kw.get('response_format'):
            if failure=='stale':
                with repo.connect() as db:db.execute('UPDATE saves SET revision=revision+1 WHERE id=?',(sid,))
            elif failure=='cancel':repo.job_progress(jid,'stopped');worker.cancelled.set()
            yield json.dumps(dict(scene=dict(elapsed_minutes=1),scene_steps=[]))
        else:yield 'Кирилл осматривается.'
    with patch('engine.find_loaded_model',return_value={'config':{}}),patch('engine.chat_stream',side_effect=stream):
        if failure=='sqlite':
            with patch.object(engine.Storage,'commit_job',side_effect=sqlite3.OperationalError('authored disk failure')):engine.run_job(repo.path,jid,worker)
        else:engine.run_job(repo.path,jid,worker)
    fresh=Repository(repo.path)
    assert fresh.get_snapshot(sid)==before and fresh.list_turns(sid)==turns
    assert fresh.get_job(jid)['status']!='saved'


def test_information_compile_failure_points_to_external_source():
    s=state()
    p=dict(scene={},scene_steps=[dict(id='news',kind='information',source_actor_id='b',target_ids=['a'],
        medium='conversation',text='Сообщил.',claims=[dict(fact_id='absent',assertion='testimony',status='known',perceived_by=['a'])])])
    with pytest.raises(StructuralDeltaError) as exc:resolve(s,p)
    row=exc.value.diagnostics('repair')[0]
    assert row['section']=='scene_steps' and row['index']==0 and row['source_ids']==['news']
    assert row['compiled_path']=='information_events[0]'


def test_objective_step_inherits_selected_action_provenance():
    s=state();player='Записываю заметку.'
    p=dict(scene=dict(elapsed_minutes=1),scene_steps=[dict(id='note',kind='occurrence',text='Записал заметку.',actor_ids=['a'],
        input_source=dict(quote=player,meaning='preserved'))])
    result=resolve(s,p,player)
    assert result.history['events'][0]['player_action']['player_evidence']==player
    p['scene_steps'][0]['actor_ids']=['b']
    with pytest.raises(StructuralDeltaError):resolve(s,p,player)


def test_repair_follows_fact_dependencies_and_logs_reinterpretation():
    import json
    from backend.runtime_v3.scene_repair import SceneCandidate
    s=state();p=dict(scene={},facts=[dict(id='f',text='Новость')],scene_steps=[
        dict(id='tell',kind='information',source_actor_id='b',target_ids=['a'],medium='conversation',text='Сообщил.',
            claims=[dict(fact_id='f',assertion='testimony',status='known',perceived_by=['a'])])])
    candidate=SceneCandidate(s,'Проза','',1);candidate.parse(p)
    feedback=json.loads(candidate.feedback([dict(section='facts',index=0,code='fact_invalid')],p))
    assert feedback['scope']['step_ids']==['tell']
    fixed=deepcopy(p['scene_steps'][0]);fixed['source_actor_id']='c'
    raw=candidate.parse(dict(candidate_hash=feedback['candidate_hash'],replacements=[fixed],sections={},reason='Говорил c, а не b.'))
    assert any(w['code']=='semantic_reinterpretation' and w['source_ids']==['tell'] for w in raw.warnings)


def test_new_jobs_and_recorded_retry_regeneration_keep_distinct_versions(tmp_path):
    import json
    from unittest.mock import patch
    from backend.repositories.preparation import Repository
    from test_integrated_repair247 import seed, archived, CONFIG
    with patch('backend.runtime_v3.player_actions.EXTRACTION_VERSION',5):
        repo=Repository(tmp_path/'versions.sqlite');sid=seed(repo,archived('knowledge'))['save']
    regenerated=repo.begin_job(sid,'','regenerate',CONFIG)
    job=repo.get_job(regenerated)
    assert json.loads(job['config_json'])['_extraction_contract']==5
    repo.job_progress(regenerated,'error',narrative='Авторский текст.',complete=True,error='Authored retry boundary')
    repo.retry_job(regenerated,dict(CONFIG,_extraction_contract=6,_extraction_transport='injected'))
    config=json.loads(repo.get_job(regenerated)['config_json'])
    assert config['_extraction_contract']==5 and config['_extraction_transport']=='chat_json_object'
    repo.job_progress(regenerated,'stopped')
    stopped=repo.get_job(regenerated)
    repo.abandon_job(sid,regenerated,stopped['revision'],stopped['attempt_epoch'])
    ordinary=repo.begin_job(sid,'Осматриваюсь.','turn',CONFIG)
    assert json.loads(repo.get_job(ordinary)['config_json'])['_extraction_contract']==6


def test_unrelated_optional_annotation_does_not_block_valid_route():
    s,p=fixture();p['choices']='bad optional suggestions';p['scene_actions']={'invalid':'annotation'}
    p['continuity_beats']=[{'kind':'not-a-beat'}]
    result=resolve(s,p)
    assert result.state['characters']['a']['location_id']=='park'
    assert not result.choices
    assert any(w['section']=='scene_actions' and w['action']=='drop_section' for w in result.warnings)


def test_v6_unchanged_domains_receive_internal_metadata_defaults():
    s=state();p=dict(scene=dict(elapsed_minutes=1),scene_steps=[],
        life_changes=[dict(id='b',life_status='dead',assertion='established')],
        promotions=[dict(id='newcomer',name='Лада',fields={})])
    result=resolve(s,p,'')
    assert result.state['characters']['b']['life_status']=='dead'
    assert result.state['characters']['newcomer']['display_name']=='Лада'
    assert 'newcomer' in result.pending_reviews
    assert any(row['kind']=='npc_identity_created' and row['evidence']=='' for row in result.history['state_changes'])


def test_v6_keeps_existing_domain_budgets():
    s=state();p=dict(scene={},scene_steps=[],births=[{}]*25)
    with pytest.raises(StructuralDeltaError):resolve(s,p,'')


def test_unselected_decision_diagnostic_targets_original_finding():
    s=state();p=dict(scene={},scene_steps=[],agency_findings=[dict(narrative_evidence='Он согласился.',classification='unauthorized_choice')])
    with pytest.raises(StructuralDeltaError) as exc:resolve(s,p,'Осматриваюсь.')
    row=exc.value.diagnostics('validation')[0]
    assert row['code']=='narrative_agency_conflict' and row['path']=='agency_findings[0]'
    assert row['action']=='reauthor_narrative'


def test_possession_and_development_keep_linked_sources_without_duplicate_quotes():
    from test_possessions import state as possession_state, delta
    from test_personality import setup, profile
    s=possession_state();actor=s['camera']['controlled_actor_id'];player='Забираю своё семейное кольцо.'
    row=delta(s,transition='voluntary',decision_actor_id=actor,updates=dict(owner_id=actor,holder_id=actor,location_id=None,status='available'))
    p=dict(scene=dict(elapsed_minutes=1),scene_steps=[dict(id='event',kind='occurrence',actor_ids=[actor],fact_ids=[row['fact_id']],text='Забрал кольцо.',input_source=dict(quote=player,meaning='preserved'))],
        facts=[dict(id=row['fact_id'],text='Кольцо у владельца.',character_ids=[actor],visibility='secret')],possession_deltas=[row])
    result=resolve(s,p,player)
    assert result.state['possessions']['ring']['holder_id']==actor
    assert result.state['knowledge']==s['knowledge']
    bad=deepcopy(p);bad['scene_steps'][0].pop('input_source')
    with pytest.raises(StructuralDeltaError):resolve(s,bad,player)
    s=setup()['world_state'];s['camera'].update(controlled_actor_id='b',present_character_ids=['b'])
    s['characters']['b']['location_id']=s['camera']['location_id'];player='Я спокойно объясняю свою позицию.'
    p=dict(scene=dict(elapsed_minutes=1),scene_steps=[dict(id='source',kind='occurrence',actor_ids=['b'],text='Объяснила позицию.',input_source=dict(quote=player,meaning='preserved'))],
        development_evidence=[dict(id='proof',actor_id='b',source_event_id='source',meaning='Отстаивает границы',kind='behavior',assertion='completed')])
    result=resolve(s,p,player)
    assert len(profile(result.state)['evidence'])==1
    assert next(iter(profile(result.state)['evidence'].values()))['player_owned']


def test_targeted_repair_can_declare_missing_destination_without_rewriting_route():
    import json
    from backend.runtime_v3.scene_repair import SceneCandidate
    s,p=fixture();p['scene_steps']=p['scene_steps'][1:2];p['scene_steps'][0]['endpoint']='new-place'
    candidate=SceneCandidate(s,'Пришёл в новое место.',INPUT,1);raw=candidate.parse(p)
    with pytest.raises(StructuralDeltaError) as exc:
        StateResolver(s,'Пришёл в новое место.',INPUT,**resolver_options(s,INPUT,contract_version=6)).resolve(raw)
    info=json.loads(candidate.feedback(exc.value.diagnostics('repair'),p))
    repaired=candidate.parse(dict(candidate_hash=info['candidate_hash'],replacements=[],
        sections={'locations':[dict(id='new-place',name='Новое место')]},reason='Пропущено объявление установленного места.'))
    result=StateResolver(s,'Пришёл в новое место.',INPUT,**resolver_options(s,INPUT,contract_version=6)).resolve(repaired)
    assert result.state['characters']['a']['location_id']=='new-place'
    assert repaired.semantic_candidate['scene_steps']==p['scene_steps']


def test_targeted_repair_cannot_change_independent_record_in_same_section():
    import json
    from backend.runtime_v3.scene_repair import SceneCandidate
    s=state();p=dict(scene={},scene_steps=[dict(id='info',kind='information',source_actor_id='b',medium='conversation',
        text='Сообщил.',claims=[dict(fact_id='affected',assertion='testimony',status='known',perceived_by=['a'])])],
        facts=[dict(id='affected',text='Первое'),dict(id='independent',text='Второе')])
    candidate=SceneCandidate(s,'Проза','',1);candidate.parse(p)
    info=json.loads(candidate.feedback([dict(section='facts',index=0,code='fact_invalid')],p))
    assert info['scope']['record_keys']['facts']==['affected']
    changed=deepcopy(p['facts']);changed[1]['text']='Подменено'
    with pytest.raises(StructuralDeltaError) as exc:
        candidate.parse(dict(candidate_hash=info['candidate_hash'],replacements=[],sections={'facts':changed},reason='Недопустимая подмена.'))
    assert exc.value.code=='scene_repair_scope'


def test_scoped_section_edit_retains_unmentioned_neighbor_and_logs_withdrawal():
    import json
    from backend.runtime_v3.scene_repair import SceneCandidate,record_key
    s=state();p=dict(scene={},scene_steps=[],facts=[dict(id='bad',text='Черновик'),dict(id='other',text='Сохранить')])
    candidate=SceneCandidate(s,'Проза','',1);candidate.parse(p)
    info=json.loads(candidate.feedback([dict(section='facts',index=0,code='fact_invalid')],p))
    raw=candidate.parse(dict(candidate_hash=info['candidate_hash'],replacements=[],sections={'facts':[dict(id='bad',text='Уточнено')]},reason='Исправлено исходное утверждение.'))
    assert raw.semantic_candidate['facts']==[dict(id='bad',text='Уточнено'),p['facts'][1]]
    candidate=SceneCandidate(s,'Проза','',1);candidate.parse(p)
    info=json.loads(candidate.feedback([dict(section='facts',index=0,code='fact_invalid')],p))
    raw=candidate.parse(dict(candidate_hash=info['candidate_hash'],replacements=[],sections={},reason='Первое утверждение было только предположением.',
        withdrawals=[dict(section='facts',record_key='bad',reason='Не установленный факт.')]))
    assert raw.semantic_candidate['facts']==[p['facts'][1]]
    assert any(w.get('record_key')=='bad' and w['code']=='semantic_reinterpretation' for w in raw.warnings)


def test_repair_combines_multiple_record_diagnostics_without_unlocking_neighbors():
    import json
    from backend.runtime_v3.scene_repair import SceneCandidate
    s=state();p=dict(scene={},scene_steps=[],facts=[
        dict(id='first',text='Первый черновик'),dict(id='second',text='Второй черновик'),
        dict(id='independent',text='Сохранить')])
    candidate=SceneCandidate(s,'Проза','',1);candidate.parse(p)
    info=json.loads(candidate.feedback([
        dict(section='facts',index=0,code='fact_invalid'),
        dict(section='facts',index=1,code='fact_invalid')],p))
    assert info['scope']['record_keys']['facts']==['first','second']
    edits=[dict(id='first',text='Первое исправлено'),dict(id='second',text='Второе исправлено')]
    raw=candidate.parse(dict(candidate_hash=info['candidate_hash'],replacements=[],
        sections={'facts':edits},reason='Уточнены оба исходных утверждения.'))
    assert raw.semantic_candidate['facts']==edits+[p['facts'][2]]
