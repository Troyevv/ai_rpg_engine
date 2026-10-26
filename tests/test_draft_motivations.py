"""Draft/Runtime Motivation compatibility; no provider reasoning needed to fix types."""
import hashlib
import json
from copy import deepcopy
from unittest.mock import patch
import pytest
from test_initial_draft_v4 import rich, REMOTE, SHORT, api, wait_job
from backend.services import draft_initial as initial, draft_world as draft, draft_completeness as review
from backend.runtime_v3.models import Character, Motivation, identity
from backend.repositories.preparation import Repository

FIELDS=('goals','intentions','obligations')


def motivated():
    state=rich();cid=state['protagonist_id'];actor=state['world']['characters'][cid]
    state['world']['events']['motivation_origin']=dict(id='motivation_origin',text='Событие авторской предыстории.',minute=0,participants=[cid],witnesses=[cid],fact_ids=[],player_observed=True,scene_id=None)
    for field,status in zip(FIELDS,('completed','blocked','superseded')):
        actor[field]=[Motivation(id=field+'_kept',text='Сохранённое '+field,status=status,
            evidence='Авторская предыстория',source_sequence=0,source_event_id='motivation_origin',
            due_minute=20000,revision=3,dependencies={'characters':[cid],'roles':['job'],'organizations':['apex']},
            review_required=['author_check'],reviewed_signature='recorded-signature').model_dump(),
            Motivation(id=field+'_active',text='Текущая '+field).model_dump()]
    return state,cid


def test_schema_normalization_projection_and_migration_use_one_contract():
    raw,cid=motivated();before=deepcopy(raw)
    schema=initial.prompt_schema()['properties']['world']['properties']['characters']['additionalProperties']
    for field in FIELDS:assert schema['properties'][field]['items']['properties']['dependencies']
    state,report=initial.inspect_candidate(raw);assert not report['errors'],report
    assert raw==before
    for field in FIELDS:
        assert state['world']['characters'][cid][field]==raw['world']['characters'][cid][field]
    assert state['world']['characters'][cid]['short_goal']=='Текущая goals'
    card=next(c for c in state['characters'] if c['id']==cid)
    assert card['fields']['Намерения']=='Текущая intentions'
    assert initial.normalize(state)==initial.normalize(initial.normalize(state))
    canonical=initial.canonical_check(state).snapshot['world_state']['characters'][cid]
    for field in FIELDS:assert canonical[field]==raw['world']['characters'][cid][field]
    changed=draft.patch(state,'campaign','','title','Другое название')
    for field in FIELDS:assert changed['world']['characters'][cid][field]==canonical[field]
    items=deepcopy(canonical['goals']);items[0]['text']='Исправленный текст'
    changed=draft.patch(changed,'actor',cid,'goals',items)
    assert changed['world']['characters'][cid]['goals']==items
    markdown=draft.export_markdown(changed)
    assert 'Исправленный текст [completed]' in markdown
    assert '[object Object]' not in markdown
    assert draft.exported_state(markdown)==draft.prepare(changed)
    assert draft.prepare(json.loads(json.dumps(changed)))==draft.prepare(changed)


@pytest.mark.parametrize('field',FIELDS)
def test_old_strings_have_stable_runtime_ids(field):
    state,cid=motivated();state['world']['characters'][cid][field]=['Первая строка','Вторая строка']
    result=draft.prepare(state)['world']['characters'][cid][field]
    assert [x['id'] for x in result]==[identity(field,cid,i,text) for i,text in enumerate(state['world']['characters'][cid][field])]
    expected=Character(id=cid,**{field:state['world']['characters'][cid][field]}).model_dump()[field]
    assert result==expected
    assert draft.prepare(draft.prepare(state))['world']['characters'][cid][field]==expected
    assert draft.patch(state,'actor',cid,field,['Новая строка'])['world']['characters'][cid][field][0]['text']=='Новая строка'


