"""Free compiler and real Preparation/SQLite integration tests for author contract 1."""
import json
from copy import deepcopy
from unittest.mock import patch
import pytest

from backend.services.world_authoring import Document, AuthorBrief, VERSION
from backend.services.world_authoring_compiler import compile_document, CompileError
from backend.services.world_authoring_pipeline import source_sections
from test_api import api, REMOTE
from test_world_generation import wait


def institute():
    from pathlib import Path
    return json.loads((Path(__file__).parent / "fixtures/world_authoring/institute.json").read_text())


def family():
    from pathlib import Path
    return json.loads((Path(__file__).parent / "fixtures/world_authoring/family.json").read_text())


def orbital():
    from pathlib import Path
    return json.loads((Path(__file__).parent / "fixtures/world_authoring/orbital.json").read_text())


@pytest.mark.parametrize('fixture', [institute, family, orbital])
def test_compiler_is_deterministic_lossless_and_does_not_mutate(fixture):
    document=fixture(); original=deepcopy(document)
    with patch('socket.socket', side_effect=AssertionError('compiler network')):
        first=compile_document(document)
        second=compile_document(document, first.id_map)
    assert first==second and document==original
    assert first.transformations
    cards=first.snapshot['character_cards']
    for person in document['characters']:
        card=next(c for c in cards if c['name']==person['name'])
        if person.get('biography'):assert card['fields']['Биография']==person['biography']
        if person.get('age'):assert card['fields']['Возраст']==person['age']
    assert all(c['birth_date'] is None for c in first.snapshot['world_state']['characters'].values())


def test_asymmetric_feelings_knowledge_and_time_precision():
    result=compile_document(family());state=result.snapshot['world_state']
    assert len(state['relationships'])==1
    assert next(iter(state['relationships'].values()))['dimensions']=={'respect':40.}
    assert len(state['knowledge'])==2
    assert result.snapshot['initial_history']['legacy'][0]['status']=='unknown'
    event=result.snapshot['initial_history']['events'][0]
    assert event['time_description']=='Вчера вечером' and 'minute' not in event
    from backend.runtime_v3.calendar import current_time
    assert current_time(state)['weekday']==4 and state['meta']['world_time']==360


@pytest.mark.parametrize('mutation,path', [
    (lambda d:d['characters'][0].update(location='missing'), 'location'),
    (lambda d:d['locations'][0].update(parent='lab'), 'locations'),
    (lambda d:d['characters'][0].update(goals=[dict(key='g',text='Согласиться на предложение')]), 'goals'),
    (lambda d:d['opening']['time'].pop('clock'), 'opening/time'),
])
def test_actionable_technical_errors(mutation,path):
    document=institute();mutation(document)
    with pytest.raises(CompileError,match=path) as exc:compile_document(document)
    assert exc.value.diagnostic['action']


def test_schema_is_authoring_only_and_analysis_cannot_invent():
    schema=json.dumps(Document.model_json_schema())
    for name in ('WorldStateV3','source_turn','source_sequence','revision','AppearanceFeature','ConstraintRule'):
        assert name not in schema
    with pytest.raises(ValueError):AuthorBrief.model_validate({'entities':[dict(key='x',name='X',kind='character')]})
    with pytest.raises(ValueError):Document.model_validate({**family(),'feelings':[dict(key='x',source='son',target='father',levels={'trust':.95})]})


def test_source_split_only_when_needed_and_is_lossless():
    schema=AuthorBrief.model_json_schema();text='Подробная идея.\n'*600
    assert source_sections(text,131072,4000,schema)==[text]
    chunks=source_sections(text,12000,2000,schema)
    assert len(chunks)>1 and ''.join(chunks)==text


