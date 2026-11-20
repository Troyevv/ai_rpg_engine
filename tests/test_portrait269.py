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
        assert all(rows[cid]['descriptor']['traits']['clothing']=='pilot' for cid in ids)
        assert rows[ids[1]]['warnings']
    if scope=='workspace':
        draft=client.get(url+'?author=true').json()
        exported=client.get(url+f"/export?version_id={draft['version_id']}&format=json").json()
        _,clone=create(client,exported)
        assert clone['portraits'][ids[0]]['procedural_portrait']==expected



@pytest.mark.parametrize('editing',[True,False])
def test_new_editor_and_creative_actor_share_world_catalog(editing):
    from test_draft_editor_paths import recorded
    from backend.repositories.drafts import candidate_hash
    from backend.services import draft_creative, draft_editor
    from backend.services.draft_changes import apply_proposal
    sample=recorded()
    state=sample['base']['state']
    state['creation_settings']={**state.get('creation_settings',{}),'portrait_style':'semi_realistic'}
    packet=json.loads(sample['reply'])
    packet['candidate_hash']=candidate_hash(state)
    card=packet['changes'][1]['value']
    card['portrait_traits']={'form':'human','face':'diamond','eye_shape':'monolid','build':'full','eyes':'amber','nose_shape':'unknown'}
    warnings=[]
    result,_=apply_proposal(state,json.dumps(packet),editing=editing,warnings=warnings)
    art=result['world']['characters']['olya']['procedural_portrait']
    assert art['art_style']=='semi_realistic'
    assert {k:art['traits'][k] for k in ('face','eye_shape','build','eyes')}==dict(face='diamond',eye_shape='monolid',build='full',eyes='amber')
    assert any(row['category']=='portrait_traits' for row in warnings)
    wire=draft_editor.messages(sample['base'],'Редактирование') if editing else draft_creative.messages(state,'Замысел')
    schema=json.loads(wire[1]['content'])['world_schema']['properties']['characters']['items']['properties']['portrait_traits']
    assert 'monolid' in schema['properties']['eye_shape']['enum']


def test_local_style_keeps_selected_photo_original_and_crop(api):
    from test_portraits import image
    client,_=api
    url,draft=create(client)
    cid=draft['state']['characters'][0]['id']
    path=url+f'/characters/{cid}/portraits'
    uploaded=client.post(path,params={'revision':draft['revision']},content=image(),headers={'content-type':'image/png'}).json()
    photo=uploaded['portrait']
    crop=dict(x=.23,y=.71,zoom=1.8)
    client.patch(path+'/'+photo['id'],json=dict(revision=uploaded['revision'],crop=crop)).raise_for_status()
    before=client.get(path+'?author=true').json()
    base='/api/portrait-proposals/workspace/'+url.split('/')[3]
    preview=client.post(base+'/style',json=dict(revision=before['revision'],ids=[cid],art_style='anime')).json()
    client.post(base+'/'+preview['id']+'/apply',json=dict(revision=before['revision'],ids=[cid])).raise_for_status()
    after=client.get(path+'?author=true').json()
    assert after['descriptor']['art_style']=='anime'
    assert after['portrait_mode']==before['portrait_mode']=='auto'
    assert after['portrait']==before['portrait'] and after['portrait']['crop']==crop
    assert client.get(path+'/assets/'+photo['asset_id']+'?author=true').status_code==200
