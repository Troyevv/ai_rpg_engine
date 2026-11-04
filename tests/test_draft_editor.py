"""AI editing: real API/storage/runtime with controlled provider responses."""
import json
import threading
import time
from copy import deepcopy
from unittest.mock import patch
import pytest
from test_api import api, REMOTE, wait_job
from test_draft_creative import candidate, proposal, additions, change
from backend.services import draft_editor, draft_completeness, draft_creative
from backend.repositories.preparation import Repository
from backend.services.draft_changes import apply_proposal


def setup(client):
    wid=client.post('/api/workspaces',json={'name':'Редактор'}).json()['id']
    url=f'/api/workspaces/{wid}/draft'
    response=client.post(url+'/import',json={'revision':0,'text':json.dumps(candidate()),'format':'json'})
    assert response.status_code==200,response.text
    return wid,url,client.get(url+'?author=true').json()


def request(client,url,draft,text='Добавь Веру и её мастерскую.',key='edit1'):
    return client.post(url+'/edits',json={'revision':draft['revision'],'text':text,'request_id':key,
        'config':dict(REMOTE,context_length=131072,max_tokens=24000),'api_key':'offline'})


def provider(changes=None,calls=None):
    def stream(**kw):
        system=kw['messages'][0]['content']
        if calls is not None:calls.append(system)
        kw['on_usage']({'prompt_tokens':100,'completion_tokens':40});kw['on_finish']('stop')
        if system.startswith(draft_editor.MARKER):
            data=json.loads(kw['messages'][1]['content']);s=data['candidate']
            yield proposal(s,changes(s) if changes else None)
        elif system.startswith(draft_completeness.MARKER):yield '{"issues":[]}'
        elif system.startswith(draft_creative.MARKER):
            data=json.loads(kw['messages'][1]['content']);yield json.dumps(dict(candidate_hash=data['candidate_hash'],rationale='Мир уже согласован.',changes=[]))
        else:yield json.dumps(candidate(),ensure_ascii=False)
    return stream


def run_edit(client,url,draft,changes=None,calls=None,key='edit1'):
    with patch('backend.services.preparation.chat_stream',side_effect=provider(changes,calls)):
        response=request(client,url,draft,key=key);assert response.status_code==200,response.text
        job=wait_job(client,response.json()['id']);assert job['status']=='saved',job.get('error')
    return job,client.get(url+'/edits').json()['edits'][0]


def decide(client,url,draft,edit,decision='accept',**extra):
    return client.post(url+'/edits/'+edit['id'],json={'revision':draft['revision'],'decision':decision,**extra})


def test_multientity_preview_confirm_rollback_and_idempotency(api):
    client,app=api;wid,url,before=setup(client);calls=[]
    job,edit=run_edit(client,url,before,calls=calls)
    preview=client.get(url+'?author=true').json()
    assert preview['version_id']==before['version_id'] and preview['state']==before['state']
    assert len(edit['diff'])>=9 and edit['review']['status']=='completed'
    assert not edit['stale'] and edit['status']=='preview'
    # Same request after worker finished is not another paid job.
    repeated=request(client,url,before);assert repeated.json()['id']==job['id']
    assert len(calls)==2
    assert decide(client,url,preview,edit).status_code==200
    accepted=client.get(url+'?author=true').json()
    assert accepted['state']['world']['roles']['craft']['actor_id']=='craftswoman'
    assert accepted['state']['authoring']['editor_instructions'][-1]['instruction']=='Добавь Веру и её мастерскую.'
    assert accepted['version_id']!=before['version_id']
    assert decide(client,url,preview,edit).status_code==200
    assert client.get(url+'?author=true').json()['version_id']==accepted['version_id']
    assert len(app.state.repository.request_log(job_id=job['id']))==2
    restore=client.patch(url,json={'revision':accepted['revision'],'operation':'restore','source_id':before['version_id']})
    assert restore.status_code==200 and restore.json()['state']==before['state']
    assert Repository(app.state.repository.path).draft(wid,True)['state']==before['state']


def test_reject_and_stale_manual_edit(api):
    client,app=api;wid,url,before=setup(client)
    _,edit=run_edit(client,url,before)
    preview=client.get(url+'?author=true').json()
    updated=client.patch(url,json={'revision':preview['revision'],'operation':'patch','kind':'campaign','field':'title','value':'Ручное название'}).json()
    assert decide(client,url,updated,edit).status_code!=200
    assert client.get(url+'/edits').json()['edits'][0]['stale']
    assert decide(client,url,updated,edit,'reject').status_code==200
    assert client.get(url+'?author=true').json()['state']['campaign']['title']=='Ручное название'