def provider(document,calls,fail=None):
    def stream(**kw):
        stage=kw['messages'][0]['content'].split('\nStage: ')[1].split('\n')[0]
        data=json.loads(kw['messages'][-1]['content']);calls.append(stage)
        if fail:fail(stage)
        if stage=='author_brief':result={'entities':[],'observations':[],'ambiguities':[]}
        elif stage=='author_document':result=document
        elif stage in ('author_plan', 'author_plan_page'):
            from backend.services.world_authoring import Sections
            result={k:document[k] for k in ('world','opening')}
            result['records']=[dict(section=s,key=r['key'],summary=r.get('name',r.get('text','Accepted circumstance')))
                for s in Sections.model_fields for r in document.get(s,[])]
            if stage=='author_plan_page':
                known={(r['section'],r['key']) for r in data['registered_records']}
                pending=[r for r in result['records'] if (r['section'],r['key']) not in known]
                result['records']=pending[:data['max_records']]
                result['complete']=len(pending)<=data['max_records']
                if known:result.update(world=None,opening=None)
        elif stage=='author_batch':
            result={}
            for row in data['assigned_records']:
                result.setdefault(row['section'],[]).append(next(r for r in document[row['section']] if r['key']==row['key']))
        else:raise AssertionError(stage)
        yield json.dumps(result,ensure_ascii=False)
    return stream


def submit(client,large=False):
    wid=client.post('/api/workspaces',json={'name':'Author document'}).json()['id']
    response=client.post(f'/api/workspaces/{wid}/draft/generate',json=dict(task='world_staged',text='Переезд и работа в НИИ.',revision=0,
        creation={'cast_preset':'custom','core_npcs':1,'secondary_npcs':0},
        config={**REMOTE,'context_length':131072,'max_tokens':3000 if large else 16000},api_key='fixture'))
    assert response.status_code==200,response.text
    return wid,response.json()['id']


@pytest.mark.parametrize('large',[False,True])
def test_real_worker_compile_confirm_reload(api,large):
    client,app=api;calls=[]
    with patch('backend.services.preparation.chat_stream',side_effect=provider(institute(),calls)):
        wid,jid=submit(client,large);done=wait(client,jid)
    assert done['status']=='saved',done
    repo=app.state.repository
    assert repo.generation_resources(jid,['prompt'])['prompt']['version']==VERSION
    assert 'review' not in calls
    assert ('author_batch' in calls)==large
    draft=repo.draft(wid,True)
    saved=repo.confirm_draft(wid,draft['revision'],draft['version_id'])
    snapshot=repo.get_snapshot(saved['save'])
    assert len(snapshot['world_state']['characters'])==2
    assert snapshot['campaign']['initial_world']['brief']=='Переезд и работа в НИИ.'
    assert 'source_document' not in json.dumps(repo.draft(wid),ensure_ascii=False)


def test_provider_failure_preserves_analysis_and_explicit_resume(api):
    client,app=api;calls=[]
    def fail(stage):
        if stage=='author_document':raise RuntimeError('injected')
    with patch('backend.services.preparation.chat_stream',side_effect=provider(institute(),calls,fail)):
        wid,jid=submit(client);failed=wait(client,jid)
    assert failed['status']=='failed'
    before=app.state.repository.inspect_generation_checkpoint(jid,'author_brief',True)['artifact_version']
    with patch('backend.services.preparation.chat_stream',side_effect=provider(institute(),calls)):
        response=client.post(f'/api/jobs/{jid}/generation/resume',json={'revision':failed['generation']['revision']})
        assert response.status_code==200,response.text
        assert wait(client,jid)['status']=='saved'
    assert calls.count('author_brief')==1
    assert app.state.repository.inspect_generation_checkpoint(jid,'author_brief',True)['artifact_version']==before


