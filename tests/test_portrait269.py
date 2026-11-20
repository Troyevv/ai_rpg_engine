import json
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from backend.runtime_v3.models import ProceduralPortraitV4
from backend.runtime_v3.portrait_catalog import ILLUSTRATION
from backend.services.draft_portraits import default_descriptor
from backend.services.portrait_traits import input_schema
from test_api import api, REMOTE
from test_workshop_portraits import create, fixture


def test_open_build_and_stable_semantic_catalog():
    actor={'appearance':{'items':{'build':{'kind':'build','text':'Коренастое'}}}}
    def pick(cid,world):
        return default_descriptor(cid,'adult',actor,{'build':'slim','eye_shape':'monolid'},
            'mature_adult',version=4,world_id=world,profile='futuristic',art_style='anime')
    population=[pick(str(i),'A') for i in range(512)]
    assert population==[pick(str(i),'A') for i in range(512)]
    assert population[0]!=pick('0','B')
    assert {p['traits']['clothing'] for p in population}==set(ILLUSTRATION['wardrobes']['futuristic'])
    assert {p['traits']['hair'] for p in population}==set(ILLUSTRATION['styles']['hair'])
    assert all(p['traits']['build']=='stocky' and p['traits']['eye_shape']=='monolid' for p in population)
    assert all(p['traits']['hair_color'] in ILLUSTRATION['natural_hair'] and p['traits']['detail']=='none' for p in population)
    actor['appearance']['items']['build']['fact_id']='private'
    assert {pick(str(i),'B')['traits']['build'] for i in range(36)}==set(ILLUSTRATION['styles']['build'])
    traits={**population[0]['traits'],'detail':'<svg/>'}
    with pytest.raises(ValidationError):
        ProceduralPortraitV4.model_validate(dict(population[0],traits=traits))
    assert 'art_style' not in input_schema(4)['properties']


@pytest.mark.parametrize('scope',['workspace','save'])
def test_free_switch_selective_apply_and_mixed_commission(api,scope):
    client,app=api
    state=fixture()
    state['creation_settings']={'portrait_style':'anime'}
    ids=[card['id'] for card in state['characters'][:2]]
    for card in state['characters']:
        state['world']['characters'][card['id']].update(developmental_stage='adult')
        card['portrait_traits']={'eye_shape':'monolid','hair':'twists','detail':'mole','clothing':'medic','skin':'ebony'}
    url,d=create(client,state)
    owner=url.split('/')[3]
    if scope=='save':
        r=client.post(url+'/confirm',json=dict(revision=d['revision'],version_id=d['version_id'],accept_warnings=True))
        assert r.status_code==200,r.text
        owner=r.json()['save']
        url=f'/api/saves/{owner}'
    def listing(cid):
        return client.get(url+f'/characters/{cid}/portraits?author=true').json()
    before=[listing(cid)['descriptor'] for cid in ids]
    revision=listing(ids[0])['revision']
    assert all(p['version']==4 and p['art_style']=='anime' and p['traits']['clothing']=='medic' for p in before)
    base=f'/api/portrait-proposals/{scope}/{owner}'
    with patch('llm.chat_stream',side_effect=AssertionError('local conversion dispatched')):
        ticket=client.post(base+'/style',json=dict(revision=revision,ids=ids,art_style='semi_realistic'))
        assert ticket.status_code==200,ticket.text
        expected=dict(before[0],art_style='semi_realistic')
        assert ticket.json()['proposals'][ids[0]]['descriptor']==expected
        assert listing(ids[0])['descriptor']==before[0]
        apply=base+'/'+ticket.json()['id']+'/apply'
        reply=client.post(apply,json=dict(ids=[ids[0]],revision=revision))
        assert reply.status_code==200,reply.text
        assert listing(ids[0])['descriptor']==expected and listing(ids[1])['descriptor']==before[1]
        assert client.post(apply,json=dict(ids=[ids[1]],revision=revision)).status_code==409
    revision=listing(ids[0])['revision']
    def stream(**kw):
        payload=json.loads(kw['messages'][1]['content'])
        assert 'monolid' in payload['trait_schema']['properties']['eye_shape']['enum']
        assert kw['thinking']=='low'
        kw['on_finish']('stop')
        yield json.dumps(dict(version=4,characters={cid:dict(eye_shape='upturned',clothing='pilot',detail='bad') for cid in ids}))
    with patch('llm.chat_stream',side_effect=stream) as wire:
        quote=client.post(base,json=dict(ids=ids,revision=revision,config=dict(REMOTE,thinking='low')))
        assert quote.status_code==200,quote.text
        result=client.post(base+'/'+quote.json()['id']+'/generate',json={'api_key':'test'}).json()
        assert result['status']=='ready' and wire.call_count==1
        rows=result['proposals']
        assert [rows[cid]['descriptor']['art_style'] for cid in ids]==['semi_realistic','anime']
        assert rows[ids[1]]['descriptor']['traits']['clothing']=='pilot'
        assert rows[ids[1]]['warnings']
    if scope=='workspace':
        draft=client.get(url+'?author=true').json()
        exported=client.get(url+f"/export?version_id={draft['version_id']}&format=json").json()
        _,clone=create(client,exported)
        assert clone['portraits'][ids[0]]['procedural_portrait']==expected

