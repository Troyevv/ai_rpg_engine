"""Replay the paid DeepSeek response, with real jobs/storage/normalization/handoff."""
import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import pytest
from test_api import api, wait_job
from test_draft_editor import request, decide
from backend.repositories.drafts import candidate_hash
from backend.services import draft_editor, draft_completeness, draft_creative_repair as correction
from backend.services.draft_changes import apply_proposal, validate_candidate, ProposalError

FIXTURE = Path(__file__).parent/'fixtures/draft_editor/ilya_sister.json'


def recorded():
    return json.loads(FIXTURE.read_text())


def reply_for(state, *, clean=False):
    p=json.loads(recorded()['reply']);p['candidate_hash']=candidate_hash(state)
    if clean:p['changes'].pop()
    return json.dumps(p,ensure_ascii=False)


def assert_vera(before, after):
    w=after['world'];v=w['characters']['vera']
    assert len([c for c in after['characters'] if c['id']=='vera'])==1
    card=next(c for c in after['characters'] if c['id']=='vera')
    assert card['name']=='Вера Соколова' and card['fields']['Возраст']=='23 года'
    assert v['birth_date']=='2003-04-11' and v['biological_sex']=='female' and v['developmental_stage']=='adult'
    assert v['location']=='loc_sokolovy_tver' and v['scene_id'] is None
    assert v['minute']==before['world_clock']['minute']
    assert 'Вера' in after['characters'][0]['fields']['Биография']
    assert v['goals'][0]['text'] and v['intentions'][0]['text']
    for item in v['goals']+v['intentions']:
        assert item['revision']==0 and item['review_required']==[] and item['reviewed_signature']==''
    assert w['objective_relations']['obj_rel_ilya_vera_sibling']['kind']=='sibling'
    assert w['residences']['res_vera_tver']['location_id']==v['location']
    assert {w['roles'][k]['actor_id'] for k in ('role_vera_student','role_vera_bookstore')}=={'vera'}
    assert w['relationships']['rel_ilya_vera']['target_id']=='vera'
    assert w['relationships']['rel_vera_ilya']['target_id']=='ilya'
    assert {k['actor_id'] for k in w['knowledge'].values() if k['fact_id']=='fact_ilya_sister'}=={'ilya','vera','sonya','maxim'}
    for key in ('world_clock','camera','controlled_actor_id','protagonist_id'):
        assert after[key]==before[key]
    for section in ('scenes','scene_records','events','scheduled_events'):
        assert w[section]==before['world'][section]
    assert all('vera' not in s['participants'] for s in w['scenes'].values())
    assert w['characters']['ilya']==before['world']['characters']['ilya']  # no agency
    for section in ('facts','knowledge'):
        for key,val in before['world'][section].items():assert w[section][key]==val
    for cid in ('sonya','maxim'):
        assert w['characters'][cid]==before['world']['characters'][cid]
        assert next(c for c in after['characters'] if c['id']==cid)==next(c for c in before['characters'] if c['id']==cid)


def test_exact_recorded_reply_and_server_normalization():
    f=recorded();s=f['base']['state'];original=deepcopy(s)
    assert json.loads(f['reply'])['candidate_hash']==candidate_hash(s)
    with pytest.raises(ProposalError) as e:apply_proposal(s,f['reply'],editing=True)
    allowed=correction.scope(s,f['reply'],e.value)
    assert allowed['drop_indices']==[15]
    fixed=correction.apply(f['reply'],json.dumps(dict(proposal_hash=allowed['proposal_hash'],patches=[],drop_indices=[15])),allowed)
    out,p=apply_proposal(s,fixed,editing=True)
    assert len(p['changes'])==15
    assert_vera(s,out)
    assert s==original and validate_candidate(s,out,editing=True)==out
    # Model-free normalization is the only source of new server defaults.
    goal=p['changes'][3]['value']['goals'][0]
    assert all(k not in goal for k in ('revision','review_required','reviewed_signature','source_sequence','source_event_id'))
    no_metadata,_=apply_proposal(s,json.dumps(p),editing=True)
    assert no_metadata==out


def test_collect_scope_and_delete_property_not_null():
    s=recorded()['base']['state'];p=json.loads(reply_for(s))
    goal=p['changes'][3]['value']['goals'][0]
    goal.update(revision=9,review_required=['forged'],reviewed_signature='forged',source_event_id='forged')
    raw=json.dumps(p)
    with pytest.raises(ProposalError) as e:apply_proposal(s,raw,editing=True)
    allowed=correction.scope(s,raw,e.value)
    assert allowed['drop_indices']==[15]
    assert set(allowed['remove_paths'])=={f'/changes/3/value/goals/0/{k}' for k in ('revision','review_required','reviewed_signature','source_event_id')}
    null_patch=dict(proposal_hash=allowed['proposal_hash'],patches=[dict(path=allowed['remove_paths'][0],value=None)],drop_indices=[])
    with pytest.raises(ValueError):correction.apply(raw,json.dumps(null_patch),allowed)
    response=dict(proposal_hash=allowed['proposal_hash'],patches=[],remove_paths=allowed['remove_paths'],drop_indices=[15])
    fixed=correction.apply(raw,json.dumps(response),allowed)
    assert all(k not in json.loads(fixed)['changes'][3]['value']['goals'][0] for k in ('revision','review_required','reviewed_signature','source_event_id'))
    assert_vera(s,apply_proposal(s,fixed,editing=True)[0])
    for mutation in (dict(response,proposal_hash='stale'),dict(response,drop_indices=[1]),dict(response,remove_paths=['/changes/3/value/goals/0/text'])):
        with pytest.raises(ValueError):correction.apply(raw,json.dumps(mutation),allowed)