def test_author_document_editor_recompiles_and_detects_compiled_edits(api):
    client,app=api
    with patch('backend.services.preparation.chat_stream',side_effect=provider(institute(),[])):
        wid,jid=submit(client);assert wait(client,jid)['status']=='saved'
    endpoint=f'/api/workspaces/{wid}/draft'
    view=client.get(endpoint+'/canonical?author=true').json()
    assert view['contract']==VERSION and not view['compiled_conflict']
    characters=deepcopy(view['values']['characters'])
    characters[0]['biography']='Авторская биография, сохранённая целиком.'
    response=client.patch(endpoint,json=dict(revision=view['revision'],operation='patch',kind='canonical',field='characters',value=characters,warnings_ack=True))
    assert response.status_code==200,response.text
    assert client.get(endpoint+'/canonical?author=true').json()['values']['characters'][0]['biography']==characters[0]['biography']
    draft=app.state.repository.draft(wid,True)
    saved=app.state.repository.confirm_draft(wid,draft['revision'],draft['version_id'])
    card=app.state.repository.get_snapshot(saved['save'])['character_cards'][0]
    assert card['fields']['Биография']==characters[0]['biography']
    from backend.services.initial_world_editor import patch as edit
    from backend.services.initial_world_v2 import normalize
    changed=normalize(draft['state']).snapshot
    next(iter(changed['world_state']['characters'].values()))['physical_state']='Ручная правка Runtime'
    with pytest.raises(ValueError,match='author/conflict'):edit(changed,'characters',characters)


def test_new_contract_start_turn_reload_regenerate_rollback_and_branch(api):
    from test_temporal_guard import run
    from backend.repositories.preparation import Repository
    client,app=api;repo=app.state.repository
    document=institute()
    document['commitments']=[dict(key='meeting',origin='explicit',description='Начало встречи',participants=['newcomer'],
        time=dict(day_offset=0,clock='09:05'))]
    with patch('backend.services.preparation.chat_stream',side_effect=provider(document,[])):
        wid,jid=submit(client);assert wait(client,jid)['status']=='saved'
    draft=repo.draft(wid,True);sid=repo.confirm_draft(wid,draft['revision'],draft['version_id'])['save']
    initial=repo.get_snapshot(sid)
    assert run(repo,sid,1,kind='start')[0]['status']=='saved'
    started=repo.get_snapshot(sid)
    assert run(repo,sid,2)[0]['status']=='saved'
    accepted=repo.get_snapshot(sid);turn=repo.list_turns(sid)[-1]
    assert run(repo,sid,10080,kind='regenerate')[0]['status']=='error'
    assert repo.get_snapshot(sid)==accepted
    repo=Repository(repo.path)
    assert run(repo,sid,1,kind='regenerate')[0]['status']=='saved'
    repo.select_variant(sid,turn['id'],turn['active_variant_id'],repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)==accepted
    repo.rollback_last(sid);assert repo.get_snapshot(sid)==started
    assert run(repo,sid,4)[0]['status']=='saved'
    boundary=repo.get_snapshot(sid)
    assert boundary['world_state']['meta']['world_time']==545
    assert run(repo,sid,1)[0]['status']=='error'
    assert Repository(repo.path).get_snapshot(sid)==boundary
    assert boundary['world_state']['meta']['calendar']==initial['world_state']['meta']['calendar']


@pytest.mark.parametrize('fault',['json','output','provider'])
def test_failed_unit_has_bounded_attempts(api,fault):
    from llm import OutputLimitReached
    client,app=api;calls=[]
    base=provider(institute(),calls)
    def stream(**kw):
        stage=kw['messages'][0]['content'].split('\nStage: ')[1].split('\n')[0]
        if stage=='author_document':
            calls.append(stage)
            if fault=='json':yield '{';return
            if fault=='output':raise OutputLimitReached('fixture limit')
            raise RuntimeError('fixture provider')
        yield from base(**kw)
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        wid,jid=submit(client);done=wait(client,jid)
    assert done['status']=='failed'
    assert calls.count('author_document')==(2 if fault=='json' else 1)
    assert app.state.repository.inspect_generation_checkpoint(jid,'author_brief',True)['status']=='completed'


def test_dense_relations_do_not_have_a_response_cap_on_combined_document():
    d=institute();d['characters']=[dict(key=f'p{i}',name=f'Персонаж {i}',location='lab') for i in range(30)]
    d['roles']=[]
    d['opening'].update(protagonist='p0',controlled='p0',pov='p0',present=['p0'])
    d['feelings']=[dict(key=f'r{i}_{j}',source=f'p{i}',target=f'p{j}',levels={'trust':'high'}) for i in range(30) for j in range(30) if i!=j]
    result=compile_document(d)
    assert len(result.snapshot['world_state']['relationships'])==870


