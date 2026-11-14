"""Reduced regressions from the retained Life248 world-generation responses."""
from copy import deepcopy
import json
import pytest
from backend.services import draft_initial, draft_repair, draft_creative
from test_initial_draft_v4 import rich
from test_api import api, wait_job
from unittest.mock import patch


def dependencies_case():
    s=rich();cid=s['characters'][1]['id'];s['world']['characters'][cid]['goals']=[dict(id='g',text='Keep the cafe open',status='active',evidence='Original evidence',dependencies={'facts':['ownership'],'organizations':['bank']})]
    s['world']['roles']['job']['fact_id']='ownership'
    return s,cid


def test_initial_collects_dependencies_and_provenance_without_loss():
    s,cid=dependencies_case();before=deepcopy(s);_,report=draft_initial.inspect_candidate(s)
    assert s==before
    paths={e['path'] for e in report['diagnostics']}
    assert f'/world/characters/{cid}/goals/0/dependencies' in paths
    assert '/world/roles/job/fact_id' in paths


def test_generation_dependency_schema_matches_runtime():
    import jsonschema
    schema=draft_initial.prompt_schema()['properties']['world']['properties']['characters']['additionalProperties']['properties']['goals']['items']['properties']['dependencies']
    jsonschema.validate({'organizations':['bank']},schema)
    with pytest.raises(jsonschema.ValidationError):jsonschema.validate({'facts':['ownership']},schema)


def test_explicit_dependency_repair_preserves_unsupported_input_as_evidence():
    s,cid=dependencies_case();_,report=draft_initial.inspect_candidate(s)
    messages,scope=draft_repair.request(json.dumps(s),report['diagnostics'])
    root=f'/world/characters/{cid}/goals/0'
    issue=next(x for x in report['diagnostics'] if x['path']==root+'/dependencies')
    assert root+'/evidence' in scope
    patches=[dict(path=root+'/dependencies',value={'organizations':['bank']}),dict(path='/world/roles/job/fact_id',value=None)]
    with pytest.raises(ValueError,match='evidence'):draft_repair.apply(json.dumps(s),json.dumps(dict(patches=patches)),scope)
    patches.append(dict(path=root+'/evidence',value='Original evidence\n'+issue['preserve_evidence']))
    fixed=json.loads(draft_repair.apply(json.dumps(s),json.dumps(dict(patches=patches)),scope))
    _,report=draft_initial.inspect_candidate(fixed);assert not report['errors'],report
    assert fixed['world']['characters'][cid]['goals'][0]['text']==s['world']['characters'][cid]['goals'][0]['text']
    patches[0]['value']={}
    with pytest.raises(ValueError):draft_repair.apply(json.dumps(s),json.dumps(dict(patches=patches)),scope)


def test_optional_creative_rejection_finishes_valid_world_with_warnings(api):
    from backend.services import draft_completeness
    client,app=api;state=rich();calls=[]
    def provider(**kw):
        system=kw['messages'][0]['content'];calls.append(system)
        if system.startswith(draft_creative.MARKER):
            payload=json.loads(kw['messages'][1]['content'])
            answer=dict(candidate_hash=payload['candidate_hash'],rationale='Invalid optional extension',changes=[dict(op='replace',path='/world_clock/minute',value=999,reason='Forbidden clock edit')])
        elif system.startswith(draft_completeness.MARKER):answer={'issues':[]}
        elif system.startswith('Адресная коррекция творческого предложения'):
            answer=dict(proposal_hash=json.loads(kw['messages'][1]['content'])['proposal_hash'],patches=[],drop_indices=[])
        else:answer=state
        yield json.dumps(answer,ensure_ascii=False)
    wid=client.post('/api/workspaces',json={'name':'Optional creative'}).json()['id'];url=f'/api/workspaces/{wid}/draft'
    with patch('backend.services.preparation.chat_stream',side_effect=provider):
        q=client.post(url+'/generate',json=dict(revision=0,text='A family in a town',config={'provider':'deepseek','model':'deepseek-flash'},api_key='test'));assert q.status_code==200,q.text
        job=wait_job(client,q.json()['id'])
    assert job['status']=='saved',job.get('error')
    final=client.get(url+'?author=true').json();assert final['technical_valid']
    assert final['state']['world_clock']['minute']==state['world_clock']['minute']
    assert any('Необязательное' in x for x in final['validation']['warnings'])
    assert len(calls)==5
    result=client.post(url+'/confirm',json=dict(revision=final['revision'],version_id=final['version_id'],accept_warnings=True))
    assert result.status_code==200,result.text


