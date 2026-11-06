"""Draft portraits: canonical isolation, portable originals and Runtime handoff."""
import json
from copy import deepcopy
import pytest
from test_api import api
from test_draft_world import fixture
from test_portraits import image
from backend.runtime_v3.portraits import projection


def create(client,state=None):
    w=client.post('/api/workspaces',json={'name':'Мастерская портретов'}).json()
    url=f"/api/workspaces/{w['id']}/draft"
    r=client.post(url+'/import',json={'revision':w['revision'],'text':json.dumps(state or fixture()),'format':'json'})
    assert r.status_code==200,r.text
    return url,client.get(url+'?author=true').json()


def test_projection_does_not_rewrite_canon_and_descriptor_survives_start(api):
    client,app=api;url,d=create(client);cid=d['state']['characters'][0]['id']
    before=deepcopy(d['state']);descriptor=d['portraits'][cid]['procedural_portrait']
    assert descriptor and descriptor==client.get(url+'?author=true').json()['portraits'][cid]['procedural_portrait']
    assert client.get(url+f"/export?version_id={d['version_id']}&format=json").json()==before
    path=url+f'/characters/{cid}/portraits'
    descriptor.update(form='human',hair=7,palette=3)
    reply=client.put(path+'/procedural',json={'revision':d['revision'],'descriptor':descriptor,'mode':'procedural'})
    assert reply.status_code==200,reply.text
    d=client.get(url+'?author=true').json()
    assert d['state']['world']['characters'][cid]['procedural_portrait']==descriptor
    assert d['state']['world']['knowledge']==before['world']['knowledge']
    assert d['state']['characters']==before['characters']
    assert client.put(path+'/procedural',json={'revision':d['revision']-1,'descriptor':descriptor}).status_code==409
    started=client.post(url+'/confirm',json={'revision':d['revision'],'version_id':d['version_id'],'accept_warnings':True})
    assert started.status_code==200,started.text
    state=app.state.repository.get_snapshot(started.json()['save'])['world_state']
    assert state['characters'][cid]['procedural_portrait']==descriptor
    assert projection(state,cid)['procedural_portrait']==descriptor
    old=deepcopy(app.state.repository.get_snapshot(started.json()['save']))
    updated=dict(descriptor,hair=2)
    assert client.put(path+'/procedural',json={'revision':d['revision'],'descriptor':updated}).status_code==200
    assert app.state.repository.get_snapshot(started.json()['save'])==old
    assert client.get(url+'?author=true').json()['state']['world']['characters'][cid]['procedural_portrait']==updated


@pytest.mark.parametrize('format',['json','md','txt'])
def test_portable_upload_crop_restore_and_scoped_handoff(api,format):
    client,app=api;url,d=create(client);cid=d['state']['characters'][0]['id'];initial=d
    path=url+f'/characters/{cid}/portraits'
    upload=client.post(path,params={'revision':d['revision']},content=image(),headers={'content-type':'image/png'})
    assert upload.status_code==200,upload.text
    p=upload.json()['portrait'];aid=p['asset_id'];asset=path+'/assets/'+aid
    assert client.get(asset+'?author=true').status_code==200
    assert client.patch(path+'/'+p['id'],json={'revision':upload.json()['revision'],'crop':{'x':.2,'y':.7,'zoom':2}}).status_code==200
    d=client.get(url+'?author=true').json()
    out=client.get(url+f"/export?version_id={d['version_id']}&format={format}");assert out.status_code==200,out.text
    second=client.post('/api/workspaces',json={'name':'Перенос'}).json();url2=f"/api/workspaces/{second['id']}/draft"
    forged=client.post(url2+'/import',json={'revision':0,'format':'json','text':json.dumps(d['state'])})
    assert forged.status_code==409
    imported=client.post(url2+'/import',json={'revision':0,'format':'json' if format=='json' else 'text','text':out.text})
    assert imported.status_code==200,imported.text
    clone=client.get(url2+'?author=true').json();other=clone['portraits'][cid]['portrait']
    assert other['asset_id']!=aid and other['crop']==p['crop']|{'x':.2,'y':.7,'zoom':2}
    assert client.get(url2+f'/characters/{cid}/portraits/assets/'+aid+'?author=true').status_code==404
    started=client.post(url2+'/confirm',json={'revision':clone['revision'],'version_id':clone['version_id'],'accept_warnings':True})
    assert started.status_code==200,started.text
    game=f"/api/saves/{started.json()['save']}/characters/{cid}/portraits"
    assert client.get(game+'/assets/'+other['asset_id']).content==client.get(asset+'?author=true').content
    assert client.get(game+'/assets/'+aid).status_code==404
    # A branch uses the same world-scoped original with its own snapshot/crop.
    from backend.repositories import portraits
    repo=app.state.repository;sid=started.json()['save'];snapshot=repo.get_snapshot(sid)
    branch=repo.create_save(repo.get_save(sid)['world_id'],'Ответвление мастерской')
    with repo.connect() as db:
        db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(snapshot),branch))
    portraits.edit(repo,branch,cid,0,portrait_id=other['id'],changes={'crop':dict(x=.5,y=.5,zoom=3)})
    assert portraits.asset(repo,branch,cid,other['asset_id'])==portraits.asset(repo,sid,cid,other['asset_id'])
    assert portraits.listing(repo,sid,cid)['portrait']['crop']['zoom']==2
    assert repo.get_snapshot(branch)['world_state']['characters'][cid]['procedural_portrait']==snapshot['world_state']['characters'][cid]['procedural_portrait']
    # Roll back to before upload, then to the exact immutable uploaded version.
    for version,visible in [(initial['version_id'],False),(d['version_id'],True)]:
        current=client.get(url+'?author=true').json()
        restored=client.patch(url,json={'revision':current['revision'],'operation':'restore','source_id':version})
        assert restored.status_code==200,restored.text
        assert (client.get(asset+'?author=true').status_code==200)==visible


