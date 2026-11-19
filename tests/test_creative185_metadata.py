"""Paid Sosnovka reply: provider text is real; tests never call live DeepSeek."""
import json
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import pytest
from test_api import api, REMOTE, wait_job
from backend.services import draft_creative, draft_creative_repair, draft_completeness
from backend.services.draft_changes import apply_proposal, ProposalError
from backend.services.draft_initial import SERVER_FIELDS, prompt_schema
from backend.repositories.drafts import candidate_hash

FIXTURE=Path(__file__).parent/'fixtures/creative185/sosnovka.json'

def saved():return json.loads(FIXTURE.read_text())


def test_paid_rejected_reply_revalidates_without_call_or_partial_apply():
    data=saved();state=data['candidate'];before=deepcopy(state)
    journal=dict(creative=data['creative'],actual_tokens=123,requests=['keep'],responses={'keep':{'parts':['paid']}})
    original=deepcopy(journal)
    def no_call(*_):pytest.fail('paid creative must not be regenerated or corrected')
    after=draft_creative.develop(state,'brief',journal,no_call,lambda:None)
    assert state==before
    assert journal['creative']['status']=='applied'
    assert journal['creative']['original_reply']==original['creative']['original_reply']
    assert journal['creative']['current_reply']==original['creative']['current_reply']
    assert len(journal['creative']['proposal']['changes'])==7
    assert journal['creative']['corrections']==[]
    for key in ('requests','responses','actual_tokens'):assert journal[key]==original[key]
    for name in ('sonya','maxim','ilya'):
        assert 'revision' not in after['world']['knowledge']['know_'+name+'_repair']
    from backend.runtime_v3.migration import migrate_v2
    runtime=migrate_v2(after).snapshot['world_state']
    assert runtime['knowledge']['sonya:fact_house_repair']['revision']==0
    assert runtime['knowledge']['ilya:fact_house_repair']['status']=='unknown'
    assert draft_creative.develop(after,'brief',journal,no_call,lambda:None)==after
    assert draft_creative.develop(before,'brief',journal,no_call,lambda:None)==after


@pytest.mark.parametrize('value',[1,-1,True,'0',None])
def test_invalid_revision_has_exact_correction_scope_and_is_atomic(value):
    data=saved();state=data['candidate'];before=deepcopy(state);proposal=json.loads(data['creative']['current_reply'])
    proposal['changes'][3]['value']['revision']=value
    text=json.dumps(proposal)
    with pytest.raises(ValueError) as exc:apply_proposal(state,text)
    allowed=draft_creative_repair.scope(state,text,exc.value)
    assert allowed['paths']==[]
    assert allowed['remove_paths']==['/changes/3/value/revision']
    assert state==before
    correction=dict(proposal_hash=allowed['proposal_hash'],patches=[],remove_paths=allowed['remove_paths'],drop_indices=[])
    fixed=draft_creative_repair.apply(text,json.dumps(correction),allowed)
    assert len(apply_proposal(state,fixed)[1]['changes'])==7
    assert 'revision' not in json.loads(fixed)['changes'][3]['value']
    correction['remove_paths']=['/changes/0/value/name']
    with pytest.raises(ValueError):draft_creative_repair.apply(text,json.dumps(correction),allowed)


@pytest.mark.parametrize('field,value',[('revision',5),('source_turn',7),('authoring',{'source':'fake'}),
    ('birth_provenance',{'source':'fake'}),('field_facts',{'owner_id':'fake'}),('applied',{'fake':'fact'}),
    ('remote_source_ids',['fake']),('confirmed_once',True),('source_sequence',4),
    ('reviewed_signature','forged'),('time_reference_minute',999)])
@pytest.mark.parametrize('section',['knowledge','facts','characters','relationships','events','possessions','organizations','roles','residences','conditions','threads','scheduled_events',
    'pregnancies','reproductive_events','naming_decisions'])
def test_server_metadata_cannot_be_minted_in_any_record(section,field,value):
    state=saved()['candidate']
    proposal=dict(candidate_hash=candidate_hash(state),rationale='test',changes=[dict(op='add',
        path=f'/world/{section}/new185',value={field:value},reason='test')])
    with pytest.raises(ProposalError) as exc:apply_proposal(state,json.dumps(proposal))
    allowed=draft_creative_repair.scope(state,json.dumps(proposal),exc.value)
    assert allowed['paths']==[]
    assert allowed['remove_paths']==[f'/changes/0/value/{field}']
    fixed=draft_creative_repair.apply(json.dumps(proposal),json.dumps(dict(
        proposal_hash=allowed['proposal_hash'],patches=[],remove_paths=allowed['remove_paths'],drop_indices=[])),allowed)
    assert json.loads(fixed)['changes'][0]['value']=={}
    # A null assignment must not masquerade as deleting model authority.
    with pytest.raises(ValueError):draft_creative_repair.apply(json.dumps(proposal),json.dumps(dict(
        proposal_hash=allowed['proposal_hash'],patches=[dict(path=allowed['remove_paths'][0],value=None)],drop_indices=[])),allowed)


def test_existing_revision_and_nested_provenance_remain_protected():
    state=saved()['candidate']
    key=next(iter(state['world']['knowledge']))
    proposal=dict(candidate_hash=candidate_hash(state),rationale='test',changes=[dict(op='replace',
        path=f'/world/knowledge/{key}/revision',value=1,reason='test')])
    with pytest.raises(ProposalError):apply_proposal(state,json.dumps(proposal))
    def walk(node):
        if isinstance(node,dict):
            assert not SERVER_FIELDS & node.get('properties',{}).keys()
            for v in node.values():walk(v)
        elif isinstance(node,list):
            for v in node:walk(v)
    walk(prompt_schema())