@pytest.mark.parametrize('field,value',[('revision',1),('review_required',['x']),('reviewed_signature','x'),('source_sequence',2),('source_event_id','x')])
def test_existing_motivation_authority_is_immutable(field,value):
    s,_=apply_proposal(recorded()['base']['state'],reply_for(recorded()['base']['state'],clean=True),editing=True)
    goal=deepcopy(s['world']['characters']['vera']['goals'][0]);goal[field]=value
    p=dict(candidate_hash=candidate_hash(s),rationale='Изменить цель',changes=[dict(op='replace',path='/world/characters/vera/goals',value=[goal],reason='правка')])
    with pytest.raises(ProposalError):apply_proposal(s,json.dumps(p),editing=True)
    p['changes'][0].update(path='/world/characters/vera/goals/0/'+field,value=value)
    with pytest.raises(ValueError):apply_proposal(s,json.dumps(p),editing=True)


def test_content_edits_inherit_existing_metadata_and_new_goal_gets_defaults():
    s=recorded()['base']['state'];s,_=apply_proposal(s,reply_for(s,clean=True),editing=True)
    goal=s['world']['characters']['vera']['goals'][0]
    goal.update(revision=7,source_sequence=4,review_required=['location'],reviewed_signature='server',source_event_id=None)
    p=dict(candidate_hash=candidate_hash(s),rationale='Уточнить планы',changes=[dict(op='replace',path='/world/characters/vera/goals',value=[dict(id=goal['id'],text='Закончить диплом.'),dict(id='new_goal',text='Найти практику.')],reason='правка')])
    out,_=apply_proposal(s,json.dumps(p),editing=True)
    changed=out['world']['characters']['vera']['goals']
    for k in ('revision','source_sequence','review_required','reviewed_signature','source_event_id'):assert changed[0][k]==goal[k]
    assert changed[0]['text']=='Закончить диплом.' and changed[1]['revision']==0
    # Empty lists remain empty; creating an NPC never fabricates motivations.
    b=recorded()['base']['state'];p=json.loads(reply_for(b,clean=True));p['changes'][3]['value'].update(goals=[],intentions=[],short_goal='')
    out,_=apply_proposal(b,json.dumps(p),editing=True)
    assert out['world']['characters']['vera']['goals']==[] and out['world']['characters']['vera']['intentions']==[]


def import_world(client):
    wid=client.post('/api/workspaces',json={'name':'Сестра Ильи'}).json()['id'];url=f'/api/workspaces/{wid}/draft'
    r=client.post(url+'/import',json={'revision':0,'format':'json','text':json.dumps(recorded()['base']['state'])})
    assert r.status_code==200,r.text
    return url,client.get(url+'?author=true').json()


def replay_stream(calls, *, fail=False, semantic_forge=False, semantic_refine=False):
    def stream(**kw):
        system=kw['messages'][0]['content'];data=json.loads(kw['messages'][1]['content'])
        kw['on_usage']({'prompt_tokens':100,'completion_tokens':40});kw['on_finish']('stop')
        if system.startswith(draft_editor.MARKER):
            calls.append('proposal');assert 'Создай сестру Ильи' in data['author_context']
            yield reply_for(data['candidate'])
        elif system.startswith('Адресная коррекция'):
            calls.append('correction')
            yield json.dumps(dict(proposal_hash=data['proposal_hash'],patches=[],drop_indices=[0] if fail else [15]))
        elif system.startswith(draft_completeness.MARKER):
            calls.append('review')
            yield json.dumps({'issues':[dict(path='/world/characters/vera/goals',message='Уточнить учебную цель',patch_paths=['/world/characters/vera/goals'])] if semantic_forge or semantic_refine and calls.count('review')==1 else []})
        else:
            calls.append('semantic_repair')
            yield json.dumps({'patches':[dict(path='/world/characters/vera/goals',value=[dict(id='goal_vera_study',text='Диплом.',**({'revision':999} if semantic_forge else {}))])]})
    return stream