def test_pause_author_edit_restart_reuses_accepted_batches(api):
    from backend.repositories.preparation import Repository
    from backend.services.preparation import Preparation, Handle
    from backend.services.world_generation import run
    client,app=api;repo=app.state.repository;calls=[]
    commit=repo.commit_generation_unit
    def pause(jid,token,unit,payload):
        result=commit(jid,token,unit,payload)
        if unit=='author_document':repo.generation_control(jid,'pause')
        return result
    with patch.object(repo,'commit_generation_unit',side_effect=pause),patch('backend.services.preparation.chat_stream',side_effect=provider(institute(),calls)):
        wid,jid=submit(client,True);done=wait(client,jid)
    assert done['status']=='paused'
    before={u['unit_id']:repo.inspect_generation_checkpoint(jid,u['unit_id'],True)['artifact_version'] for u in done['generation']['units'] if u['status']=='completed'}
    cp=repo.inspect_generation_checkpoint(jid,'author_document',True)
    response=client.patch(f'/api/workspaces/{wid}/draft',json=dict(operation='patch',kind='checkpoint',generation_job=jid,
        generation_unit='author_document',artifact_version=cp['artifact_version'],revision=done['generation']['revision'],
        field='/characters/0/biography',value='Исправлено автором.',preview=False))
    assert response.status_code==200,response.text
    repo=Repository(repo.path)
    repo.generation_control(jid,'resume',response.json()['revision'])
    count=len(calls)
    run(Preparation(repo),jid,json.loads(repo.preparation_job(jid)['config_json']),'fixture',Handle(),None,provider(institute(),calls))
    assert repo.preparation_job(jid)['status']=='saved'
    assert len(calls)==count
    for key,version in before.items():
        if key!='author_document':assert repo.inspect_generation_checkpoint(jid,key,True)['artifact_version']==version
    doc=repo.generation_resources(jid,['author_document'])['author_document']
    assert doc['characters'][0]['field_origins']['biography']=='explicit'


def test_lifecycle_fields_are_explicit_and_absence_creates_no_records():
    from backend.runtime_v3.life import capabilities
    base=compile_document(institute())
    assert not base.snapshot['world_state']['contacts']
    assert not base.snapshot['world_state']['conditions']
    d=institute();d['characters'][0].update(developmental_stage='adult', reproductive_capability='neither',
        capabilities={'can_speak':False}, identity_components={'chosen':'Имя'},
        name_changes=[dict(previous='Старое',current='Новое',date='2020-01-01',description='Смена имени задолго до приезда')])
    d['conditions']=[dict(key='injury',actor='newcomer',description='Повреждена нога',effects={'can_move':False},duration='temporary')]
    d['contacts']=[dict(key='colleague',owner='newcomer',character='mentor',label='Коллега',address='internal:42',provenance='Передал лично')]
    result=compile_document(d);state=result.snapshot['world_state'];cid=result.id_map['characters/newcomer']
    assert capabilities(state,cid)['can_move'] is False
    assert capabilities(state,cid)['can_speak'] is False
    assert next(iter(state['contacts'].values()))['character_id']==result.id_map['characters/mentor']
    change=next(r for r in result.snapshot['initial_history']['legacy'] if r['kind']=='identity_change')
    assert change['date']=='2020-01-01' and 'minute' not in change
    assert not state['pregnancies'] and not state['reproductive_events']


