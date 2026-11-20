import json
from unittest.mock import patch

import pytest

from test_api import api, REMOTE
from test_workshop_portraits import create,fixture
from backend.services.draft_portraits import default_descriptor
from backend.runtime_v3.portrait_catalog import CATALOG


def test_world_scoped_catalogue_and_wardrobe():
    def sample(world):
        return [default_descriptor(str(i),'adult',version=3,world_id=world,profile='historical') for i in range(80)]
    first=sample('first')
    assert sample('first')==first and sample('second')!=first
    assert {p['garment'] for p in first}==set(CATALOG['wardrobes']['historical'])
    assert {p['hairstyle'] for p in first}==set(CATALOG['styles']['hair'])
    assert {p['eyes'] for p in first}==set(range(8))
    assert all(p['accessory']==0 for p in first)
    from backend.runtime_v3.models import ProceduralPortraitV3
    assert all(p['face_revision']==2 for p in first)
    historical=dict(first[0])
    historical.pop('face_revision')
    assert 'face_revision' not in ProceduralPortraitV3.model_validate(historical).model_dump()


@pytest.mark.parametrize('scope',['save','workspace'])
def test_single_paid_dispatch_partial_preview_and_revision_fence(api,scope):
    client,app=api
    raw=fixture()
    raw['campaign']['portrait_profile']='historical'
    cards=raw['characters'][:2]
    ids=[c['id'] for c in cards]
    for c in cards:
        raw['world']['characters'][c['id']].update(developmental_stage='adult')
        c['fields']['Внешность']='Светлая коса и серые глаза.'
    actor=raw['world']['characters'][ids[0]]
    actor['appearance']={'items':{
        'public':dict(category='presentation',kind='hairstyle',text='Коса'),
        'private':dict(category='modification',kind='tattoo',text='Скрытый узор',fact_id='meeting')}}
    url,d=create(client,raw)
    owner=url.split('/')[3]
    if scope=='save':
        start=client.post(url+'/confirm',json=dict(revision=d['revision'],version_id=d['version_id'],accept_warnings=True))
        assert start.status_code==200,start.text
        owner=start.json()['save']
        url=f'/api/saves/{owner}'
    paths=[url+f'/characters/{cid}/portraits' for cid in ids]
    before=[client.get(path+'?author=true').json() for path in paths]
    revision=before[0]['revision']
    base=f'/api/portrait-proposals/{scope}/{owner}'
    body=dict(revision=revision,config=dict(REMOTE,thinking='low'),ids=ids)
    calls=[]
    def stream(**kw):
        payload=json.loads(kw['messages'][1]['content'])
        assert set(payload['cards'])==set(ids) and 'Тайная встреча' not in str(payload)
        assert payload['wardrobe']=='historical'
        assert payload['cards'][ids[0]]['features']==[{'kind':'hairstyle','text':'Коса'}]
        assert 'Скрытый узор' not in kw['messages'][1]['content']
        assert kw['thinking']=='low'
        calls.append(payload)
        kw['on_usage'](dict(prompt_tokens=128,completion_tokens=49,prompt_cache_hit_tokens=0))
        kw['on_finish']('stop')
        yield json.dumps(dict(version=3,characters={ids[0]:dict(hair='bald',clothing='smock',eyes='<svg>'),ids[1]:{'src':'private.png'}}))
    with patch('llm.chat_stream',side_effect=stream):
        q=client.post(base,json=body)
        assert q.status_code==200,q.text
        assert not calls and q.json()['requests']==1
        ticket=base+'/'+q.json()['id']
        # A second quote is bound to the same revision; cancellation costs nothing.
        other=base+'/'+client.post(base,json=body).json()['id']
        assert client.post(other+'/cancel').json()['status']=='cancelled'
        assert client.post(other+'/generate',json={'api_key':'test'}).json()['status']=='cancelled'
        result=client.post(ticket+'/generate',json={'api_key':'test'})
        assert result.status_code==200,result.text
        result=result.json()
        assert result['status']=='ready',result
        assert client.post(ticket+'/generate',json={'api_key':'test'}).json()==result
        assert client.get(ticket).json()==result and len(calls)==1
        art=result['proposals'][ids[0]]['descriptor']
        assert art['garment']=='smock' and art['hairstyle']=='braid' and result['proposals'][ids[0]]['warnings']
        assert ids[1] in result['errors']
        assert client.post(ticket+'/apply',json=dict(ids=[ids[0]],revision=revision+1)).status_code==409
        assert before==[client.get(path+'?author=true').json() for path in paths]
        assert client.post(ticket+'/apply',json=dict(ids=[ids[0]],revision=revision)).status_code==200
        assert client.post(ticket+'/apply',json=dict(ids=[ids[0]],revision=revision)).status_code==409
        after=[client.get(path+'?author=true').json() for path in paths]
        assert after[0]['descriptor']==art and after[1]['descriptor']==before[1]['descriptor']
        assert after[0]['revision']==revision+1
    rows=app.state.repository.request_log(job_id=ticket.split('/')[-1])
    assert len(rows)==1 and rows[0]['thinking']=='low'


@pytest.mark.parametrize('outcome',['invalid','timeout'])
def test_uncertain_response_is_never_reissued(api,outcome):
    client,_=api;url,d=create(client);cid=d['state']['characters'][0]['id']
    base='/api/portrait-proposals/workspace/'+url.split('/')[3]
    q=client.post(base,json=dict(ids=[cid],revision=d['revision'],config=REMOTE))
    ticket=base+'/'+q.json()['id']
    with patch('llm.chat_stream',side_effect=TimeoutError if outcome=='timeout' else lambda **kw:iter(['{'])) as wire:
        for _ in range(2):
            response=client.post(ticket+'/generate',json={'api_key':'test'})
            assert response.json()['status']=='interrupted'
        assert wire.call_count==1
    assert client.get(url+'?author=true').json()['revision']==d['revision']


