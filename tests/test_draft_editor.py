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
        else:
            initial=candidate();initial['world'].pop('contacts',None)
            yield json.dumps(initial,ensure_ascii=False)
    return stream


def run_edit(client,url,draft,changes=None,calls=None,key='edit1'):
    with patch('backend.services.preparation.chat_stream',side_effect=provider(changes,calls)):
        response=request(client,url,draft,key=key);assert response.status_code==200,response.text
        job=wait_job(client,response.json()['id']);assert job['status']=='saved',job.get('error')
    return job,client.get(url+'/edits?author=true').json()['edits'][0]


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
    assert client.get(url+'/edits?author=true').json()['edits'][0]['stale']
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


@pytest.mark.parametrize('entry', ['idea', 'json', 'md', 'txt'])
def test_generation_editor_start_turn_save_reload(api, entry):
    client,app=api;wid=client.post('/api/workspaces',json={'name':'Полный цикл'}).json()['id'];url=f'/api/workspaces/{wid}/draft'
    if entry == 'idea':
        with patch('backend.services.preparation.chat_stream', side_effect=provider()):
            generated = client.post(url+'/generate', json={'revision':0, 'text':'Город после пожара',
                'config':dict(REMOTE, context_length=131072, max_tokens=24000), 'api_key':'offline'})
            job = wait_job(client, generated.json()['id'])
            assert job['status'] == 'saved', job.get('error')
    else:
        _, source_url, source = setup(client)
        exported = client.get(source_url+'/export', params={'version_id':source['version_id'], 'format':entry})
        assert exported.status_code == 200, exported.text
        imported = client.post(url+'/import', json={'revision':0, 'text':exported.text,
            'format':'json' if entry == 'json' else 'text'})
        assert imported.status_code == 200, imported.text
    draft = client.get(url+'?author=true').json()
    _, rejected = run_edit(client, url, draft, key='declined-version')
    preview = client.get(url+'?author=true').json()
    assert decide(client, url, preview, rejected, 'reject').status_code == 200
    assert client.get(url+'?author=true').json()['state'] == draft['state']
    current = client.get(url+'?author=true').json()
    _, edit = run_edit(client, url, current)
    preview = client.get(url+'?author=true').json()
    assert decide(client, url, preview, edit).status_code == 200
    accepted = client.get(url+'?author=true').json()
    def restore(current, version):
        response = client.patch(url, json={'revision':current['revision'], 'operation':'restore', 'source_id':version})
        assert response.status_code == 200, response.text
        return response.json()
    restored = restore(accepted, draft['version_id'])
    assert restored['state'] == draft['state']
    draft = restore(restored, accepted['version_id'])
    assert draft['state'] == accepted['state']
    from test_portraits import image
    cid=draft['state']['characters'][0]['id']
    first_portrait=client.post(url+f'/characters/{cid}/portraits',params={'revision':draft['revision']},content=image(),headers={'content-type':'image/png'})
    assert first_portrait.status_code==200,first_portrait.text
    first_portrait=first_portrait.json()['portrait']
    original_image=client.get(url+f'/characters/{cid}/portraits/assets/'+first_portrait['asset_id']+'?author=true').content
    draft=client.get(url+'?author=true').json()
    started=client.post(url+'/confirm',json={'revision':draft['revision'],'version_id':draft['version_id'],'accept_warnings':True})
    assert started.status_code==200,started.text
    sid=started.json()['save'];repo=app.state.repository
    from test_runtime_v3_engine import run as play, raw_for
    from test_engine import CONFIG
    from backend.runtime_v3.repository import read_history
    expected=repo.get_snapshot(sid)['world_state']
    for kind in ('start','turn','turn'):
        before=repo.get_snapshot(sid);jid=repo.begin_job(sid,'Осмотреться.' if kind=='turn' else '',kind,CONFIG)
        play(repo,jid,raw_for(before));assert repo.get_job(jid)['status']=='saved'
        repo=Repository(repo.path)
        after=repo.get_snapshot(sid)
        for section in ('organizations','roles','objective_relations','knowledge','threads'):
            assert after['world_state'][section]==expected[section]
        with repo.connect() as db:history,_=read_history(db,after['history_head'])
        assert any(e['id']=='fire' for e in history['events'])
    old=deepcopy(repo.get_snapshot(sid))
    from backend.repositories import portraits
    current=client.get(url+'?author=true').json()
    cid=current['state']['characters'][0]['id']
    edited=client.patch(url,json={'revision':current['revision'],'operation':'patch','kind':'campaign','field':'title','value':'Второе прохождение'})
    assert edited.status_code==200,edited.text
    _,edit=run_edit(client,url,edited.json(),lambda s:[change('/campaign/description','История после пожара: новое начало.','replace')],key='after-start')
    current=client.get(url+'?author=true').json()
    assert decide(client,url,current,edit).status_code==200
    current=client.get(url+'?author=true').json()
    portrait=client.post(url+f'/characters/{cid}/portraits',params={'revision':current['revision'],'replace_id':first_portrait['id']},content=image(size=(240,360)),headers={'content-type':'image/png'})
    assert portrait.status_code==200,portrait.text
    current=client.get(url+'?author=true').json()
    assert decide(client,url,current,edit).status_code==200  # accepted package stays idempotent
    second=client.post(url+'/confirm',json={'revision':current['revision'],'version_id':current['version_id'],'accept_warnings':True})
    assert second.status_code==200,second.text
    new_sid=second.json()['save'];assert new_sid!=sid
    assert client.post(url+'/confirm',json={'revision':current['revision'],'version_id':current['version_id'],'accept_warnings':True}).json()['save']==new_sid
    assert repo.get_snapshot(sid)==old
    new=repo.get_snapshot(new_sid)
    assert new['world_state']['knowledge']==old['world_state']['knowledge']
    assert new['world_state']['characters'][cid]['portraits']!=old['world_state']['characters'][cid]['portraits']
    assert portraits.asset(repo,new_sid,cid,portrait.json()['portrait']['asset_id'])!=original_image
    assert portraits.asset(repo,sid,cid,first_portrait['asset_id'])==original_image
    with pytest.raises(ValueError):portraits.asset(repo,sid,cid,portrait.json()['portrait']['asset_id'])
    _,preview=run_edit(client,url,current,lambda s:[change('/campaign/tone','Спокойный','replace')],key='stale-after-start')
    current=client.get(url+'?author=true').json()
    patched=client.patch(url,json={'revision':current['revision'],'operation':'patch','kind':'campaign','field':'tone','value':'Драма'}).json()
    assert decide(client,url,patched,preview).status_code==409
    assert repo.get_snapshot(sid)==old and repo.get_snapshot(new_sid)==new
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
    assert client.get(url+'/edits?author=true').json()['edits'][0]['status']!='accepted'


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
    assert repo.world_edits(wid,True)['edits'][0]['status']=='accepted'
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
    edit=client.get(url+'/edits?author=true').json()['edits'][0];draft=client.get(url+'?author=true').json()
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
    edit=client.get(url+'/edits?author=true').json()['edits'][0]
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