def test_new_duplicate_diagnostic_updates_second_repair_scope_atomically(api):
    from backend.services import draft_completeness
    client,app=api;state=rich();cid=state['characters'][1]['id']
    state['world']['knowledge']={'original':dict(actor_id=cid,fact_id='ownership',status='known',evidence='Original'), 'unresolved':dict(actor_id='missing',fact_id='ownership',status='known',evidence='Different')}
    repairs=[]
    def provider(**kw):
        system=kw['messages'][0]['content']
        if system.startswith('Если player_agency:'):
            payload=json.loads(kw['messages'][1]['content']);repairs.append(payload)
            patches=[dict(path='/world/knowledge/unresolved/actor_id',value=cid)]
            if len(repairs)==2:
                assert '/world/knowledge/unresolved/evidence' in {x['path'] for x in payload['errors']}
                assert payload['candidate_hash']==repairs[0]['candidate_hash']
                patches.append(dict(path='/world/knowledge/unresolved/evidence',value='Original'))
            answer=dict(patches=patches)
        elif system.startswith(draft_creative.MARKER):
            payload=json.loads(kw['messages'][1]['content']);answer=dict(candidate_hash=payload['candidate_hash'],rationale='Controlled no-op',changes=[])
        elif system.startswith(draft_completeness.MARKER):answer={'issues':[]}
        else:answer=state
        yield json.dumps(answer,ensure_ascii=False)
    wid=client.post('/api/workspaces',json={'name':'Newly exposed duplicate'}).json()['id'];url=f'/api/workspaces/{wid}/draft'
    with patch('backend.services.preparation.chat_stream',side_effect=provider):
        q=client.post(url+'/generate',json=dict(revision=0,text='A family in a town',config={'provider':'deepseek','model':'deepseek-flash'},api_key='test'))
        assert q.status_code==200,q.text
        job=wait_job(client,q.json()['id'])
    assert job['status']=='saved',job.get('error')
    assert len(repairs)==2
    final=client.get(url+'?author=true').json()
    assert len(final['state']['world']['knowledge'])==1
    row=next(iter(final['state']['world']['knowledge'].values()));assert row['actor_id']==cid and row['evidence']=='Original'
    journal=json.loads(app.state.repository.preparation_job(job['id'])['response_journal'])
    assert journal['repair_failures'][0]['trial']['after'][0]['category']=='duplicate'
    assert state['world']['knowledge']['unresolved']['actor_id']=='missing'


def test_event_fact_knowledge_proposal_is_atomic():
    from backend.services.draft_changes import apply_proposal
    from backend.repositories.drafts import candidate_hash
    s=rich();before=deepcopy(s);cid=s['characters'][1]['id']
    changes=[dict(op='add',path='/world/facts/new_fact',value=dict(id='new_fact',text='A letter was received.',character_ids=[cid],secret=False),reason='Past event'),
             dict(op='add',path='/world/events/new_event',value=dict(id='new_event',text='Received a letter.',participants=[cid],witnesses=[],minute=None,scene_id=None,fact_ids=[],player_observed=False),reason='Past event'),
             dict(op='add',path='/world/knowledge/new_knowledge',value=dict(actor_id=cid,fact_id='new_fact',status='known',source_event_id='new_event',evidence='Received the letter.'),reason='Witnessed')]
    proposal=dict(candidate_hash=candidate_hash(s),rationale='Connected past event',changes=changes)
    with pytest.raises(ValueError):apply_proposal(s,json.dumps(proposal))
    assert s==before
    changes[1]['value']['fact_ids']=['new_fact']
    result,_=apply_proposal(s,json.dumps(proposal))
    assert s==before
    assert result['world']['events']['new_event']['fact_ids']==['new_fact']
    assert next(v for v in result['world']['knowledge'].values() if v['fact_id']=='new_fact')['source_event_id']=='new_event'