@pytest.mark.parametrize('field',FIELDS)
@pytest.mark.parametrize('invalid,suffix',[(17,'/0'),(None,'/0'),([], '/0'),({'id':'bad','text':17},'/0/text'),({'id':'bad','text':'x','status':'wrong'},'/0/status')])
def test_wrong_elements_have_exact_paths(field,invalid,suffix):
    state,cid=motivated();state['world']['characters'][cid][field]=[invalid]
    _,report=initial.inspect_candidate(state)
    expected=f'/world/characters/{cid}/{field}'+suffix
    assert expected in {e['path'] for e in report['diagnostics']},report
    assert all(e['path']!='/' for e in report['diagnostics'])
    with pytest.raises(initial.DraftErrors) as exc:draft.prepare(state)
    assert expected in {e['path'] for e in exc.value.errors}
    clean,_=motivated()
    with pytest.raises(initial.DraftErrors) as exc:draft.patch(clean,'actor',cid,field,[invalid])
    assert expected in {e['path'] for e in exc.value.errors}


@pytest.mark.parametrize('value',[None,{'text':'not a list'},'not a list',17])
def test_invalid_container_is_not_iterated_as_legacy_strings(value):
    state,cid=motivated();state['world']['characters'][cid]['goals']=value
    _,report=initial.inspect_candidate(state)
    assert report['diagnostics'][0]['path']==f'/world/characters/{cid}/goals'
    with pytest.raises(ValueError):Character(id=cid,goals=value)


def test_independent_bad_fields_and_duplicate_ids():
    state,cid=motivated();actor=state['world']['characters'][cid]
    actor['goals']=[17,None];actor['intentions']=[{'id':'x','text':False}]
    actor['obligations']=[{'id':'dup','text':'a'},{'id':'dup','text':'b'}]
    _,report=initial.inspect_candidate(state)
    assert {e['path'] for e in report['diagnostics']}=={f'/world/characters/{cid}/'+s for s in ('goals/0','goals/1','intentions/0/text','obligations/1/id')}


