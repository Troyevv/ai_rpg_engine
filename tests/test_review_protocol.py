"""Protocol failures are synthetic fixtures, not the user's unavailable raw report."""
import json
from copy import deepcopy
from threading import Event
from unittest.mock import patch
import pytest
from test_initial_draft_v4 import api, rich, REMOTE, SHORT, wait_job
from test_draft_completeness import real, DINNER, findings, corrections, candidate
from backend.services import draft_completeness as review, draft_initial as initial, draft_repair
from backend.services.draft_response import response
from backend.repositories.preparation import Repository
from llm import ProviderHTTPError


@pytest.mark.parametrize('reply,address',[
    ('','/'),('{"issues":[','/'),('{"issues":[],"issues":[]}','/'),
    ('{"issues":null}','/issues'),('{"issues":[],"approved":true}','/approved'),
    ('{"issues":[{"message":"x","severity":"minor"}]}','/issues/0/severity'),
    ('{"issues":[{"path":"/world/world/roles/job/title","message":"x"}]}','/issues/0/path'),
    ('{"issues":[{"path":"/world/roles/missing/title","message":"x"}]}','/issues/0/path'),
    ('{"issues":[{"path":"/characters/999/name","message":"x"}]}','/issues/0/path'),
    ('{"issues":[{"path":"/characters/-1/name","message":"x"}]}','/issues/0/path'),
    ('{"issues":[{"path":"/characters/01/name","message":"x"}]}','/issues/0/path'),
    ('{"issues":[{"path":"/controlled_actor_id","message":"x","related_paths":["/world/nope"]}]}','/issues/0/related_paths/0'),
])
def test_rejected_reports_have_report_and_world_addresses(reply,address):
    with pytest.raises(review.ReportError) as exc:review.parse(reply,rich())
    assert address in [e['report_path'] for e in exc.value.errors]
    assert all('world_path' in e for e in exc.value.errors)


def test_partial_report_and_patch_permissions_are_separate():
    state=rich()
    valid={'path':'/world/roles/job','message':'Уточнить роль','patch_paths':['/world/roles/job/title']}
    rec={'message':'Можно подробнее описать вечер','severity':'recommendation'}
    invalid={'path':'/world/world/roles/job','message':'Не терять это замечание'}
    with pytest.raises(review.ReportError) as exc:review.parse(json.dumps({'issues':[valid,rec,invalid]}),state)
    assert [e['message'] for e in exc.value.issues]==[valid['message'],rec['message'],invalid['message']]
    assert exc.value.errors[0]['world_path']==invalid['path']
    issues=review.parse(json.dumps({'issues':[valid,rec]}),state)
    _,paths=draft_repair.request(json.dumps(state),issues[:1])
    assert paths==['/world/roles/job/title']
    with pytest.raises(ValueError):draft_repair.apply(json.dumps(state),json.dumps({'patches':[{'path':valid['path'],'value':{}}]}),paths)


@pytest.mark.parametrize('path',['/characters/0/fields/Биография','/locations/0/name','/controlled_actor_id','/campaign/title','/world/roles/new_role','/world_clock/minute'])
def test_exact_fields_and_new_records(path):
    assert review.parse(json.dumps({'issues':[{'path':path,'message':'Проверить'}]}),rich())[0]['patch_paths']==[path]


def test_escaped_id_and_related_path():
    state=rich();state['world']['roles']['a/b~c']=state['world']['roles'].pop('job')
    p='/world/roles/a~1b~0c/title'
    issue=review.parse(json.dumps({'issues':[dict(path=p,message='Уточнить',related_paths=['/world/roles/a~1b~0c'])]}),state)[0]
    assert issue['patch_paths']==[p]


def test_independent_typed_errors_are_retained():
    state=rich();state['world']['roles']['job'].update(actor_id=[],since=20,until=1)
    state['locations'][0]['kind']=''
    _,report=initial.inspect_candidate(state)
    paths={d['path'] for d in report['diagnostics']}
    assert {'/world/roles/job/actor_id','/world/roles/job/until','/locations/0/kind'}<=paths
    assert '/' not in paths and not any('unhashable' in e for e in report['errors'])


def test_symmetric_duplicates_preserve_phases_and_directed_feelings():
    state=rich();ids=[c['id'] for c in state['characters'][:2]]
    a=dict(id='a',kind='friend',source_id=ids[0],target_id=ids[1],since=10)
    state['world']['objective_relations']={'a':a,'b':dict(a,id='b',source_id=ids[1],target_id=ids[0]),'past':dict(a,id='past',status='closed',until=20,since=1)}
    before=deepcopy(state['world']['relationships'])
    normalized=initial.normalize(state)
    assert set(normalized['world']['objective_relations'])=={'a','past'}
    assert normalized['world']['relationships']==before
    state['world']['objective_relations']['b']['since']=11
    _,report=initial.inspect_candidate(state)
    duplicates=[e for e in report['diagnostics'] if e['category']=='relation_conflict']
    assert duplicates and all(not e['path'].endswith('/status') for e in duplicates)
    _,paths=draft_repair.request(json.dumps(state),duplicates)
    assert set(paths)=={'/world/objective_relations/a/since','/world/objective_relations/b/since'}