def test_optional_creative_rejection_keeps_valid_base_review_and_confirmation(api):
    client,app=api;calls=[];data=saved()
    def stream(**kw):
        system=kw['messages'][0]['content'];calls.append(system)
        if system.startswith(draft_creative.MARKER):
            p=json.loads(data['creative']['current_reply']);p['candidate_hash']=json.loads(kw['messages'][1]['content'])['candidate_hash'];value=p
        elif system.startswith(draft_completeness.MARKER):value={'issues':[]}
        else:
            value=deepcopy(data['candidate']);value['world'].pop('contacts',None)
        kw['on_finish']('stop');kw['on_usage']({'prompt_tokens':100,'completion_tokens':20})
        yield json.dumps(value,ensure_ascii=False)
    wid=client.post('/api/workspaces',json={'name':'Sosnovka185'}).json()['id'];url=f'/api/workspaces/{wid}/draft'
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        with patch.object(draft_creative,'VALIDATION_VERSION',1),patch.object(draft_creative,'apply_proposal',side_effect=ValueError('Модель не может назначать серверное происхождение: revision')):
            r=client.post(url+'/generate',json=dict(revision=0,text='Сосновка.',config=dict(REMOTE,context_length=131072,max_tokens=20000),api_key='offline'))
            assert r.status_code==200,r.text
            jid=r.json()['id'];assert wait_job(client,jid)['status']=='saved'
    # Current production deliberately continues from the structurally valid base.
    # Historical rejected-journal revalidation remains tested above without calls.
    assert len(calls)==3 and calls[-1].startswith(draft_completeness.MARKER)
    draft=client.get(url+'?author=true').json();raw=client.get(url+'/raw').json()
    assert draft['review']['status']=='completed'
    assert raw['creative']['status']=='rejected' and raw['creative']['correction_complete']
    assert raw['creative']['corrections']==[]
    journal=json.loads(app.state.repository.preparation_job(jid)['response_journal'])
    assert json.loads(journal['candidate_text'])['world']['knowledge']==data['candidate']['world']['knowledge']
    assert 'loc_sonya_room' not in {row['id'] for row in draft['state']['locations']}
    result=client.post(url+'/confirm',json=dict(revision=draft['revision'],version_id=draft['version_id'],accept_warnings=True))
    assert result.status_code==200,result.text
    sid=result.json()['save'];snap=app.state.repository.get_snapshot(sid)['world_state']
    assert 'loc_sonya_room' not in snap['locations'] and 'poss_sonya_tablet' not in snap['possessions']
    assert client.get(f'/api/saves/{sid}').status_code==200
    assert client.post(url+'/confirm',json=dict(revision=draft['revision'],version_id=draft['version_id'],accept_warnings=True)).json()['save']==sid



@pytest.mark.parametrize('root',['characters','locations'])
def test_appended_card_nested_provenance_has_proposal_address(root):
    data=saved();state=data['candidate']
    card=deepcopy(state[root][0]);card['id']='new185'
    card['birth_provenance']={'source':'forged'}
    if root=='characters':card['is_player']=False
    p=dict(candidate_hash=candidate_hash(state),rationale='test',changes=[dict(op='add',path='/'+root+'/-',value=card,reason='test')])
    with pytest.raises(ProposalError) as exc:apply_proposal(state,json.dumps(p))
    scope=draft_creative_repair.scope(state,json.dumps(p),exc.value)
    assert scope['paths']==[] and scope['remove_paths']==['/changes/0/value/birth_provenance']
    fixed=draft_creative_repair.apply(json.dumps(p),json.dumps(dict(
        proposal_hash=scope['proposal_hash'],patches=[],remove_paths=scope['remove_paths'],drop_indices=[])),scope)
    expected=deepcopy(card);del expected['birth_provenance']
    assert json.loads(fixed)['changes'][0]['value']==expected


def test_upgrade_revalidation_does_not_reset_failed_correction_budget():
    data=saved();state=data['candidate'];record=data['creative']
    p=json.loads(record['current_reply']);p['changes'][3]['value']['revision']=7
    record['current_reply']=json.dumps(p);record['corrections']=[{'error':'old1'},{'error':'old2'}]
    journal={'creative':record};before=deepcopy(state)
    for _ in range(2):
        with pytest.raises(ValueError):draft_creative.develop(state,'brief',journal,lambda *_:pytest.fail('no extra request'),lambda:None)
    assert state==before and len(record['corrections'])==2
    assert record['validation_version']==draft_creative.VALIDATION_VERSION
    assert record['diagnostics'][0]['path']=='/world/knowledge/know_sonya_repair/revision'


def test_appended_card_diagnostic_does_not_grant_access_to_other_cards():
    state=saved()['candidate'];changes=[]
    for i in range(2):
        card=deepcopy(state['locations'][0]);card['id']='new'+str(i)
        if i==1:card['birth_provenance']={'source':'forged'}
        changes.append(dict(op='add',path='/locations/-',value=card,reason='test'))
    p=dict(candidate_hash=candidate_hash(state),rationale='test',changes=changes)
    with pytest.raises(ProposalError) as exc:apply_proposal(state,json.dumps(p))
    scope=draft_creative_repair.scope(state,json.dumps(p),exc.value)
    assert scope['remove_paths']==['/changes/1/value/birth_provenance']
    assert scope['paths']==[]