def test_invalid_descriptor_and_atomic_import(api):
    client,_=api;url,d=create(client);cid=d['state']['characters'][0]['id'];desc=d['portraits'][cid]['procedural_portrait']
    for value in [dict(desc,seed='<svg>'),dict(desc,version=2),dict(desc,hair=999)]:
        assert client.put(url+f'/characters/{cid}/portraits/procedural',json={'revision':d['revision'],'descriptor':value}).status_code==422
    assert client.get(url+'?author=true').json()['version_id']==d['version_id']


def test_visual_preference_preserves_original_and_legacy_period_rules(api):
    client,app=api;url,d=create(client);cid=d['state']['characters'][0]['id']
    path=url+f'/characters/{cid}/portraits';descriptor=d['portraits'][cid]['procedural_portrait']
    uploaded=client.post(path,params={'revision':d['revision']},content=image(),headers={'content-type':'image/png'}).json()
    original=uploaded['portrait'];image_url=path+'/assets/'+original['asset_id']+'?author=true'
    for mode in ('procedural','auto'):
        revision=client.get(url+'?author=true').json()['revision']
        result=client.put(path+'/procedural',json={'revision':revision,'descriptor':descriptor,'mode':mode})
        assert result.status_code==200,result.text
        assert len(result.json()['portraits'])==1
        assert (result.json()['portrait'] is None)==(mode=='procedural')
        assert client.get(image_url).status_code==200
    d=client.get(url+'?author=true').json()
    started=client.post(url+'/confirm',json={'revision':d['revision'],'version_id':d['version_id'],'accept_warnings':True}).json()
    runtime=app.state.repository.get_snapshot(started['save'])['world_state']
    legacy=deepcopy(runtime);legacy['characters'][cid].pop('procedural_portrait')
    assert projection(legacy,cid)['procedural_portrait'] is None
    assert projection(legacy,cid)['portrait']['asset_id']==original['asset_id']
    # A descriptor tied to another life period is never reused as the current face.
    runtime['characters'][cid]['procedural_portrait']['stage']='infant' if descriptor['stage']!='infant' else 'adult'
    assert projection(runtime,cid)['procedural_portrait'] is None