def test_manual_override_requires_explicit_consent_and_retains_other_paths(api):
    client,app=api;wid,url,before=setup(client)
    before=client.patch(url,json={'revision':before['revision'],'operation':'patch','kind':'campaign','field':'title','value':'Старый замысел'}).json()
    before=client.patch(url,json={'revision':before['revision'],'operation':'patch','kind':'campaign','field':'tone','value':'Тихая драма'}).json()
    _,edit=run_edit(client,url,before,lambda s:[change('/campaign/title','Новый замысел','replace')])
    preview=client.get(url+'?author=true').json()
    assert edit['conflicts']==['/campaign/title']
    assert decide(client,url,preview,edit).status_code!=200
    assert decide(client,url,preview,edit,accept_conflicts=True).status_code==200
    after=client.get(url+'?author=true').json()['state']
    assert after['campaign']['tone']=='Тихая драма'
    assert set(before['state']['authoring']['manual_paths'])<=set(after['authoring']['manual_paths'])
    payload=json.loads(draft_editor.messages({'state':after,'source':'Старый замысел'},'Добавь деталь')[1]['content'])
    assert 'Новый замысел' in payload['candidate']['campaign']['title']
    assert 'previous_instructions' in payload['author_context']


def test_remove_dependencies_and_rebase_manual_paths():
    state=candidate();enriched,_=apply_proposal(state,proposal(state))
    # Remove the complete newly added subgraph atomically.
    changes=[change('/characters/'+str(len(enriched['characters'])-1),enriched['characters'][-1],'remove')]
    for section,ident in [('characters','craftswoman'),('organizations','workshop'),('roles','craft'),('objective_relations','friend'),('facts','fire'),('events','fire'),('knowledge','fire'),('threads','rebuild')]:
        changes.append(change('/world/'+section+'/'+ident,enriched['world'][section][ident],'remove'))
    removed,_=apply_proposal(enriched,proposal(enriched,changes),editing=True)
    assert removed==state
    with pytest.raises(ValueError):apply_proposal(enriched,proposal(enriched,changes))
    with pytest.raises(ValueError):apply_proposal(enriched,proposal(enriched,changes[:1]),editing=True)
    s=deepcopy(state);s['characters'].insert(1,dict(s['characters'][1],id='extra'))
    s.setdefault('authoring',{})['manual_paths']=['/characters/2/name']
    after=deepcopy(s);after['characters'].pop(1)
    assert draft_editor.manual_conflicts(s,after)==[]
    assert draft_editor.accepted_state(s,after,'delete','j')['authoring']['manual_paths']==['/characters/1/name']


@pytest.mark.parametrize('changes',[
    lambda s:[change('/world/characters/'+s['controlled_actor_id']+'/intentions',['Согласиться'],'replace')],
    lambda s:[change('/world/knowledge/bad',dict(actor_id=s['controlled_actor_id'],fact_id='ownership',status='known',source_event_id='missing'))],
    lambda s:[change('/world/events/future',dict(id='future',text='already happened',minute=9999999,participants=[],witnesses=[],fact_ids=[]))],
    lambda s:[change('/world_clock/minute',900,'replace')],
])
def test_invalid_editor_packages_never_mutate(changes):
    s=candidate();before=deepcopy(s)
    with pytest.raises(ValueError):apply_proposal(s,proposal(s,changes(s)),editing=True)
    assert s==before


