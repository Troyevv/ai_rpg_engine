"""Default HTTP creation: one full response, canonical repair and durable editor."""
import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import pytest
from test_api import api, REMOTE
from test_world_generation import wait
from test_world_authoring import institute, family
from backend.services.draft_generation import capture_world, preserve_unaffected

SHORT='Молодой парень переезжает в Москву, устраивается в НИИ и пытается начать новую жизнь.'
FULL=Path('tests/fixtures/world_authoring/volkov_user_brief.txt').read_text()
CONFIG={**REMOTE,'context_length':32768,'max_tokens':8192}


def submit(client,source=SHORT,task='world_staged',config=None):
    wid=client.post('/api/workspaces',json={'name':'Single world'}).json()['id']
    response=client.post(f'/api/workspaces/{wid}/draft/generate',json=dict(
        task=task,text=source,revision=0,config=config or CONFIG,api_key='fixture'))
    assert response.status_code==200,response.text
    return wid,response.json()['id']


@pytest.mark.parametrize('source',[SHORT,FULL],ids=['short','full-volkov-input'])
@pytest.mark.parametrize('task',['world','world_staged'])
def test_default_creation_one_request_and_playable_edit(api,source,task):
    # Controlled answer verifies transport/lifecycle, not semantic live fidelity.
    client,app=api;seen=[]
    def stream(**kw):
        seen.append(kw)
        assert json.loads(kw['messages'][-1]['content'])['original_source']==source
        yield json.dumps(institute(),ensure_ascii=False)
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        wid,jid=submit(client,source,task);done=wait(client,jid)
    assert done['status']=='saved',done
    assert len(seen)==1
    assert {u['stage'] for u in done['generation']['units']}=={'author_document','compile'}
    repo=app.state.repository
    draft=repo.draft(wid,True)
    repo.edit_draft(wid,draft['revision'],'patch',kind='campaign',field='title',value='Edited')
    draft=repo.draft(wid,True)
    sid=repo.confirm_draft(wid,draft['revision'],draft['version_id'])['save']
    from test_temporal_guard import run
    from backend.repositories.preparation import Repository
    assert run(repo,sid,1,kind='start')[0]['status']=='saved'
    assert run(repo,sid,1)[0]['status']=='saved'
    before=repo.get_snapshot(sid)
    loaded=Repository(repo.path)
    assert loaded.get_snapshot(sid)==before
    assert run(loaded,sid,1)[0]['status']=='saved'


@pytest.mark.parametrize('fault',['reference','type','missing','json'])
def test_repair_receives_original_and_report_and_preserves_content(api,fault):
    client,app=api;good=institute();bad=deepcopy(good);seen=[]
    if fault=='reference':bad['characters'][0]['location']='absent'
    if fault=='type':bad['characters'][0]['biography']=123
    if fault=='missing':del bad['opening']['situation']
    raw='{"broken":' if fault=='json' else json.dumps(bad)
    def stream(**kw):
        seen.append(kw)
        if len(seen)==1:yield raw
        else:
            data=json.loads(kw['messages'][-1]['content'])
            assert data['original_response']==raw
            assert data['validation_report'][0]['path']
            yield json.dumps(good)
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        _,jid=submit(client);done=wait(client,jid)
    assert done['status']=='saved',done
    assert len(seen)==2


def test_two_repairs_max_and_raw_retained_privately(api):
    client,app=api;calls=[]
    def stream(**kw):calls.append(kw);yield '{"private-secret":'
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        _,jid=submit(client);done=wait(client,jid)
    assert done['status']=='failed' and len(calls)==3
    cp=app.state.repository.inspect_generation_checkpoint(jid,'author_document',True)
    assert cp['diagnostic']['raw_response']=='{"private-secret":'
    assert 'private-secret' not in json.dumps(done)


def test_output_limit_never_schema_retried_and_keeps_partial(api):
    from llm import OutputLimitReached
    client,app=api;calls=[]
    def stream(**kw):
        calls.append(kw);yield '{"private":'
        raise OutputLimitReached('limit')
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        _,jid=submit(client);done=wait(client,jid)
    assert done['status']=='failed' and len(calls)==1
    cp=app.state.repository.inspect_generation_checkpoint(jid,'author_document',True)
    assert cp['diagnostic']['raw_response']=='{"private":'
    assert 'private' not in json.dumps(done)