@pytest.mark.parametrize('code',[429,503])
def test_http_retry_releases_reservation_under_tight_budget(code):
    class Repo:
        def save_response_journal(self,*a):pass
        def preparation_progress(self,*a):pass
        def draft_phase(self,*a):pass
    config=dict(REMOTE,_draft_token_budget=3000,max_tokens=2000)
    calls=[];journal={}
    def generate(*args):
        calls.append(args)
        if len(calls)==1:raise ProviderHTTPError('rejected',code)
        yield '{}'
    with patch.object(Event,'wait',return_value=False):
        assert response(Repo(),'j',journal,'world',[{'role':'user','content':'x'}],config,32768,generate,Event())=='{}'
    assert len(calls)==2 and journal['reserved_tokens']<3000
    assert journal['http_failures'][0]['reservation_released']


def test_full_volkov_failed_review_resume_edit_play_reload(api):
    client,app=api
    wid=client.post('/api/workspaces',json={'name':'Protocol recovery'}).json()['id'];url=f'/api/workspaces/{wid}/draft'
    calls=[];bad={'issues':[{'path':'/world/world/roles/new_role','message':'Профессия должна быть канонической'}]}
    def broken(**kw):
        calls.append(kw)
        if len(calls)==1:yield json.dumps(real(),ensure_ascii=False);return
        if len(calls)==3:
            feedback=json.loads(kw['messages'][-1]['content'])
            assert json.loads(feedback['rejected_response'])==bad
            assert feedback['validation_errors'][0]['report_path']=='/issues/0/path'
            assert feedback['report_schema']['properties']['issues']
        kw['on_usage']({'prompt_tokens':100,'completion_tokens':40,'prompt_cache_hit_tokens':0})
        kw['on_finish']('stop');yield json.dumps(bad)
    with patch('backend.services.preparation.chat_stream',side_effect=broken):
        r=client.post(url+'/generate',json={'revision':0,'text':DINNER,'config':dict(REMOTE,context_length=131072),'api_key':'do-not-export','creation_settings':{'npc_expressiveness':'hyperbolized'}})
        jid=r.json()['id'];assert wait_job(client,jid)['status']=='error'
    d=client.get(url+'?author=true').json();assert d['review']['status']=='failed'
    assert d['candidate']['creation_settings']['npc_expressiveness']=='hyperbolized'
    assert all(e['path']!='/' for e in d['validation']['diagnostics'])
    raw=client.get(url+'/raw').json()
    assert len(raw['review_failures'])==3
    assert raw['review_failures'][0]['response']==json.dumps(bad)
    assert raw['review_failures'][0]['candidate_hash']
    assert any(r['usage_json'] for r in raw['requests'])
    assert 'do-not-export' not in json.dumps(raw)
    public=client.get(url).json();assert public['candidate'] is None
    assert 'Профессия должна' not in json.dumps(public,ensure_ascii=False)
    # Ordinary title edit cannot remove a failed check, and Resume uses this version.
    changed=client.patch(url,json={'revision':d['revision'],'operation':'patch','kind':'campaign','field':'title','value':'Сохранённый мир'})
    assert changed.status_code==200,changed.text
    d=changed.json();assert d['review']['status']=='stale'
    assert client.post(url+'/confirm',json={'revision':d['revision'],'version_id':d['version_id']}).status_code==409
    reviews=[]
    def recovered(**kw):
        calls.append(kw)
        if kw['messages'][0]['content'].startswith(review.MARKER):
            payload=json.loads(kw['messages'][1]['content']);assert payload['candidate']['campaign']['title']=='Сохранённый мир'
            reviews.append(payload)
            yield json.dumps({'issues':findings() if len(reviews)==1 else [{'severity':'recommendation','message':'Бытовые детали можно расширить позднее'}]})
        else:
            assert 'patches' in kw['messages'][0]['content']
            yield json.dumps({'patches':corrections()})
    with patch('backend.services.preparation.chat_stream',side_effect=recovered):
        r=client.post(url+'/resume',json={'revision':d['revision'],'api_key':'do-not-export','context_length':131072})
        assert r.status_code==200,r.text
        job=wait_job(client,jid);assert job['status']=='saved',job
    assert len(calls)==7  # world + three failed strategies + fresh review + repair + review
    d=client.get(url+'?author=true').json()
    assert d['review']['status']=='completed' and d['review']['issues'][0]['severity']=='recommendation'
    started=client.post(url+'/confirm',json={'revision':d['revision'],'version_id':d['version_id'],'accept_warnings':True});assert started.status_code==200,started.text
    sid=started.json()['save'];repo=app.state.repository
    from test_runtime_v3_engine import run as play,raw_for
    from test_engine import CONFIG
    for kind in ('start','turn','turn'):
        before=repo.get_snapshot(sid);gamejob=repo.begin_job(sid,'Осматриваюсь.' if kind=='turn' else '',kind,CONFIG)
        play(repo,gamejob,raw_for(before));assert repo.get_job(gamejob)['status']=='saved'
        repo=Repository(repo.path);world=repo.get_snapshot(sid)['world_state']
        assert world['meta']['npc_expressiveness']=='hyperbolized'
        assert world['facts']['f1']['visibility']=='secret'
        assert world['knowledge']['c8:f1']['status']=='unknown'
        assert world['relationships']