@pytest.mark.parametrize('after_start',[False,True])
def test_full_npc_pipeline_preview_accept_startgame_rollback(api,after_start):
    client,app=api;url,before=import_world(client);old=None
    if after_start:
        r=client.post(url+'/confirm',json={'revision':before['revision'],'version_id':before['version_id'],'accept_warnings':True});assert r.status_code==200,r.text
        sid=r.json()['save'];old=deepcopy(app.state.repository.get_snapshot(sid));before=client.get(url+'?author=true').json()
    calls=[]
    with patch('backend.services.preparation.chat_stream',side_effect=replay_stream(calls)):
        r=request(client,url,before,text='Создай сестру Ильи');assert r.status_code==200,r.text
        job=wait_job(client,r.json()['id']);assert job['status']=='saved',job.get('error')
    assert calls==['proposal','correction','review']
    current=client.get(url+'?author=true').json();assert current['state']==before['state'] and current['version_id']==before['version_id']
    edit=client.get(url+'/edits?author=true').json()['edits'][0]
    assert edit['status']=='preview' and len(edit['proposal']['changes'])==15 and edit['review']['issues']==[]
    assert decide(client,url,current,edit).status_code==200
    accepted=client.get(url+'?author=true').json();assert accepted['version_id']!=before['version_id']
    assert_vera(before['state'],accepted['state'])
    assert decide(client,url,current,edit).status_code==200
    assert client.get(url+'?author=true').json()['version_id']==accepted['version_id']
    started=client.post(url+'/confirm',json={'revision':accepted['revision'],'version_id':accepted['version_id'],'accept_warnings':True});assert started.status_code==200,started.text
    runtime=app.state.repository.get_snapshot(started.json()['save'])['world_state']
    assert runtime['objective_relations']['obj_rel_ilya_vera_sibling']['kind']=='sibling'
    assert runtime['characters']['vera']['location_id']=='loc_sokolovy_tver'
    assert runtime['knowledge']['vera:fact_ilya_sister']['status']=='known'
    assert 'vera' not in runtime['camera']['present_character_ids']
    if old is not None:assert app.state.repository.get_snapshot(sid)==old
    current=client.get(url+'?author=true').json()
    restored=client.patch(url,json={'revision':current['revision'],'operation':'restore','source_id':before['version_id']});assert restored.status_code==200
    assert restored.json()['state']==before['state']


@pytest.mark.parametrize('outcome',['reject','stale','bad_correction','semantic_forge'])
def test_npc_failure_and_rejection_are_atomic(api,outcome):
    client,app=api;url,before=import_world(client);calls=[]
    with patch('backend.services.preparation.chat_stream',side_effect=replay_stream(calls,fail=outcome=='bad_correction',semantic_forge=outcome=='semantic_forge')):
        job=wait_job(client,request(client,url,before,text='Создай сестру Ильи').json()['id'])
    current=client.get(url+'?author=true').json();assert current['state']==before['state']
    edit=client.get(url+'/edits?author=true').json()['edits'][0]
    assert edit['instruction']=='Создай сестру Ильи'
    if outcome in ('bad_correction','semantic_forge'):
        assert job['status']=='error' and job['error']
        assert decide(client,url,current,edit).status_code==409
    elif outcome=='reject':assert decide(client,url,current,edit,'reject').status_code==200
    else:
        changed=client.patch(url,json={'revision':current['revision'],'operation':'patch','kind':'campaign','field':'title','value':'Ручная версия'}).json()
        assert decide(client,url,changed,edit).status_code==409
        assert client.get(url+'?author=true').json()['state']==changed['state']
    assert not any(c['id']=='vera' for c in client.get(url+'?author=true').json()['state']['characters'])


def test_semantic_goal_repair_preserves_server_defaults(api):
    client,app=api;url,before=import_world(client);calls=[]
    with patch('backend.services.preparation.chat_stream',side_effect=replay_stream(calls,semantic_refine=True)):
        job=wait_job(client,request(client,url,before,text='Создай сестру Ильи').json()['id'])
    assert job['status']=='saved',job.get('error')
    assert calls==['proposal','correction','review','semantic_repair','review']
    current=client.get(url+'?author=true').json();edit=client.get(url+'/edits?author=true').json()['edits'][0]
    assert decide(client,url,current,edit).status_code==200
    goal=client.get(url+'?author=true').json()['state']['world']['characters']['vera']['goals'][0]
    assert goal['text']=='Диплом.' and goal['revision']==0 and goal['review_required']==[]


def test_prompt_keeps_canon_but_excludes_motivation_authority_from_schema():
    f=recorded();messages=draft_editor.messages(f['base'],'Создай сестру Ильи')
    payload=json.loads(messages[1]['content'])
    assert payload['candidate']==f['base']['state']
    from backend.services.draft_initial import prompt_schema
    world=prompt_schema()['properties']['world']['properties']
    goals=world['characters']['additionalProperties']['properties']['goals']
    assert all('"'+key+'"' not in json.dumps(goals) for key in ('revision','review_required','reviewed_signature','source_sequence','source_event_id'))
    assert 'source_event_id' in world['knowledge']['additionalProperties']['properties']