@pytest.mark.parametrize('decision',['accept','reject'])
def test_editor_history_requires_explicit_author_projection(api,decision):
    client,app=api;wid,url,before=setup(client)
    npc=before['state']['characters'][-1]['id'];hidden='HIDDEN_EDITOR_CANON_184'
    before=client.patch(url+'/candidate',json={'revision':before['revision'],'path':'/world/facts/hidden184','value':{
        'id':'hidden184','text':hidden,'secret':True,'story_secret':True,'secret_subject_ids':[npc],
        'secret_existence':'hidden','character_ids':[npc],'evidence':[hidden+' evidence']}}).json()
    def stream(**kw):
        if kw['messages'][0]['content'].startswith(draft_completeness.MARKER):
            yield json.dumps({'issues':[{'path':'/world/facts/hidden184/text','severity':'recommendation','message':hidden+' review'}]})
        else:yield from provider(lambda state:[change('/world/facts/hidden184/text',hidden+' changed','replace')])(**kw)
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        job=wait_job(client,request(client,url,before,text=hidden+' instruction').json()['id'])
        assert job['status']=='saved',job
    public=client.get(url+'/edits').json()
    assert public=={'edits':[], 'started':False}
    assert client.get(url+'/edits?author=false').json()==public
    author=client.get(url+'/edits?author=true').json()['edits'][0]
    for key in ('diff','references','review','instruction'):
        assert hidden in json.dumps(author[key],ensure_ascii=False)
    assert hidden not in client.get(url).text
    assert decide(client,url,client.get(url+'?author=true').json(),author,decision,accept_warnings=True,accept_conflicts=True).status_code==200
    assert client.get(url+'/edits').json()==public
    assert client.get(url+'/edits?author=true').json()['edits'][0]['status']==('accepted' if decision=='accept' else 'rejected')
    assert hidden not in client.get(url).text
    if decision=='accept':
        current=client.get(url+'?author=true').json()
        started=client.post(url+'/confirm',json={'revision':current['revision'],'version_id':current['version_id'],'accept_warnings':True})
        assert started.status_code==200,started.text
        sid=started.json()['save']
        assert hidden not in client.get(f'/api/saves/{sid}').text
        assert hidden in client.get(f'/api/saves/{sid}/author-state').text
        assert client.get(url+'/edits').json()=={'edits':[],'started':True}