def test_generation_editor_start_turn_save_reload(api):
    client,app=api;wid=client.post('/api/workspaces',json={'name':'Полный цикл'}).json()['id'];url=f'/api/workspaces/{wid}/draft'
    with patch('backend.services.preparation.chat_stream',side_effect=provider()):
        generated=client.post(url+'/generate',json={'revision':0,'text':'Город после пожара','config':dict(REMOTE,context_length=131072,max_tokens=24000),'api_key':'offline'})
        job=wait_job(client,generated.json()['id']);assert job['status']=='saved',job.get('error')
    draft=client.get(url+'?author=true').json();_,edit=run_edit(client,url,draft)
    draft=client.get(url+'?author=true').json();assert decide(client,url,draft,edit).status_code==200
    draft=client.get(url+'?author=true').json()
    started=client.post(url+'/confirm',json={'revision':draft['revision'],'version_id':draft['version_id'],'accept_warnings':True})
    assert started.status_code==200,started.text
    sid=started.json()['save'];repo=app.state.repository
    assert request(client,url,draft,key='after-start').status_code!=200
    from test_runtime_v3_engine import run as play, raw_for
    from test_engine import CONFIG
    from backend.runtime_v3.repository import read_history
    expected=repo.get_snapshot(sid)['world_state']
    for kind in ('start','turn'):
        before=repo.get_snapshot(sid);jid=repo.begin_job(sid,'Осмотреться.' if kind=='turn' else '',kind,CONFIG)
        play(repo,jid,raw_for(before));assert repo.get_job(jid)['status']=='saved'
        repo=Repository(repo.path)
        after=repo.get_snapshot(sid)
        for section in ('organizations','roles','objective_relations','knowledge','threads'):
            assert after['world_state'][section]==expected[section]
        with repo.connect() as db:history,_=read_history(db,after['history_head'])
        assert any(e['id']=='fire' for e in history['events'])
    assert client.get(f'/api/saves/{sid}').status_code==200
    assert 'craftswoman:fire' not in client.get(f'/api/saves/{sid}').json()['state']['world']['knowledge']
    assert repo.get_snapshot(sid)['authoring']['editor_instructions']