def test_oversize_has_no_planner_or_paid_request(api):
    client,app=api
    with patch('backend.services.preparation.chat_stream') as provider:
        wid=client.post('/api/workspaces',json={'name':'Too large'}).json()['id']
        r=client.post(f'/api/workspaces/{wid}/draft/generate',json=dict(task='world',text=FULL*10,
            revision=0,config=CONFIG,api_key='fixture'))
    assert r.status_code==409
    provider.assert_not_called()
    assert 'author/request/world' in r.text


def test_repair_cannot_rewrite_unaffected_biography():
    before=institute();after=deepcopy(before)
    after['characters'][0]['biography']='A different person'
    with pytest.raises(ValueError):
        preserve_unaffected(before,after,[{'path':'/characters/'+before['characters'][0]['key']+'/location'}])


def test_schema_preserves_domain_fields_and_constraints():
    from backend.services.world_authoring import Document
    captured=capture_world(SHORT,CONFIG)['prompt']['schemas']['author_document']
    original=Document.model_json_schema()
    def check(before,after):
        if isinstance(before,dict):
            for key,value in before.items():
                if key in ('properties','$defs'):
                    assert set(value)==set(after[key])
                    for name in value:check(value[name],after[key][name])
                elif key not in ('title','default'):check(value,after[key])
        elif isinstance(before,list):
            assert len(before)==len(after)
            for a,b in zip(before,after):check(a,b)
        else:assert before==after
    check(original,captured)
    assert 'title' in captured['$defs']['World']['properties']


def test_two_distinct_technical_repairs_do_not_regenerate_good_fields(api):
    client,app=api;good=institute();first=deepcopy(good);second=deepcopy(good)
    first['characters'][0]['location']='missing'
    first['opening']['location']='missing'
    second['characters'][0]['location']='missing'
    replies=iter([first,second,good]);calls=[]
    def stream(**kw):calls.append(kw);yield json.dumps(next(replies))
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        _,jid=submit(client);done=wait(client,jid)
    assert done['status']=='saved',done
    assert len(calls)==3


def test_repair_refuses_creative_rewrite_and_keeps_original(api):
    client,app=api;bad=institute();bad['characters'][0]['location']='missing'
    wrong=institute();wrong['characters'][0]['biography']='Rewritten without permission'
    replies=iter([bad,wrong]);calls=[]
    def stream(**kw):calls.append(kw);yield json.dumps(next(replies))
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        _,jid=submit(client);done=wait(client,jid)
    assert done['status']=='failed' and len(calls)==2
    cp=app.state.repository.inspect_generation_checkpoint(jid,'author_document',True)
    assert json.loads(cp['diagnostic']['raw_response'])==bad


def test_small_context_rejected_without_fallback():
    with pytest.raises(ValueError,match='author/request/world'):
        capture_world(SHORT,{**CONFIG,'context_length':8192})


def test_failed_technical_result_resumes_as_repair_without_new_world(api):
    client,app=api;bad=institute();bad['characters'][0]['location']='missing';calls=[]
    # Pause at the repair boundary, leaving a durable raw result and report.
    repo=app.state.repository;original_fail=repo.fail_generation_unit
    def fail(jid,token,unit,error):
        original_fail(jid,token,unit,error)
        if unit=='author_document':repo.generation_control(jid,'pause')
    with patch.object(repo,'fail_generation_unit',side_effect=fail), patch(
            'backend.services.preparation.chat_stream',return_value=iter([json.dumps(bad)])):
        _,jid=submit(client);paused=wait(client,jid)
    assert paused['status']=='paused',paused
    def repaired(**kw):
        calls.append(kw)
        assert json.loads(kw['messages'][-1]['content'])['original_response']==json.dumps(bad)
        yield json.dumps(institute())
    with patch('backend.services.preparation.chat_stream',side_effect=repaired):
        r=client.post('/api/jobs/'+jid+'/generation/resume',json={
            'revision':paused['generation']['revision'],'api_key':'fixture'})
        assert r.status_code==200,r.text
        done=wait(client,jid)
    assert done['status']=='saved',done
    assert len(calls)==1