@pytest.mark.parametrize('field',['name','id','alias'])
def test_deleted_location_cannot_survive_as_legacy_text_reference(field):
    s=candidate();loc=s['locations'][1];loc['aliases']=['Старая кухня']
    value={'name':loc['name'],'id':loc['id'],'alias':'  СТАРАЯ КУХНЯ  '}[field]
    for actor in s['world']['characters'].values():
        if actor.get('location')==loc['name']:actor['location']=value
    for scene in s['world']['scenes'].values():scene['location']=value
    before=deepcopy(s)
    with pytest.raises(ValueError,match='связан'):
        apply_proposal(s,proposal(s,[change('/locations/1',loc,'remove')]),editing=True)
    assert s==before


def test_history_references_block_deletion_without_erasing_history():
    s=candidate();cid='archived_npc'
    s['characters'].append(dict(deepcopy(s['characters'][-1]),id=cid,name=cid))
    s['world']['characters'][cid]=dict(deepcopy(s['world']['characters'][s['characters'][-2]['id']]),id=cid)
    s['world']['scene_records']['archived']={'id':'archived','snapshot':{'participants':[cid]},'text':'История остаётся.'}
    changes=[change('/characters/'+str(len(s['characters'])-1),s['characters'][-1],'remove'),change('/world/characters/'+cid,s['world']['characters'][cid],'remove')]
    before=deepcopy(s)
    with pytest.raises(ValueError,match='связан'):
        apply_proposal(s,proposal(s,changes),editing=True)
    assert s==before