def test_saved_candidate_resume_editor_export_start_reload(api):
    client,app=api;repo=app.state.repository
    wid=client.post('/api/workspaces',json={'name':'Motivation recovery'}).json()['id'];url=f'/api/workspaces/{wid}/draft'
    raw,cid=motivated();expected=deepcopy(raw['world']['characters'][cid]);text=json.dumps(raw,ensure_ascii=False)
    cfg=dict(REMOTE,context_length=65536,_draft_task='world',_draft_input=SHORT)
    jid=repo.begin_preparation(wid,'draft_world',SHORT,cfg,0)
    repo.save_response_journal(jid,{'candidate_text':text,'responses':{'world':{'complete':True,'parts':[
        dict(text=text,offset=0,sha256=hashlib.sha256(text.encode()).hexdigest(),finish_reason='stop')]}},
        'errors':[{'path':'/','message':'goals: нужен список строк.','category':'validation_incomplete'}]})
    repo.save_draft_candidate(jid,raw,[{'path':'/','message':'goals: нужен список строк.','category':'validation_incomplete'}])
    repo.preparation_progress(jid,'','error')
    d=client.get(url+'?author=true').json();assert not d['validation']['errors']
    # An old candidate becomes technically readable after updating, without erasing metadata.
    def reviewer(**kw):
        assert kw['messages'][0]['content'].startswith(review.MARKER)
        candidate=json.loads(kw['messages'][1]['content'])['candidate']
        for field in FIELDS:assert candidate['world']['characters'][cid][field]==expected[field]
        yield '{"issues":[{"severity":"recommendation","message":"Описание можно дополнить позднее"}]}'
    with patch('backend.services.preparation.chat_stream',side_effect=reviewer) as provider:
        r=client.post(url+'/resume',json={'revision':d['revision'],'api_key':'test'})
        assert r.status_code==200,r.text
        job=wait_job(client,jid);assert job['status']=='saved',job
        assert provider.call_count==1
    d=client.get(url+'?author=true').json()
    edited=deepcopy(expected['intentions']);edited[0]['text']='Отредактированное намерение';expected['intentions']=edited
    r=client.patch(url,json={'revision':d['revision'],'operation':'patch','kind':'actor','entity_id':cid,'field':'intentions','value':edited})
    assert r.status_code==200,r.text
    d=r.json()
    exported=client.get(url+'/export',params={'version_id':d['version_id'],'format':'md'}).text
    assert draft.exported_state(exported)['world']['characters'][cid]['intentions']==edited
    with patch('backend.services.preparation.chat_stream',side_effect=reviewer) as provider:
        r=client.post(url+'/resume',json={'revision':d['revision'],'api_key':'test'})
        assert r.status_code==200,r.text
        assert wait_job(client,jid)['status']=='saved'
        assert provider.call_count==1
    d=client.get(url+'?author=true').json()
    started=client.post(url+'/confirm',json={'revision':d['revision'],'version_id':d['version_id'],'accept_warnings':True})
    assert started.status_code==200,started.text
    sid=started.json()['save']
    for repository in (repo,Repository(repo.path)):
        actor=repository.get_snapshot(sid)['world_state']['characters'][cid]
        for field in FIELDS:assert actor[field]==expected[field]
    from test_runtime_v3_engine import run as play,raw_for
    from test_engine import CONFIG
    for kind in ('start','turn','turn'):
        before=repo.get_snapshot(sid);job=repo.begin_job(sid,'Осматриваюсь.' if kind=='turn' else '',kind,CONFIG)
        play(repo,job,raw_for(before));assert repo.get_job(job)['status']=='saved'
        repo=Repository(repo.path)
        actor=repo.get_snapshot(sid)['world_state']['characters'][cid]
        for field in FIELDS:
            for actual,original in zip(actor[field],expected[field]):
                for key in ('id','text','status','dependencies','source_sequence','source_event_id','due_minute'):
                    assert actual[key]==original[key]


@pytest.mark.parametrize('format',['json','text'])
@pytest.mark.parametrize('legacy',[False,True])
def test_import_motivations_remains_free_and_preserves_canonical_data(api,format,legacy):
    client,app=api;raw,cid=motivated()
    if legacy:
        for field in FIELDS:raw['world']['characters'][cid][field]=['Импорт '+field]
    expected=draft.prepare(raw)['world']['characters'][cid]
    text=json.dumps(raw) if format=='json' else draft.export_markdown(raw)
    wid=client.post('/api/workspaces',json={'name':'Import motivations'}).json()['id'];url=f'/api/workspaces/{wid}/draft'
    with patch('backend.services.preparation.chat_stream') as provider:
        r=client.post(url+'/import',json={'revision':0,'format':format,'text':text})
        assert r.status_code==200,r.text
        d=client.get(url+'?author=true').json()
        assert d['review'] is None
        r=client.post(url+'/confirm',json={'revision':d['revision'],'version_id':d['version_id']})
        assert r.status_code==200,r.text
        actor=Repository(app.state.repository.path).get_snapshot(r.json()['save'])['world_state']['characters'][cid]
        for field in FIELDS:assert actor[field]==expected[field]
        provider.assert_not_called()


def test_targeted_provider_field_result_preserves_motivation_objects():
    from backend.services.draft_generation import decode_result
    state,cid=motivated();records=deepcopy(state['world']['characters'][cid]['goals'])
    records[0]['text']='Уточнённый текст от модели'
    result=decode_result(json.dumps({'value':records}),state,{'_draft_task':'field','_draft_target':{'kind':'actor','id':cid,'field':'goals'}})
    assert result['world']['characters'][cid]['goals']==records
    for field in ('intentions','obligations'):assert result['world']['characters'][cid][field]==state['world']['characters'][cid][field]
