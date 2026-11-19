"""New generation defaults, archived paid responses and atomic offline recovery."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from backend.api.schemas import ModelConfig
from backend.repositories.documents import ROOT, is_builtin_prompt
from backend.repositories.drafts import candidate_hash
from backend.repositories.preparation import Repository
from backend.services import draft_generation, draft_response, draft_creative, draft_initial
from backend.services.draft_changes import apply_proposal
from backend.services.token_budget import prepare, snapshot
from generation266_fixture import seed
from test_api import api
from test_draft_creative import candidate, proposal, change


def test_exact_prompt_upgrade_and_immutable_request(tmp_path):
    repo=Repository(tmp_path/'prompt.sqlite')
    name='draft_world_prompt.md'
    old=(Path(__file__).parent/'fixtures/initial_world/historical_world_prompt.md').read_text()
    sha=hashlib.sha256(old.encode()).hexdigest()
    assert sha=='1f05837f4c8ea397ad9c46acc89b04a254cc6562fba25b9fccd7651f8e38aab2'
    current=(ROOT/name).read_text()
    wid=repo.create_workspace('Архив')['id']
    with repo.connect() as db:
        db.execute('DELETE FROM prompt_upgrades WHERE name=? AND old_hash=?',(name,sha))
        previous=repo._record_document(db,'prompt',name,old)
    jid=repo.begin_preparation(wid,'draft_world','',dict(_draft_task='world',_draft_input='Приморский город'),0)
    recorded=[dict(role='system',content=old)]
    repo.save_response_journal(jid,{'messages':recorded})
    repo.init_documents()
    config=json.loads(repo.preparation_job(jid)['config_json'])
    assert config['_prompts'][name]['content']==old
    assert json.loads(repo.preparation_job(jid)['response_journal'])['messages']==recorded
    assert draft_generation.messages_for(repo,{'workspace_id':wid},config)[0]['content'].startswith(current)
    with repo.connect() as db:
        row=db.execute("SELECT v.* FROM document_heads h JOIN document_versions v ON h.version_id=v.id WHERE h.owner=?",(name,)).fetchone()
        assert row['content']==current and row['source_version_id']==previous
        repo._record_document(db,'prompt',name,old+' ')
    repo.init_documents()
    assert not is_builtin_prompt(name,old+' ')
    assert repo.document_history('prompt',name)['prompt_origin']=='custom_unverified'


@pytest.mark.parametrize('text',['{} {}','{} trailing','{"a":1,"a":2}\n}','{"a":"unfinished}', '{}\n}}','[]\n}'])
def test_creative_does_not_discard_ambiguous_content(text):
    with pytest.raises(ValueError):draft_creative.proposal_text(text)


def test_stable_id_does_not_grant_edit_rights():
    state=candidate();card=state['characters'][1];path='/characters/'+card['id']+'/fields/Внешность'
    raw=proposal(state,[change(path,'Светлая прядь у виска.','replace')])+'\n}'
    clean,why=draft_creative.proposal_text(raw)
    trial,_=apply_proposal(state,clean)
    assert why=='extra_outer_brace' and trial['characters'][1]['fields']['Внешность']!=card['fields']['Внешность']
    state.setdefault('authoring',{})['manual_paths']=['/characters/1/fields/Внешность']
    with pytest.raises(ValueError):apply_proposal(state,clean)
    for op,address in [('replace',path),('remove','/characters/'+card['id']),('replace','/characters/missing/fields')]:
        with pytest.raises(ValueError):apply_proposal(state,proposal(state,[change(address,'x',op)]))


@pytest.mark.parametrize('newer',[True,False])
def test_atomic_recovery_across_restart_and_repeated_confirmation(api,newer):
    client,app=api;repo=app.state.repository
    ids=seed(repo,newer=newer);wid,jid=ids['wid'],ids['jid']
    url=f"/api/workspaces/{wid}/draft/creative/{jid}/{ids['base']}"
    before=repo.draft(wid,True);journal=json.loads(repo.preparation_job(jid)['response_journal'])
    preview=client.get(url).json()
    mode='copy' if newer else 'current'
    assert preview['mode']==mode and len(preview['changes'])==1
    body=dict(revision=before['revision'],destination=mode)
    assert client.post(url,json=dict(body,revision=0)).status_code>=400
    first=client.post(url,json=body)
    assert first.status_code==200,first.text
    receipt=first.json()
    assert client.post(url,json=body).json()==receipt==client.get(url).json()
    reopened=Repository(repo.path)
    target=reopened.draft(receipt['workspace_id'],True)
    assert target['state']['characters'][1]['fields']['Внешность']=='У левого виска светлая прядь.'
    saved=json.loads(reopened.preparation_job(jid)['response_journal'])
    assert saved['actual_tokens']==journal['actual_tokens'] and saved['actual_cost']==journal['actual_cost']
    if newer:
        assert reopened.draft(wid,True)['version_id']==before['version_id']
        assert reopened.draft(wid,True)['state']['campaign']['title']=='Поздняя редакция автора'
        finish=f'/api/workspaces/{wid}/draft/finish/{jid}'
        assert client.post(finish,json={'revision':before['revision']}).status_code==200
        done=reopened.draft(wid,True)
        assert not done['version_is_candidate'] and done['review']['issues']==before['review']['issues']
        assert client.post(finish,json={'revision':before['revision']}).json()['version_id']==done['version_id']


def test_world_low_policy_scale_and_frozen_legacy_snapshot():
    cfg=ModelConfig(provider='deepseek',model='deepseek-v4-flash',thinking='low').model_dump()
    messages=[dict(role='user',content='В приморском городе живут несколько семей.')]
    outputs=[]
    for size in ('small','medium','large'):
        config=prepare(dict(cfg,_draft_task='world',_creation_settings={'cast_preset':size}),'draft_world')
        plan=draft_response.stage_output_plan('world',messages,config)
        assert plan['reasoning_allowance']==2*plan['visible_target']
        assert plan['output_limit']<=config['_budget_caps']['max_output']
        outputs.append(plan['output_limit'])
    assert outputs==sorted(set(outputs))
    manual=prepare(dict(cfg,budget_mode='manual',max_tokens=4096),'draft_world')
    assert draft_response.stage_output_limit('world',messages,manual)==4096
    old=snapshot(config)
    del old['_world_budget_policy'],old['_world_reasoning_ratio']
    old['max_tokens']=33536
    replay=prepare(dict(cfg,_budget_snapshot=old),'draft_world')
    assert '_world_reasoning_ratio' not in replay and replay['max_tokens']==33536


@pytest.mark.skipif(not os.getenv('RPG_GENERATION266_EXPORT'),reason='private original supplied separately')
def test_original_export_exact_bases():
    raw=Path(os.environ['RPG_GENERATION266_EXPORT']).read_bytes()
    assert hashlib.sha256(raw).hexdigest()=='fa6f113176acebdb100a2302ee005437cc2b5ba35eec9eb3db57e1cb36d9503a'
    archive=json.loads(raw);final=archive['candidate_snapshot'];jid=archive['job_id']
    assert not draft_initial.inspect_candidate(final,for_start=True)[1]['errors']
    states=[]
    repo=SimpleNamespace(preparation_job=lambda _:dict(workspace_id='archive'),draft=lambda *a,**kw:dict(state=None),
        draft_phase=lambda *a,**kw:None,save_response_journal=lambda *a:None,
        save_draft_candidate=lambda _,state,*a,**kw:states.append(deepcopy(state)))
    cfg=dict(_draft_source=archive['author_input']['source_text'],_draft_task='world',_creation_settings=final['creation_settings'],
             provider='deepseek',model='deepseek-v4-flash',max_tokens=33536,temperature=1,context_length=1000000,
             _prompts={'draft_world_prompt.md':dict(content='archive')})
    parts=archive['responses']['world']['parts']
    with patch.object(draft_response,'response',return_value=''.join(p['text'] for p in parts)),patch.object(draft_creative,'develop',return_value=None):
        draft_generation.run(SimpleNamespace(repo=repo),jid,cfg,None,SimpleNamespace(cancel=Event()),None,None)
    base=states[-1]
    second=deepcopy(base)
    second['world']['characters']=final['world']['characters']
    second['authoring']['calendar_completion']=final['authoring']['calendar_completion']
    for state,record,expected in zip((base,second),[*archive['creative_history'],archive['creative']],[(88,12,9),(22,8,3)]):
        assert candidate_hash(state)==record['before_hash']
        clean,why=draft_creative.proposal_text(record['current_reply'])
        restored,batch=apply_proposal(state,clean)
        assert (len(batch['changes']),len(restored['characters']),len(restored['locations']))==expected
        assert why==('extra_outer_brace' if expected[0]==88 else None)
        if why:assert any('Тимур' in c['name'] and 'Внешность' in c['fields'] for c in draft_creative.npc_gaps(restored))
    assert final['locations'][1]!=restored['locations'][1]