@pytest.mark.parametrize('phase',['proposing','reviewing'])
def test_process_crash_recovery_preserves_frozen_editor_and_requires_unknown_consent(tmp_path,phase):
    """Kill a real backend process, including its worker, without lifespan cleanup."""
    import os
    import subprocess
    import sys
    from pathlib import Path
    from fastapi.testclient import TestClient
    from backend.api.app import create_app
    db=tmp_path/'restart.sqlite3';ready=tmp_path/'ready.json'
    with TestClient(create_app(db)) as client:
        wid,url,before=setup(client)
    script=r'''
import json,sys,threading
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.api.app import create_app
from test_draft_editor import request,provider
from backend.services import draft_editor,draft_completeness
entered=threading.Event()
def stream(**kw):
    target=draft_editor.MARKER if sys.argv[3]=='proposing' else draft_completeness.MARKER
    if kw['messages'][0]['content'].startswith(target):
        entered.set();threading.Event().wait()
    yield from provider()(**kw)
with TestClient(create_app(sys.argv[1])) as client, patch('backend.services.preparation.chat_stream',side_effect=stream):
    url='/api/workspaces/'+sys.argv[2]+'/draft'
    response=request(client,url,client.get(url+'?author=true').json())
    assert response.status_code==200,response.text
    assert entered.wait(10)
    Path(sys.argv[4]).write_text(json.dumps(response.json()))
    threading.Event().wait()
'''
    env=dict(os.environ,PYTHONPATH=os.pathsep.join([str(Path.cwd()),str(Path.cwd()/'tests')]))
    with (tmp_path/'child.log').open('w') as log:
        child=subprocess.Popen([sys.executable,'-c',script,str(db),wid,phase,str(ready)],env=env,stdout=log,stderr=log)
        try:
            deadline=time.monotonic()+15
            while not ready.exists() and time.monotonic()<deadline and child.poll() is None:time.sleep(.02)
            assert ready.exists(),(tmp_path/'child.log').read_text()
            jid=json.loads(ready.read_text())['id']
        finally:
            child.kill();child.wait(timeout=5)
    calls=[]
    with TestClient(create_app(db)) as client:
        job=client.get('/api/jobs/'+jid).json()
        assert job['status']=='stopped' and job['unknown_outcome']
        current=client.get(url+'?author=true').json()
        assert current['state']==before['state'] and current['version_id']==before['version_id']
        assert decide(client,url,current,{'id':jid}).status_code==409
        with patch('backend.services.preparation.chat_stream',side_effect=provider(calls=calls)):
            assert client.post(url+'/resume',json={'revision':current['revision'],'api_key':'offline'}).status_code==409
            response=client.post(url+'/resume',json={'revision':current['revision'],'api_key':'offline','acknowledge_unknown':True})
            assert response.status_code==200,response.text
            assert wait_job(client,jid)['status']=='saved'
        assert len(calls)==(2 if phase=='proposing' else 1)
        assert client.get(url+'?author=true').json()['state']==before['state']
        assert decide(client,url,current,{'id':jid}).status_code==200
        accepted=client.get(url+'?author=true').json()
        assert len([v for v in accepted['history'] if v['reason']=='ai_edit'])==1


def test_lost_confirmation_response_and_concurrent_retries_publish_one_version(api):
    from concurrent.futures import ThreadPoolExecutor
    client,app=api;wid,url,before=setup(client);_,edit=run_edit(client,url,before)
    preview=client.get(url+'?author=true').json()
    # Commit succeeds, but the client never receives/uses the response.
    assert decide(client,url,preview,edit).status_code==200
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:decide(client,url,preview,edit),range(4)))
    assert all(r.status_code==200 for r in results)
    current=client.get(url+'?author=true').json()
    assert len([v for v in current['history'] if v['reason']=='ai_edit'])==1
    assert current['revision']==preview['revision']+1
    assert decide(client,url,current,edit,'reject').status_code==409