def test_nested_transformation_map_has_every_leaf_and_specific_targets():
    from backend.services.author_transformations import leaves
    from backend.services.world_authoring import Sections
    d=institute();d['characters'][0]['goals']=[dict(key='job',origin='explicit',text='Работать в НИИ')]
    d['feelings']=[dict(key='r',source='newcomer',target='mentor',levels={'trust':'high','respect':'unknown'})]
    result=compile_document(d);doc=Document.model_validate(d)
    lookup={r['source']:r for r in result.transformations}
    for section in Sections.model_fields:
        for row in getattr(doc,section):
            for suffix,_ in leaves(row.model_dump()):assert section+'/'+row.key+suffix in lookup
    assert lookup['characters/newcomer/goals/0/text']['target'].endswith('/goals/0/text')
    assert lookup['characters/newcomer/goals/0/text']['origin']=='explicit'
    assert lookup['feelings/r/levels/trust']['target'].endswith('/dimensions/trust')
    assert lookup['feelings/r/levels/respect']['method']=='unknown_omitted'
    assert lookup['opening/time/clock']['target']=='world_state/meta/world_time'


def test_combined_analysis_has_no_per_response_limit():
    from backend.services.world_authoring_pipeline import combine_briefs
    parts=[dict(entities=[dict(key=f'p{i}_{j}',origin='explicit',name=str(j),kind='character') for j in range(150)],observations=[],ambiguities=[]) for i in range(3)]
    assert len(combine_briefs(parts)['entities'])==450


def test_paged_plan_restart_does_not_repeat_accepted_pages(api):
    client,app=api;repo=app.state.repository;calls=[]
    base=provider(institute(),calls)
    def broken(**kw):
        data=json.loads(kw['messages'][-1]['content'])
        if '\nStage: author_plan_page' in kw['messages'][0]['content'] and data['registered_records']:
            raise RuntimeError('interrupted page')
        yield from base(**kw)
    with patch('backend.services.preparation.chat_stream',side_effect=broken):
        wid,jid=submit(client,True);failed=wait(client,jid)
    assert failed['status']=='failed'
    cp=repo.inspect_generation_checkpoint(jid,'author_plan_page_0_0',True)
    assert cp['status']=='completed' and len(cp['artifact']['records'])<=4
    with patch('backend.services.preparation.chat_stream',side_effect=base):
        response=client.post(f'/api/jobs/{jid}/generation/resume',json={'revision':failed['generation']['revision']})
        assert response.status_code==200,response.text
        assert wait(client,jid)['status']=='saved'
    assert repo.inspect_generation_checkpoint(jid,'author_plan_page_0_0',True)['artifact_version']==cp['artifact_version']


def test_long_original_is_processed_losslessly_across_requests(api):
    client,app=api;calls=[];seen=[]
    original=('Detailed user material with explicit characteristics preserved.\n'*1500)
    base=provider(institute(),calls)
    def stream(**kw):
        stage=kw['messages'][0]['content'].split('\nStage: ')[1].split('\n')[0]
        data=json.loads(kw['messages'][-1]['content']);seen.append((stage,data))
        yield from base(**kw)
    wid=client.post('/api/workspaces',json={'name':'Long original'}).json()['id']
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        response=client.post(f'/api/workspaces/{wid}/draft/generate',json=dict(task='world_staged',text=original,revision=0,
            creation={'cast_preset':'custom','core_npcs':1,'secondary_npcs':0},
            config={**REMOTE,'context_length':32768,'max_tokens':3000},api_key='fixture'))
        assert response.status_code==200,response.text
        jid=response.json()['id'];done=wait(client,jid)
    assert done['status']=='saved',done
    pieces=[data['source'] for stage,data in seen if stage=='author_brief']
    assert len(pieces)>1 and ''.join(pieces)==original
    batches={}
    for stage,data in seen:
        if stage=='author_batch':
            key=tuple(r['key'] for r in data['assigned_records'])
            batches.setdefault(key,[]).append(data['original_source'])
    assert batches and all(''.join(parts)==original for parts in batches.values())
    snapshot=app.state.repository.generation_resources(jid,['assembled'])['assembled']
    assert snapshot['campaign']['initial_world']['brief']==original