@pytest.mark.parametrize('failure',['empty','timeout','truncated'])
def test_transport_failure_resume_retains_paid_response_and_cost(api,failure):
    from llm import OutputLimitReached
    client,app=api;wid,url,before=setup(client);calls=[];full=''
    def broken(**kw):
        nonlocal full
        calls.append(1)
        data=json.loads(kw['messages'][1]['content']);full=proposal(data['candidate'])
        kw['on_usage']({'prompt_tokens':100,'completion_tokens':40})
        if failure=='timeout':raise TimeoutError('controlled timeout')
        if failure=='truncated':
            yield full[:len(full)//2]
            raise OutputLimitReached('controlled truncation')
        kw['on_finish']('stop');yield ''
    with patch('backend.services.preparation.chat_stream',side_effect=broken):
        response=request(client,url,before);job=wait_job(client,response.json()['id'])
    assert job['status']=='error'
    original=client.get(url+'?author=true').json()
    assert original['state']==before['state'] and original['version_id']==before['version_id']
    journal=json.loads(app.state.repository.preparation_job(job['id'])['response_journal'])
    assert app.state.repository.request_log(job_id=job['id'])
    # Empty response needs explicit consent; no automatic duplicate request.
    if failure=='empty':
        assert len(calls)==1 and job['empty_retry_token']
        with patch('backend.services.preparation.chat_stream',side_effect=provider()):
            resumed=client.post(url+'/resume',json={'revision':original['revision'],'api_key':'offline',
                'retry_empty_response':job['empty_retry_token'],'expected_epoch':job['attempt_epoch']})
            assert resumed.status_code==200,resumed.text
            done=wait_job(client,job['id']);assert done['status']=='saved',done.get('error')
        assert client.get(url+'?author=true').json()['state']==before['state']
        assert len(app.state.repository.request_log(job_id=job['id']))==3
    else:
        assert journal['editor']['base']['state']==before['state']


def test_cancel_and_double_click_never_publish_late_proposal(api):
    client,app=api;wid,url,before=setup(client);entered=threading.Event();release=threading.Event();calls=[]
    def slow(**kw):
        calls.append(1);entered.set();assert release.wait(5)
        yield from provider()(**kw)
    with patch('backend.services.preparation.chat_stream',side_effect=slow):
        first=request(client,url,before);assert entered.wait(5)
        second=request(client,url,before);assert second.json()['id']==first.json()['id']
        jid=first.json()['id']
        stopped=client.post('/api/jobs/'+jid+'/stop');assert stopped.status_code==200,stopped.text
        release.set()
        for _ in range(100):
            if not app.state.preparation.live(jid):break
            time.sleep(.01)
    assert len(calls)==1
    assert client.get(url+'?author=true').json()['state']==before['state']
    assert client.get('/api/jobs/'+jid).json()['status']=='stopped'
    assert client.get(url+'/edits').json()['edits'][0]['status']!='accepted'


def test_deletion_requires_consent_and_persists_rollback(api):
    client,app=api;wid,url,before=setup(client)
    # Unreferenced organization exercises deletion without incidental dependencies.
    before=client.patch(url+'/candidate',json={'revision':before['revision'],'path':'/world/organizations/unused','value':{'id':'unused','name':'Закрытый клуб'}}).json()
    _,edit=run_edit(client,url,before,lambda s:[change('/world/organizations/unused',s['world']['organizations']['unused'],'remove')])
    preview=client.get(url+'?author=true').json()
    assert decide(client,url,preview,edit).status_code!=200
    assert decide(client,url,preview,edit,accept_conflicts=True).status_code==200
    updated=client.get(url+'?author=true').json()
    assert 'unused' not in updated['state']['world']['organizations']
    restored=client.patch(url,json={'revision':updated['revision'],'operation':'restore','source_id':before['version_id']})
    assert restored.json()['state']['world']['organizations']['unused']['name']=='Закрытый клуб'


def test_manual_knowledge_and_relationship_paths_are_protected():
    from backend.services import draft_world
    s=candidate()
    for kind,section,field,value in [('relationship','relationships','context','Явная авторская связь'),('fact','facts','text','Факт автора')]:
        ident=next(iter(s['world'][section]))
        updated=draft_world.patch(s,kind,ident,field,value)
        path=f'/world/{section}/{ident}/{field}'
        assert path in updated['authoring']['manual_paths']
        changed=deepcopy(updated);changed['world'][section][ident][field]='Модель заменила'
        assert path in draft_editor.manual_conflicts(updated,changed)


def test_removed_manual_record_does_not_leave_dangling_override():
    s=candidate();s.setdefault('authoring',{})['manual_paths']=['/world/organizations/apex/name']
    after=deepcopy(s);after['world']['organizations'].pop('apex')
    assert draft_editor.manual_conflicts(s,after)==['/world/organizations/apex/name']
    assert draft_editor.accepted_state(s,after,'Удалить организацию','j')['authoring']['manual_paths']==[]


def test_preview_survives_repository_restart(api):
    client,app=api;wid,url,before=setup(client);_,edit=run_edit(client,url,before)
    repo=Repository(app.state.repository.path);draft=repo.draft(wid,True)
    repo.decide_world_edit(wid,edit['id'],draft['revision'],'accept')
    assert repo.world_edits(wid)['edits'][0]['status']=='accepted'
    assert repo.draft(wid,True)['state']['world']['roles']['craft']


def test_explicit_model_conflict_is_reviewable_but_cannot_be_applied(api):
    client,app=api;wid,url,before=setup(client)
    def stream(**kw):
        if kw['messages'][0]['content'].startswith(draft_editor.MARKER):
            data=json.loads(kw['messages'][1]['content']);reply=json.loads(proposal(data['candidate']))
            reply['conflicts']=['Сохранить единственного ребёнка и добавить родную сестру одновременно нельзя. Уточните замысел.']
            yield json.dumps(reply,ensure_ascii=False)
        else:yield '{"issues":[]}'
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        job=wait_job(client,request(client,url,before).json()['id']);assert job['status']=='saved',job.get('error')
    edit=client.get(url+'/edits').json()['edits'][0];draft=client.get(url+'?author=true').json()
    assert edit['proposal']['conflicts']
    assert decide(client,url,draft,edit,accept_conflicts=True).status_code!=200
    assert draft['state']==before['state']


def test_multi_entity_kinship_and_existing_organization_edit():
    s=candidate();changes=additions(s)
    changes += [change('/world/objective_relations/sister',dict(id='sister',source_id='craftswoman',target_id=s['characters'][2]['id'],kind='sibling',context='Сестра и брат.')),
                change('/world/organizations/apex/name','Объединение мастерских','replace')]
    after,_=apply_proposal(s,proposal(s,changes),editing=True)
    assert after['world']['objective_relations']['sister']['kind']=='sibling'
    assert after['world']['organizations']['apex']['name']=='Объединение мастерских'
    assert after['world']['events']['fire']['fact_ids']==['fire']
    assert after['world']['knowledge']['fire']['actor_id']=='craftswoman'


def test_semantic_repair_is_previewed_before_commit(api):
    client,app=api;wid,url,before=setup(client);reviews=[]
    def stream(**kw):
        system=kw['messages'][0]['content']
        if system.startswith(draft_editor.MARKER):
            data=json.loads(kw['messages'][1]['content']);yield proposal(data['candidate'])
        elif system.startswith(draft_completeness.MARKER):
            reviews.append(1)
            yield json.dumps({'issues':[dict(path='/world/organizations/workshop/name',message='Название должно отражать реставрацию.',patch_paths=['/world/organizations/workshop/name'])] if len(reviews)==1 else []})
        else:yield json.dumps({'patches':[dict(path='/world/organizations/workshop/name',value='Реставрационная мастерская')]},ensure_ascii=False)
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        job=wait_job(client,request(client,url,before).json()['id']);assert job['status']=='saved',job.get('error')
    edit=client.get(url+'/edits').json()['edits'][0]
    assert next(d for d in edit['diff'] if d['section']=='world/organizations' and d['id']=='workshop')['fields'][0]['after']['name']=='Реставрационная мастерская'
    assert client.get(url+'?author=true').json()['state']==before['state']
    assert len(reviews)==2


def test_structural_correction_keeps_good_changes(api):
    client,app=api;wid,url,before=setup(client)
    def stream(**kw):
        system=kw['messages'][0]['content'];data=json.loads(kw['messages'][1]['content'])
        if system.startswith(draft_editor.MARKER):
            changes=additions(data['candidate']);changes[3]['value']['actor_id']='missing'
            yield proposal(data['candidate'],changes)
        elif system.startswith('Адресная коррекция'):
            yield json.dumps(dict(proposal_hash=data['proposal_hash'],patches=[dict(path='/changes/3/value/actor_id',value='craftswoman')],drop_indices=[]))
        else:yield '{"issues":[]}'
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        job=wait_job(client,request(client,url,before).json()['id']);assert job['status']=='saved',job.get('error')
    journal=json.loads(app.state.repository.preparation_job(job['id'])['response_journal'])
    assert len(journal['editor']['corrections'])==1
    assert journal['editor']['candidate']['world']['roles']['craft']['actor_id']=='craftswoman'
    assert client.get(url+'?author=true').json()['state']==before['state']


def test_budget_preflight_never_calls_provider(api):
    client,app=api;wid,url,before=setup(client)
    with patch('backend.services.preparation.chat_stream',side_effect=AssertionError('provider must not be called')):
        response=client.post(url+'/edits',json={'revision':before['revision'],'text':'Измени мир','request_id':'budget',
            'config':dict(REMOTE,context_length=131072),'api_key':'offline','budget':{'max_total_tokens':1}})
        job=wait_job(client,response.json()['id']);assert job['status']=='error'
    assert 'бюджет' in job['error']
    assert not app.state.repository.request_log(job_id=job['id'])
    assert client.get(url+'?author=true').json()['state']==before['state']


def test_truncated_response_continues_same_package(api):
    from llm import OutputLimitReached
    client,app=api;wid,url,before=setup(client);reply='';calls=[]
    def stream(**kw):
        nonlocal reply
        if kw['messages'][0]['content'].startswith(draft_completeness.MARKER):yield '{"issues":[]}';return
        calls.append(kw['messages'])
        if len(calls)==1:
            data=json.loads(kw['messages'][1]['content']);reply=proposal(data['candidate'])
            yield reply[:len(reply)//2];raise OutputLimitReached()
        assert kw['messages'][-2]==dict(role='assistant',content=reply[:len(reply)//2])
        yield reply[len(reply)//2:]
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        job=wait_job(client,request(client,url,before).json()['id']);assert job['status']=='saved',job.get('error')
    assert len(calls)==2
    journal=json.loads(app.state.repository.preparation_job(job['id'])['response_journal'])
    assert len(journal['responses'][journal['editor']['slot']]['parts'])==2
    assert client.get(url+'?author=true').json()['state']==before['state']


def test_unknown_outcome_requires_consent_then_resumes_frozen_base(api):
    client,app=api;wid,url,before=setup(client)
    with patch('backend.services.preparation.chat_stream',side_effect=TimeoutError('offline')):
        job=wait_job(client,request(client,url,before).json()['id'])
    draft=client.get(url+'?author=true').json()
    assert job['unknown_outcome']
    with patch('backend.services.preparation.chat_stream',side_effect=provider()):
        refused=client.post(url+'/resume',json={'revision':draft['revision'],'api_key':'offline'})
        assert refused.status_code!=200
        resumed=client.post(url+'/resume',json={'revision':draft['revision'],'api_key':'offline','acknowledge_unknown':True})
        assert resumed.status_code==200,resumed.text
        done=wait_job(client,job['id']);assert done['status']=='saved',done.get('error')
    journal=json.loads(app.state.repository.preparation_job(job['id'])['response_journal'])
    assert len(journal['unknown_attempts'])==1 and journal['editor']['base']['state']==before['state']
    assert client.get(url+'?author=true').json()['state']==before['state']