def test_atomic_multiple_npc_locations_dependencies_and_unrelated_history():
    from backend.services.draft_initial import inspect_candidate
    s=candidate();indices=[]
    for index in (1,2):
        cid=f'extra{index}';lid=f'place{index}';eid=f'past{index}';fid=f'fact{index}'
        indices.append(len(s['characters']))
        s['characters'].append(dict(deepcopy(s['characters'][-1]),id=cid,name=cid))
        s['locations'].append(dict(id=lid,name=f'Место {index}',text='Бывшее место встречи.'))
        s['world']['characters'][cid]=dict(id=cid,situation='В гостях.',location=lid,goals=[],intentions=[],obligations=[])
        s['world']['scenes'][eid]=dict(id=eid,participants=[cid],location=lid,start_minute=1,end_minute=2,status='closed',text='Прошлая встреча.',event_ids=[eid])
        s['world']['events'][eid]=dict(id=eid,participants=[cid],witnesses=[],minute=1,scene_id=eid,text='Пришёл.',fact_ids=[fid])
        s['world']['facts'][fid]=dict(id=fid,text='Он был здесь.',character_ids=[cid],secret=False)
        s['world']['knowledge'][fid]=dict(actor_id=cid,fact_id=fid,status='known',source_event_id=eid)
        s['world']['residences'][cid]=dict(id=cid,actor_id=cid,location_id=lid)
        s['world']['relationships'][cid]=dict(source_id=cid,target_id=s['controlled_actor_id'],context='Знакомы.',dimensions={})
    s,report=inspect_candidate(s);assert not report['errors'],report
    # Prose mentioning a removed character is history, not a structured reference.
    s['world']['scene_records']['kept']=dict(id='kept',text='extra1 вспомнил place2 — это неизменяемый исторический текст.')
    before=deepcopy(s);changes=[]
    for index,pos in zip((1,2),indices):
        cid=f'extra{index}';lid=f'place{index}';eid=f'past{index}';fid=f'fact{index}'
        changes.append(change('/characters/'+str(pos),s['characters'][pos],'remove'))
        loc_index=next(i for i,l in enumerate(s['locations']) if l['id']==lid)
        changes.append(change('/locations/'+str(loc_index),s['locations'][loc_index],'remove'))
        for section,key in [('characters',cid),('scenes',eid),('events',eid),('facts',fid),('knowledge',fid),('residences',cid),('relationships',cid)]:
            changes.append(change('/world/'+section+'/'+key,s['world'][section][key],'remove'))
    result,_=apply_proposal(s,proposal(s,changes),editing=True)
    assert s==before and len(result['characters'])==len(s['characters'])-2
    assert len(result['locations'])==len(s['locations'])-2
    assert result['world']['scene_records']==s['world']['scene_records']
    assert result['world']['events']=={k:v for k,v in s['world']['events'].items() if not k.startswith('past')}
    for section in ('relationships','knowledge','scenes','events','residences'):
        incomplete=[c for c in changes if c['path']!='/world/'+section+'/'+({'knowledge':'fact1','scenes':'past1','events':'past1'}.get(section,'extra1'))]
        with pytest.raises(ValueError):apply_proposal(s,proposal(s,incomplete),editing=True)


def test_deletion_dependency_namespaces_do_not_confuse_fact_and_event_ids():
    s,_=apply_proposal(candidate(),proposal(candidate()))
    # A retained fact may share an ID with a deleted event; unlink only the event.
    changes=[change('/world/events/fire',s['world']['events']['fire'],'remove'),
        change('/world/knowledge/fire/source_event_id',None,'replace'),
        change('/world/threads/rebuild/last_event_id',None,'replace')]
    result,_=apply_proposal(s,proposal(s,changes),editing=True)
    assert result['world']['facts']['fire']==s['world']['facts']['fire']


def test_resume_after_manual_edit_cannot_adopt_new_head(api):
    client,app=api;wid,url,before=setup(client)
    with patch('backend.services.preparation.chat_stream',side_effect=TimeoutError('interrupted')):
        job=wait_job(client,request(client,url,before).json()['id'])
    current=client.get(url+'?author=true').json()
    updated=client.patch(url,json={'revision':current['revision'],'operation':'patch','kind':'campaign','field':'title','value':'Новый ручной замысел'}).json()
    with patch('backend.services.preparation.chat_stream') as stream:
        response=client.post(url+'/resume',json={'revision':updated['revision'],'api_key':'offline','acknowledge_unknown':True})
        assert response.status_code==409
        stream.assert_not_called()
    assert decide(client,url,updated,{'id':job['id']}).status_code==409
    actual=client.get(url+'?author=true').json()
    assert actual['state']==updated['state'] and actual['version_id']==updated['version_id']


def test_editor_prompt_compacts_contract_without_cutting_canon(api):
    from context_builder import estimate
    from backend.services.draft_portraits import initialize
    client,_=api;_,_,before=setup(client)
    initialize(before['state'],version=2)
    prompt=draft_editor.messages(before,'Измени мир')
    payload=json.loads(prompt[1]['content'])
    assert payload['candidate']==before['state']
    assert estimate(prompt)+512+256 <= 32768
    schema=payload['world_schema']
    assert schema['$defs']
    assert 'portrait_traits' in schema['properties']['characters']['items']['properties']