@pytest.mark.parametrize('change',['add','remove','edit'])
def test_replan_after_entity_changes_preserves_journal(api,change):
    client,app=api;repo=app.state.repository;calls=[];document=institute()
    commit=repo.commit_generation_unit
    def pause(jid,token,unit,payload):
        result=commit(jid,token,unit,payload)
        if unit=='author_document':repo.generation_control(jid,'pause')
        return result
    with patch.object(repo,'commit_generation_unit',side_effect=pause),patch('backend.services.preparation.chat_stream',side_effect=provider(document,calls)):
        wid,jid=submit(client,True);done=wait(client,jid)
    assert done['status']=='paused'
    cp=repo.inspect_generation_checkpoint(jid,'author_plan',True)
    records=deepcopy(cp['artifact']['records'])
    if change=='add':
        document['locations'].append(dict(key='park',name='Парк'))
        records.append(dict(section='locations',key='park',summary='Парк',references=[]))
    elif change=='remove':
        document['roles']=[];records=[r for r in records if r['section']!='roles']
    else:
        document['characters'][1]['biography']='Принятая новая биография.'
        next(r for r in records if r['key']=='mentor')['summary']='Принятая новая биография.'
    response=client.patch(f'/api/workspaces/{wid}/draft',json=dict(operation='patch',kind='checkpoint',generation_job=jid,
        generation_unit='author_plan',artifact_version=cp['artifact_version'],revision=done['generation']['revision'],
        field='/records',value=records,preview=False))
    assert response.status_code==200,response.text
    with patch('backend.services.preparation.chat_stream',side_effect=provider(document,calls)):
        resumed=client.post(f'/api/jobs/{jid}/generation/resume',json={'revision':response.json()['revision']})
        assert resumed.status_code==200,resumed.text
        finished=wait(client,jid)
    assert finished['status']=='saved',finished
    with repo.connect() as db:
        if change!='add':
            assert db.execute("SELECT count(*) FROM preparation_units WHERE job_id=? AND status='retired'",(jid,)).fetchone()[0]>0
        assert db.execute("SELECT count(*) FROM document_versions WHERE owner=? AND kind='generation_plan'",(jid,)).fetchone()[0]>=2
    result=repo.generation_resources(jid,['author_document'])['author_document']
    if change=='add':assert any(r['key']=='park' for r in result['locations'])
    elif change=='remove':assert not result['roles']
    else:assert result['characters'][1]['biography']=='Принятая новая биография.'


def test_captured_first_planner_revision_still_resumes(api):
    from backend.services import world_authoring_pipeline as pipeline
    capture=pipeline.capture
    def old_capture(*args):
        value=capture(*args);value['prompt'].pop('planning_version')
        value['prompt']['schemas'].pop('author_plan_page')
        return value
    client,app=api;calls=[]
    with patch.object(pipeline,'capture',side_effect=old_capture),patch('backend.services.preparation.chat_stream',side_effect=provider(institute(),calls)):
        wid,jid=submit(client,True);done=wait(client,jid)
    assert done['status']=='saved',done
    assert 'author_plan' in calls and 'author_plan_page' not in calls


def test_replan_refuses_to_discard_protected_entity(api):
    client,app=api;repo=app.state.repository
    commit=repo.commit_generation_unit
    def pause(jid,token,unit,payload):
        result=commit(jid,token,unit,payload)
        if unit=='author_document':repo.generation_control(jid,'pause')
        return result
    with patch.object(repo,'commit_generation_unit',side_effect=pause),patch('backend.services.preparation.chat_stream',side_effect=provider(institute(),[])):
        wid,jid=submit(client,True);done=wait(client,jid)
    batch=next(u['unit_id'] for u in done['generation']['units'] if u['stage']=='author_batch')
    cp=repo.inspect_generation_checkpoint(jid,batch,True)
    response=client.patch(f'/api/workspaces/{wid}/draft',json=dict(operation='patch',kind='checkpoint',generation_job=jid,
        generation_unit=batch,artifact_version=cp['artifact_version'],revision=done['generation']['revision'],
        field='/characters/0/biography',value='Protected biography',preview=False))
    assert response.status_code==200,response.text
    revision=response.json()['revision'];plan=repo.inspect_generation_checkpoint(jid,'author_plan',True)
    records=deepcopy(plan['artifact']['records']);records[0]['summary']='Changed assignment'
    response=client.patch(f'/api/workspaces/{wid}/draft',json=dict(operation='patch',kind='checkpoint',generation_job=jid,
        generation_unit='author_plan',artifact_version=plan['artifact_version'],revision=revision,
        field='/records',value=records,preview=False))
    assert response.status_code==200,response.text
    with patch('backend.services.preparation.chat_stream',side_effect=provider(institute(),[])):
        client.post(f'/api/jobs/{jid}/generation/resume',json={'revision':response.json()['revision']})
        failed=wait(client,jid)
    assert failed['status']=='failed' and 'protected edits conflict' in failed['error']
    assert repo.generation_field_locks(jid,batch)['/characters/0/biography']=='Protected biography'


