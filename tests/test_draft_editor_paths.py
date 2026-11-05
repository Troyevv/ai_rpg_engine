"""Recorded Olya proposal and narrowly scoped card identity addressing."""
import json
from copy import deepcopy
from pathlib import Path
import pytest
from backend.repositories.drafts import candidate_hash
from backend.services.draft_changes import apply_proposal, Proposal, ProposalError, resolve_card_paths
from backend.services import draft_creative_repair as correction


def recorded():
    return json.loads((Path(__file__).parent/'fixtures/draft_editor/ilya_sister_olya.json').read_text())


@pytest.mark.parametrize('reorder',[False,True])
def test_exact_olya_reply(reorder):
    f=recorded();s=f['base']['state'];p=json.loads(f['reply'])
    if reorder:s['characters'].reverse()
    p['candidate_hash']=candidate_hash(s);before=deepcopy(s)
    out, normalized=apply_proposal(s,json.dumps(p),editing=True)
    index=next(i for i,c in enumerate(s['characters']) if c['id']=='ilya')
    assert normalized['changes'][2]['path']==f'/characters/{index}/fields/Биография'
    assert len(normalized['changes'])==13
    assert s==before
    assert out['world']['characters']['olya']['scene_id'] is None
    for key in ('camera','world_clock','controlled_actor_id'):assert out[key]==s[key]
    for cid in ('sonya','maxim'):assert out['world']['characters'][cid]==s['world']['characters'][cid]
    assert out['world']['characters']['ilya']==s['world']['characters']['ilya']
    for key,val in s['world']['facts'].items():assert out['world']['facts'][key]==val


@pytest.mark.parametrize('path',['/characters/missing/fields/Биография','/characters/99/fields/Биография','/characters/ilya/missing/text'])
def test_bad_path_has_bounded_correction(path):
    f=recorded();s=f['base']['state'];p=json.loads(f['reply']);p['changes'][2]['path']=path
    raw=json.dumps(p)
    with pytest.raises(ProposalError) as e:apply_proposal(s,raw,editing=True)
    allowed=correction.scope(s,raw,e.value)
    assert allowed['paths']==['/changes/2/path']
    assert path in str(e.value)
    fixed=correction.apply(raw,json.dumps(dict(proposal_hash=allowed['proposal_hash'],patches=[dict(path='/changes/2/path',value='/characters/ilya/fields/Биография')],drop_indices=[])),allowed)
    assert json.loads(fixed)['changes'][:2]==p['changes'][:2]
    assert json.loads(fixed)['changes'][3:]==p['changes'][3:]
    assert len(apply_proposal(s,fixed,editing=True)[1]['changes'])==13


def test_duplicate_id_rejected():
    f=recorded();s=f['base']['state'];s['characters'].append(deepcopy(s['characters'][0]))
    p=json.loads(f['reply']);p['candidate_hash']=candidate_hash(s)
    with pytest.raises(ProposalError,match='Неоднозначный'):apply_proposal(s,json.dumps(p),editing=True)


def test_preceding_add_and_removed_entity():
    s={'characters':[{'id':'a','fields':{}}],'locations':[]}
    def op(kind,path,value):return dict(op=kind,path=path,value=value,reason='test')
    p=Proposal(candidate_hash='unused',rationale='test',changes=[op('add','/characters/-',{'id':'b','fields':{}}),op('add','/characters/b/fields/text','new')])
    resolve_card_paths(s,p)
    assert p.changes[1].path=='/characters/1/fields/text'
    p=Proposal(candidate_hash='unused',rationale='test',changes=[op('remove','/characters/a',s['characters'][0]),op('add','/characters/a/fields/text','new')])
    with pytest.raises(ProposalError,match='удалённой'):resolve_card_paths(s,p)

from unittest.mock import patch
from test_api import api, wait_job
from test_draft_editor import request, decide
from backend.services import draft_editor, draft_completeness


def test_olya_job_preview_apply_start_and_restore(api):
    client, app=api
    f=recorded()
    wid=client.post('/api/workspaces',json={'name':'Оля'}).json()['id']
    url=f'/api/workspaces/{wid}/draft'
    r=client.post(url+'/import',json={'revision':0,'format':'json','text':json.dumps(f['base']['state'])})
    assert r.status_code==200,r.text
    before=client.get(url+'?author=true').json();calls=[]
    def stream(**kw):
        data=json.loads(kw['messages'][1]['content']);system=kw['messages'][0]['content']
        kw['on_usage']({'prompt_tokens':100,'completion_tokens':40});kw['on_finish']('stop')
        if system.startswith(draft_editor.MARKER):
            calls.append('proposal');p=json.loads(f['reply']);p['candidate_hash']=candidate_hash(data['candidate']);yield json.dumps(p)
        else:
            assert system.startswith(draft_completeness.MARKER)
            calls.append('review');yield json.dumps({'issues':[]})
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        r=request(client,url,before,text='Создай сестру Ильи');assert r.status_code==200,r.text
        job=wait_job(client,r.json()['id']);assert job['status']=='saved',job.get('error')
    assert calls==['proposal','review']
    current=client.get(url+'?author=true').json();assert current['state']==before['state']
    edit=client.get(url+'/edits?author=true').json()['edits'][0]
    assert edit['status']=='preview' and len(edit['proposal']['changes'])==13
    assert decide(client,url,current,edit).status_code==200
    accepted=client.get(url+'?author=true').json()
    assert accepted['version_id']!=before['version_id']
    assert decide(client,url,current,edit).status_code==200
    r=client.post(url+'/confirm',json={'revision':accepted['revision'],'version_id':accepted['version_id'],'accept_warnings':True});assert r.status_code==200,r.text
    snapshot=app.state.repository.get_snapshot(r.json()['save'])
    assert 'olya' in snapshot['world_state']['characters']
    assert 'olya' not in snapshot['world_state']['camera']['present_character_ids']
    current=client.get(url+'?author=true').json()
    restored=client.patch(url,json={'revision':current['revision'],'operation':'restore','source_id':before['version_id']})
    assert restored.status_code==200 and restored.json()['state']==before['state']
    assert app.state.repository.get_snapshot(r.json()['save'])==snapshot