def test_creative_refines_only_current_creation_and_unedited_art():
    from test_initial_draft_v4 import rich
    from backend.services.draft_initial import inspect_candidate
    from backend.repositories.drafts import candidate_hash
    from backend.services.draft_changes import apply_proposal
    raw=rich(); cid=raw['characters'][0]['id']
    raw['portrait_world_id']='creation-1'
    raw['world']['characters'][cid].update(birth_date=None,developmental_stage='adult')
    raw['characters'][0]['portrait_traits']=dict(hair='pixie',eyes='grey_blue')
    base,report=inspect_candidate(raw);assert not report['errors']
    art=base['world']['characters'][cid]['procedural_portrait']
    def creative(state,job):
        packet=dict(candidate_hash=candidate_hash(state),rationale='Образ',changes=[
            dict(op='replace',path=f'/characters/{cid}/fields/Внешность',value='Волосы заплетены в косу.',reason='Уточнение'),
            dict(op='add',path=f'/characters/{cid}/portrait_traits',value=dict(hair='braid'),reason='Причёска')])
        return apply_proposal(state,json.dumps(packet),creation_job=job)[0]['world']['characters'][cid]['procedural_portrait']
    result=creative(base,'creation-1')
    assert result['hairstyle']=='braid' and result['eyes']==art['eyes'] and result['seed']==art['seed']
    assert creative(base,'another-job')==art
    base.setdefault('authoring',{}).setdefault('manual_portraits',{})[cid]=True
    assert creative(base,'creation-1')==art


def test_closed_appearance_blocks_commission_before_dispatch(api):
    from secret183_fixture import candidate
    client,_=api;state=candidate()
    state['card_field_facts']={'sonya':{'Внешность':['fact_sonya_love']}}
    url,d=create(client,state);base='/api/portrait-proposals/workspace/'+url.split('/')[3]
    with patch('llm.chat_stream',side_effect=AssertionError('unexpected dispatch')):
        response=client.post(base,json=dict(revision=d['revision'],config=REMOTE,ids=['sonya']))
    assert response.status_code==409 and 'fact_sonya_love' not in response.text


def test_runtime_rollback_and_alternate_variant_restore_own_illustration(tmp_path):
    from backend.repositories import portraits
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture,ACTOR_ID
    from test_narrative_test_world import ordinary_job,CONFIG
    from runtime_v3_fixture import execute
    repo=Repository(tmp_path/'portraits.sqlite')
    sid=load_fixture(repo,'family')['save']
    art=default_descriptor(ACTOR_ID,'adult',version=3,hints={'hair':'braid','clothing':'hoodie'},world_id='family')
    def edit(value):
        portraits.edit(repo,sid,ACTOR_ID,repo.get_save(sid)['revision'],descriptor=value,mode='procedural')
    def saved():
        return repo.get_snapshot(sid)['world_state']['characters'][ACTOR_ID]['procedural_portrait']
    edit(art);ordinary_job(repo,sid,'start')
    opening=repo.list_turns(sid)[0]
    edited=dict(art,garment='cloak')
    edit(edited);ordinary_job(repo,sid)
    repo=Repository(repo.path)
    assert saved()==edited
    repo.rollback_last(sid,repo.get_save(sid)['revision'])
    assert saved()==edited
    jid=repo.begin_job(sid,'','regenerate',CONFIG)
    camera=json.loads(repo.get_job(jid)['before_json'])['world_state']['camera']
    execute(repo,jid,dict(final_scene=dict(location_id=camera['location_id'],
        present_character_ids=camera['present_character_ids'])),'Разговор продолжается.')
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    assert saved()==art
    edit(dict(art,hairstyle='bun'))
    repo.select_variant(sid,opening['id'],opening['active_variant_id'],repo.get_save(sid)['revision'])
    assert saved()==art


def test_cancel_active_batch_rejects_duplicate_dispatch(api):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    client,_=api;url,d=create(client);cid=d['state']['characters'][0]['id']
    base='/api/portrait-proposals/workspace/'+url.split('/')[3]
    q=client.post(base,json=dict(ids=[cid],revision=d['revision'],config=REMOTE))
    ticket=base+'/'+q.json()['id']; started=Event()
    def slow(**kwargs):
        started.set()
        assert kwargs['cancel_event'].wait(5)
        yield '{}'
    with patch('llm.chat_stream',side_effect=slow) as wire, ThreadPoolExecutor() as executor:
        pending=executor.submit(client.post,ticket+'/generate',json={'api_key':'test'})
        assert started.wait(5)
        assert client.post(ticket+'/generate',json={}).json()['status']=='running'
        assert client.post(ticket+'/cancel').json()['status']=='cancelled'
        assert pending.result(timeout=5).json()['status']=='cancelled'
        assert wire.call_count==1
    assert client.get(url+'?author=true').json()['revision']==d['revision']

def test_large_quote_splits_into_bounded_groups_without_dispatch():
    from backend.services import portrait_proposals,token_budget
    config=token_budget.prepare(REMOTE,'portrait_proposal')
    cards={f'person{i}':dict(description='Короткие волосы',features=[]) for i in range(19)}
    with patch('llm.chat_stream',side_effect=AssertionError('unexpected dispatch')):
        batches=portrait_proposals.plan(cards,'neutral',config)
    assert [len(batch['ids']) for batch in batches]==[8,8,3]
    assert [cid for batch in batches for cid in batch['ids']]==list(cards)
    assert all(0<batch['limit']<=config['max_tokens'] for batch in batches)