def test_explicit_pregnancy_compiles_without_randomness_or_knowledge_inference():
    from backend.runtime_v3.calendar import current_time
    d=institute();d['opening']['time']={'date':'2030-06-01','clock':'09:00'}
    d['pregnancies']=[dict(key='ongoing',gestational_actor='mentor',impregnating_actor='newcomer',parents=['mentor'],
        conception_earliest_date='2030-01-01',conception_latest_date='2030-01-03',
        due={'date':'2030-10-01','clock':'09:00','description':'Явно выбранная игровая граница'},
        children=[{'key':'child','sex':'female'}],description='Заданная беременность; окружающие не осведомлены.')]
    original=deepcopy(d);first=compile_document(d);second=compile_document(d,first.id_map)
    assert first==second and d==original
    state=first.snapshot['world_state'];pregnancy=next(iter(state['pregnancies'].values()))
    assert pregnancy['conception_minute'] is None
    assert pregnancy['earliest_minute']==0 and pregnancy['latest_minute']==3*1440-1
    assert len(state['characters'])==2 and not state['knowledge']
    assert current_time(state)['date']=='2030-06-01' and current_time(state)['time']=='09:00'
    assert state['scheduled_events'][pregnancy['id']]['due_minute']==pregnancy['due_minute']
    d['facts']=[dict(key='known-pregnancy',text='Беременность установлена.',secret=True,participants=['mentor'])]
    d['knowledge']=[dict(key='knows-pregnancy',actor='mentor',fact='known-pregnancy',status='known',evidence='Личное наблюдение')]
    d['pregnancies'][0]['fact']='known-pregnancy'
    known=compile_document(d);pregnancy=next(iter(known.snapshot['world_state']['pregnancies'].values()))
    assert pregnancy['fact_id']==known.id_map['facts/known-pregnancy']
    assert any(k['fact_id']==pregnancy['fact_id'] for k in known.snapshot['world_state']['knowledge'].values())
    d['pregnancies'][0]['children'][0]['sex']=None
    with pytest.raises(CompileError,match='исход пола'):compile_document(d)


def test_closed_social_phases_keep_dates_and_invalid_condition_is_rejected():
    d=institute();d['roles'][0].update(status='closed',since_date='2020-01-01',until_date='2021-01-01',outcome='Перевод')
    d['objective_relations']=[dict(key='past-job',source='newcomer',target='mentor',kind='coworker',status='closed',
        since_date='2020-01-01',until_date='2021-01-01',outcome='ended')]
    state=compile_document(d).snapshot['world_state']
    assert next(iter(state['roles'].values()))['until_date']=='2021-01-01'
    assert next(iter(state['objective_relations'].values()))['status']=='closed'
    d['conditions']=[dict(key='bad',actor='mentor',description='Не может даровать способности',effects={'can_act':True})]
    with pytest.raises(ValueError,match='capabilities|способност'):compile_document(d)


def test_prior_knowledge_map_distinguishes_multiple_historical_states():
    d=family();prior=next(k for k in d['knowledge'] if not k.get('current',True))
    another={**deepcopy(prior),'key':'second-prior','status':'suspected'};d['knowledge'].append(another)
    result=compile_document(d)
    entries={r['source']:r for r in result.transformations}
    assert entries['knowledge/'+prior['key']+'/status']['target']!=entries['knowledge/second-prior/status']['target']
