import json
from copy import deepcopy
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


@pytest.mark.parametrize('scope',['save','workspace'])
def test_single_paid_dispatch_partial_preview_and_revision_fence(api,scope):
    client,app=api
    raw=fixture()
    cards=raw['characters'][:2]
    ids=[c['id'] for c in cards]
    for c in cards:
        raw['world']['characters'][c['id']].update(developmental_stage='adult')
        c['fields']['Внешность']='Светлая коса и серые глаза.'
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
        assert kw['thinking']=='low'
        calls.append(payload)
        kw['on_usage'](dict(prompt_tokens=128,completion_tokens=49,prompt_cache_hit_tokens=0))
        kw['on_finish']('stop')
        yield json.dumps(dict(version=3,characters={ids[0]:dict(hair='braid',clothing='hoodie',eyes='<svg>'),ids[1]:{'src':'private.png'}}))
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
        assert art['garment']=='hoodie' and art['hairstyle']=='braid' and result['proposals'][ids[0]]['warnings']
        assert ids[1] in result['errors']
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