def test_primary_art_direction_becomes_one_portable_descriptor(api):
    from backend.services.draft_initial import inspect_candidate, prompt_schema
    from backend.services.draft_portraits import default_descriptor
    from backend.runtime_v3.context import build_context
    client,app=api
    raw=fixture();card=raw['characters'][0];cid=card['id']
    actor=raw['world']['characters'][cid];actor.update(birth_date=None,developmental_stage='adult')
    description='Короткая тёмная стрижка, широкое лицо, серые глаза и тёмная рубашка.'
    card['fields']['Внешность']=description
    card['portrait_traits']=dict(face='broad',hair='short',hair_color='black',eyes='grey',clothing='shirt',clothing_color='dark')
    contract=prompt_schema(initial_portraits=True)['properties']['characters']['items']
    assert 'portrait_traits' not in contract['required'] and not contract['properties']['portrait_traits']['additionalProperties']
    candidate,report=inspect_candidate(raw)
    assert not report['errors'], report
    assert 'portrait_traits' not in candidate['characters'][0] and candidate['characters'][0]['fields']['Внешность']==description
    desc=candidate['world']['characters'][cid]['procedural_portrait']
    assert desc==dict(default_descriptor(cid,'adult',age_style='young_adult'),face=3,hair=0,hair_color=0,eyes=2,clothing=2,clothing_color=0)
    url,d=create(client,candidate)
    assert d['portraits'][cid]['procedural_portrait']==desc
    # New hints or literary edits never replace a portrait that has already been saved.
    again=deepcopy(candidate);again['characters'][0]['portrait_traits']={'hair_color':'blond'}
    assert inspect_candidate(again)[0]['world']['characters'][cid]['procedural_portrait']==desc
    started=client.post(url+'/confirm',json={'revision':d['revision'],'version_id':d['version_id'],'accept_warnings':True}).json()
    snapshot=app.state.repository.get_snapshot(started['save'])
    assert projection(snapshot['world_state'],cid)['procedural_portrait']==desc
    messages=build_context(snapshot, [], 'Оглядываюсь.', 'turn', 32768, 4096)
    assert desc['seed'] not in json.dumps(messages)


def test_portrait_uses_only_exact_public_initial_features():
    from backend.services.draft_portraits import default_descriptor
    base=default_descriptor('maxim','adult')
    def from_feature(**changes):
        item=dict(kind='eye_color',text='Серые',revision=1)
        return default_descriptor('maxim','adult',{'appearance':{'items':{'iris':{**item,**changes}},
            'legacy_text':'Он блондин в тёмной рубашке.'}})
    assert from_feature()=={**base,'eyes':2}
    assert from_feature(fact_id='hidden_fact')==base
    assert from_feature(source_event_id='a_private_view')==base
    assert from_feature(revision=2)==base
    assert from_feature(text='Кажутся серыми только при плохом освещении.')==base
    assert default_descriptor('maxim','child',hints={'form':'human','eyes':'grey'})['form']=='human'
    assert default_descriptor('maxim','adult',hints={'form':'neutral','eyes':'grey'})['form']=='neutral'
    assert default_descriptor('maxim','adult',hints={'hair_color':'<script>', 'clothing':['shirt']})==base
    assert 'hair_color' not in base and 'clothing_color' not in base


def test_single_primary_generation_accepts_visual_choices_not_model_owned_seeds_or_assets(api):
    from draft_provider_fixture import accept_semantics_unchecked
    from test_api import REMOTE,wait_job
    from test_initial_draft_v4 import rich, SHORT
    from unittest.mock import patch
    client,_=api;raw=rich();card=raw['characters'][0];cid=card['id']
    card['fields']['Возраст']='30 лет'
    card['portrait_traits']=dict(facial_hair='short_beard',hair='short',hair_color='black',eyes='grey',clothing='shirt',clothing_color='dark')
    raw['world']['characters'][cid].update(biological_sex='male',birth_date=None,developmental_stage='adult',
        procedural_portrait={'seed':'MODEL-CANNOT-ISSUE-AN-ID'},portraits=[{'asset_id':'forged'}],portrait_mode='procedural')
    calls=[]
    @accept_semantics_unchecked
    def stream(**kwargs):
        calls.append(kwargs['messages'][0]['content']);yield json.dumps(raw,ensure_ascii=False)
    w=client.post('/api/workspaces',json={'name':'Портреты из первичного ответа'}).json()
    path=f"/api/workspaces/{w['id']}/draft"
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        result=client.post(path+'/generate',json=dict(text=SHORT,revision=0,config=dict(REMOTE,context_length=131072),api_key='test'))
        assert result.status_code==200,result.text
        job=wait_job(client,result.json()['id']);assert job['status']=='saved',job.get('error')
    assert len(calls)==1 and 'portrait_traits' in calls[0]
    draft=client.get(path+'?author=true').json()
    desc=draft['portraits'][cid]['procedural_portrait']
    assert desc['form']=='human' and desc['eyes']==2 and desc['clothing']==2 and desc['hair_color']==desc['clothing_color']==0
    assert (desc['version'],desc['body_frame'],desc['facial_hair'])==(2,'male','short_beard')
    assert 'MODEL-CANNOT-ISSUE-AN-ID' not in desc['seed']
    assert not draft['state']['world']['characters'][cid].get('portraits')
    assert draft['state']['world']['characters'][cid].get('portrait_mode','auto')=='auto'


