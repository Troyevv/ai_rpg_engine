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