def test_legacy_failed_job_and_late_worker_cannot_overwrite_resume(tmp_path):
    from backend.services.preparation import Preparation
    from backend.services.draft_generation import run
    from test_initial_draft_v4 import Handle
    import hashlib
    repo=Repository(tmp_path/'legacy.sqlite');w=repo.create_workspace('Legacy')
    config=dict(REMOTE,_draft_task='world',_draft_input=SHORT)
    jid=repo.begin_preparation(w['id'],'draft_world',SHORT,config,0)
    def part(text):return dict(text=text,offset=0,sha256=hashlib.sha256(text.encode()).hexdigest(),finish_reason='stop')
    raw=json.dumps(rich());bad='{"issues":null}'
    journal={'responses':{'world':{'complete':True,'parts':[part(raw)]},'old-review':{'complete':True,'parts':[part(bad)]}},'review_failures':[{'slot':'old-review','error':'old parser'}]}
    repo.save_response_journal(jid,journal)
    repo.save_draft_candidate(jid,rich(),[{'path':'/','category':'review_incomplete','message':'Смысловая проверка не завершена.'}])
    repo.preparation_progress(jid,'','error')
    d=repo.draft(w['id'],True);assert d['review']['status']=='failed'
    config=repo.resume_draft_response(jid,revision=d['revision'])
    with pytest.raises(ValueError,match='Устаревший'):repo.save_response_journal(jid,journal)
    with pytest.raises(ValueError,match='Устаревший'):repo.save_draft_candidate(jid,rich(),[],epoch=0)
    with pytest.raises(ValueError,match='Устаревший'):repo.finish_draft_job(jid,rich(),epoch=0)
    calls=[]
    def stream(**kw):
        calls.append(kw)
        assert kw['messages'][0]['content'].startswith(review.MARKER)
        feedback=json.loads(kw['messages'][-1]['content'])
        assert feedback['rejected_response']==bad
        yield '{"issues":[{"message":"Необязательное уточнение стиля","severity":"recommendation"}]}'
    run(Preparation(repo),jid,config,None,Handle(),None,stream)
    assert len(calls)==1 and repo.preparation_job(jid)['status']=='saved'
    d=repo.draft(w['id'],True)
    assert d['technical_valid'] and d['review']['status']=='completed'
    # A completed current review is reused after an explicitly resumed saved job.
    config=repo.resume_draft_response(jid,revision=d['revision'])
    run(Preparation(repo),jid,config,None,Handle(),None,lambda **kw:pytest.fail('replayed accepted review'))
    assert repo.preparation_job(jid)['status']=='saved'


def test_report_repair_keeps_valid_sibling_and_malformed_patch_feedback(api):
    client,app=api;wid=client.post('/api/workspaces',json={'name':'Mixed report'}).json()['id'];url=f'/api/workspaces/{wid}/draft'
    calls=[];state=rich()
    good={'path':'/campaign/title','message':'Название противоречит замыслу'}
    bad={'severity':'unknown','message':'Не терять сообщение'}
    def stream(**kw):
        calls.append(kw);n=len(calls)
        if n==1:yield json.dumps(state)
        elif n==2:yield json.dumps({'issues':[good,bad]})
        elif n==3:
            feedback=json.loads(kw['messages'][-1]['content'])
            assert feedback['validation_errors'][0]['report_path']=='/issues/1/severity'
            assert feedback['original_indices']==[1]
            assert json.loads(feedback['rejected_response'])=={'issues':[bad]}
            yield json.dumps({'issues':[dict(bad,severity='recommendation')]})
        elif n==4:yield '{"patches":[{"path":"/campaign","value":{}}]}'
        elif n==5:
            feedback=json.loads(kw['messages'][-1]['content'])
            assert 'rejected_response' in feedback and 'неразрешённый путь' in feedback['error']
            yield '{"patches":[{"path":"/campaign/title","value":"Согласованное название"}]}'
        else:yield json.dumps({'issues':[dict(bad,severity='recommendation')]})
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        jid=client.post(url+'/generate',json={'revision':0,'text':SHORT,'config':REMOTE,'api_key':'test'}).json()['id']
        job=wait_job(client,jid);assert job['status']=='saved',job
    raw=client.get(url+'/raw').json()
    assert raw['review_failures'][0]['partial_issues'][0]['message']==good['message']
    assert raw['repair_failures'][0]['rejected_response']
    assert len(calls)==6