def test_spoiler_gated_appearance_blocks_the_image_and_direct_asset_until_known(api):
    from secret183_fixture import candidate
    client,_=api;state=candidate()
    state['card_field_facts']={'sonya':{'Внешность':['fact_sonya_love']}}
    url,d=create(client,state);path=url+'/characters/sonya/portraits'
    uploaded=client.post(path,params={'revision':d['revision']},content=image(),headers={'content-type':'image/png'})
    assert uploaded.status_code==200,uploaded.text
    aid=uploaded.json()['portrait']['asset_id'];original=path+'/assets/'+aid
    current=client.get(url+'?author=true').json()
    assert current['portraits']['sonya']['portrait']['asset_id']==aid
    assert client.get(original+'?author=true').status_code==200
    hidden={'portrait':None,'procedural_portrait':None,'silhouette':'neutral'}
    assert client.get(url).json()['portraits']['sonya']==hidden
    assert all(client.get(path).json()[k]==v for k,v in hidden.items())
    assert client.get(original).status_code==404
    assert client.get(url).json()['portraits']['maxim']['procedural_portrait']
    change=client.patch(url,json={'revision':current['revision'],'operation':'patch','kind':'knowledge',
        'entity_id':'ilya:fact_sonya_love','field':'status','value':'known','warnings_ack':True})
    assert change.status_code==200,change.text
    assert client.get(url).json()['portraits']['sonya']['portrait']['asset_id']==aid
    assert client.get(path).json()['portrait']['asset_id']==aid
    assert client.get(original).status_code==200


@pytest.mark.parametrize('visual',['infant','child','adolescent','young_adult','mature_adult','elderly'])
def test_manual_age_persists_without_mutating_canon_and_auto_resolves_on_server(api,visual):
    client,app=api;raw=fixture();cid=raw['characters'][0]['id']
    raw['world']['characters'][cid].update(birth_date=None,developmental_stage='adult')
    url,d=create(client,raw)
    path=url+f'/characters/{cid}/portraits'
    before=deepcopy(d['state']);descriptor=d['portraits'][cid]['procedural_portrait']
    descriptor=dict(descriptor,visual_age=visual,visual_age_mode='manual',stage='infant')
    saved=client.put(path+'/procedural',json={'revision':d['revision'],'descriptor':descriptor,'mode':'procedural'})
    assert saved.status_code==200,saved.text
    again=client.get(path+'?author=true').json()
    assert again['descriptor']==descriptor and again['procedural_portrait']==descriptor
    d=client.get(url+'?author=true').json();after=deepcopy(d['state'])
    for key in ('procedural_portrait','portrait_mode'):
        if key in before['world']['characters'][cid]: after['world']['characters'][cid][key]=before['world']['characters'][cid][key]
        else: after['world']['characters'][cid].pop(key,None)
    assert after==before
    # A subsequent draft normalization / initial traits pass must not replace it.
    from backend.services.draft_portraits import initialize,consume_authored_traits
    copy=deepcopy(d['state']);copy['characters'][0]['portrait_traits']={'hair':'long'}
    consume_authored_traits(copy);initialize(copy)
    assert copy['world']['characters'][cid]['procedural_portrait']==descriptor
    started=client.post(url+'/confirm',json={'revision':d['revision'],'version_id':d['version_id'],'accept_warnings':True})
    assert started.status_code==200,started.text
    runtime=app.state.repository.get_snapshot(started.json()['save'])['world_state']
    assert projection(runtime,cid)['procedural_portrait']==descriptor
    # Client-supplied artistic age and stage cannot substitute for Runtime in auto mode.
    auto=dict(descriptor,visual_age_mode='auto',visual_age='elderly',stage='unknown')
    reset=client.put(path+'/procedural',json={'revision':d['revision'],'descriptor':auto,'mode':'procedural'})
    assert reset.status_code==200,reset.text
    ref=reset.json()['age_reference'];actual=reset.json()['descriptor']
    assert actual['visual_age']==ref['visual_age'] and actual['stage']==ref['stage']
    assert actual['visual_age_mode']=='auto'
    assert app.state.repository.get_snapshot(started.json()['save'])['world_state']==runtime


def test_v1_upgrade_is_local_and_v2_survives_portable_handoff(api):
    from backend.services.draft_portraits import default_descriptor
    client,app=api
    state=fixture()
    cid,other=[c['id'] for c in state['characters'][:2]]
    actor=state['world']['characters'][cid]
    actor.update(biological_sex='male',developmental_stage='adult',birth_date=None)
    legacy=default_descriptor(cid,'adult',version=1)
    actor['procedural_portrait']=legacy
    url,d=create(client,state)
    path=url+f'/characters/{cid}/portraits'
    assert d['portraits'][cid]['procedural_portrait']==legacy
    assert d['portraits'][other]['procedural_portrait']['version']==1  # historical, unmaterialized
    ref=client.get(path+'?author=true').json()['anatomy_reference']
    assert ref=={'body_frame':'male','facial_hair_allowed':True}
    assert 'anatomy_reference' not in client.get(path).json()
    art=dict(legacy,version=2,body_frame='female',facial_hair='clean_shaven')
    assert client.put(path+'/procedural',json={'revision':d['revision'],'descriptor':art}).status_code==200
    d=client.get(url+'?author=true').json()
    assert d['portraits'][other]['procedural_portrait']['version']==1
    exported=client.get(url+f"/export?version_id={d['version_id']}&format=json").json()
    url,d=create(client,exported)
    assert d['portraits'][cid]['procedural_portrait']==art
    started=client.post(url+'/confirm',json={'revision':d['revision'],'version_id':d['version_id'],'accept_warnings':True})
    assert started.status_code==200,started.text
    runtime=app.state.repository.get_snapshot(started.json()['save'])['world_state']
    assert projection(runtime,cid)['procedural_portrait']==art
    assert runtime['characters'][cid]['biological_sex']=='male'
    assert runtime['characters'][other]['procedural_portrait']['version']==1


def test_ineligible_beard_cannot_be_saved_by_forging_artistic_age_or_frame(api):
    client,_=api
    state=fixture();cid=state['characters'][0]['id']
    state['world']['characters'][cid].update(biological_sex='male',developmental_stage='child',birth_date=None)
    url,d=create(client,state);path=url+f'/characters/{cid}/portraits'
    art=dict(d['portraits'][cid]['procedural_portrait'],version=2,stage='adult',body_frame='male',
             form='human',visual_age='elderly',visual_age_mode='manual',facial_hair='full_beard')
    assert client.put(path+'/procedural',json={'revision':d['revision'],'descriptor':art}).status_code in (409,422)
    assert client.get(path+'?author=true').json()['descriptor']['version']==1


def test_gated_portrait_stays_private_after_handoff(api):
    from secret183_fixture import candidate
    client,app=api;raw=candidate();cid='sonya'
    raw['card_field_facts']={cid:{'Внешность':['fact_sonya_love']}}
    url,d=create(client,raw)
    path=url+f'/characters/{cid}/portraits'
    art=dict(d['portraits'][cid]['procedural_portrait'],version=2,body_frame='female',facial_hair='clean_shaven')
    saved=client.put(path+'/procedural',json={'revision':d['revision'],'descriptor':art})
    assert saved.status_code==200,saved.text
    assert client.get(path).json()['procedural_portrait'] is None
    d=client.get(url+'?author=true').json()
    started=client.post(url+'/confirm',json={'revision':d['revision'],'version_id':d['version_id'],'accept_warnings':True})
    assert started.status_code==200,started.text
    sid=started.json()['save'];runtime=app.state.repository.get_snapshot(sid)['world_state']
    assert projection(runtime,cid).get('procedural_portrait') is None
    assert client.get(f'/api/saves/{sid}/characters/{cid}/portraits').status_code>=400
    fid='fact_sonya_love';runtime['knowledge']['ilya:'+fid]={'status':'known'}
    assert projection(runtime,cid)['procedural_portrait']==art
