from copy import deepcopy
from io import BytesIO
import json
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from backend.api.app import create_app
from backend.repositories import portraits
from backend.runtime_v3.portraits import select_portrait, projection
from backend.services.portrait_assets import decode_image,MAX_BYTES
from devtools.narrative_test_world import load_fixture,ACTOR_ID


def image(fmt='PNG',size=(320,480),**kwargs):
    out=BytesIO();Image.new('RGB',size,'#7755aa').save(out,format=fmt,**kwargs);return out.getvalue()


@pytest.fixture
def setup(tmp_path):
    app=create_app(tmp_path/'game.sqlite',recover=False);repo=app.state.repository;sid=load_fixture(repo,'family')['save']
    return repo,sid,TestClient(app)


@pytest.mark.parametrize('fmt,mime',[('PNG','image/png'),('JPEG','image/jpeg'),('WEBP','image/webp')])
def test_formats_content_full_pixels_and_metadata(fmt,mime):
    content,w,h=decode_image(image(fmt),mime);assert (w,h)==(320,480)
    full=Image.open(BytesIO(content));assert full.size==(320,480) and not full.getexif()


@pytest.mark.parametrize('size',[(255,256),(256,255),(4097,256),(256,4097)])
def test_dimension_rejection(size):
    with pytest.raises(ValueError):decode_image(image(size=size),'image/png')


@pytest.mark.parametrize('content,mime',[(b'<svg/>','image/png'),(b'bad','image/webp'),(b'bad','text/html'),(b'x'*(MAX_BYTES+1),'image/png')])
def test_bad_files(content,mime):
    with pytest.raises(ValueError):decode_image(content,mime)


def test_mime_mismatch_truncation_orientation_and_animation():
    with pytest.raises(ValueError):decode_image(image('JPEG'),'image/png')
    with pytest.raises(ValueError):decode_image(image()[:100],'image/png')
    exif=Image.Exif();exif[274]=6;exif[270]='private'
    data,w,h=decode_image(image('JPEG',exif=exif),'image/jpeg')
    assert (w,h)==(480,320) and not Image.open(BytesIO(data)).getexif()
    out=BytesIO();Image.new('RGB',(256,256),'red').save(out,format='WEBP',save_all=True,append_images=[Image.new('RGB',(256,256),'blue')])
    with pytest.raises(ValueError):decode_image(out.getvalue(),'image/webp')


def test_upload_crop_replace_delete_atomic_and_scoped(setup):
    repo,sid,client=setup;path=f'/api/saves/{sid}/characters/{ACTOR_ID}/portraits'
    before=repo.get_snapshot(sid);rev=repo.get_save(sid)['revision']
    res=client.post(path,params={'revision':rev},content=image(),headers={'content-type':'image/png'})
    assert res.status_code==200,res.text
    p=res.json()['portrait'];aid=p['asset_id'];url=path+'/assets/'+aid
    assert client.get(url).status_code==200
    assert client.get(url).headers['cache-control']=='private, no-store'
    r=client.patch(path+'/'+p['id'],json={'revision':rev+1,'crop':{'x':.2,'y':.7,'zoom':2.0},'label':'После стрижки'})
    assert r.status_code==200,r.text
    after=repo.get_snapshot(sid)
    assert after['world_state']['characters'][ACTOR_ID]['appearance']==before['world_state']['characters'][ACTOR_ID]['appearance']
    assert after['world_state']['knowledge']==before['world_state']['knowledge']
    assert portraits.listing(repo,sid,ACTOR_ID)['portrait']['crop']==dict(x=.2,y=.7,zoom=2.0)
    assert client.patch(path+'/'+p['id'],json={'revision':rev+1,'crop':{'x':.5,'y':.5,'zoom':1.0}}).status_code==409
    assert client.patch(path+'/'+p['id'],json={'revision':rev+2,'crop':{'x':2,'y':.5,'zoom':1.0}}).status_code==422
    other=repo.create_save(repo.get_save(sid)['world_id'],'Other')
    assert client.get(url.replace(f'/saves/{sid}/',f'/saves/{other}/')).status_code==404
    assert client.get(url.replace(ACTOR_ID,'qa_asya')).status_code==404
    assert client.get(path+'/assets/%2E%2E%2Fetc%2Fpasswd').status_code in (404,405)
    r=client.delete(path+'/'+p['id'],params={'revision':rev+2});assert r.status_code==200
    assert client.get(url).status_code==404
    # Restoring a historic snapshot restores access and exact crop; binary is immutable.
    with repo.connect() as db:db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(after),sid))
    assert client.get(url).status_code==200
    assert client.get(path).json()['portrait']['crop']['zoom']==2


def test_period_selection_child_not_adult_and_no_guess_from_name(setup):
    repo,sid,_=setup;rev=repo.get_save(sid)['revision']
    r=portraits.edit(repo,sid,'qa_asya',rev,image=decode_image(image(),'image/png'))
    snap=repo.get_snapshot(sid);s=snap['world_state'];cid='qa_asya'
    assert select_portrait(s,cid)
    s['characters'][cid]['birth_date']='1990-01-01';s['characters'][cid]['developmental_stage']='adult'
    assert select_portrait(s,cid) is None
    assert projection(s,cid)['silhouette']=='neutral'
    assert r['portraits']


def test_branch_keeps_assets_and_isolates_crops(setup):
    repo,sid,_=setup;rev=repo.get_save(sid)['revision'];p=portraits.edit(repo,sid,ACTOR_ID,rev,image=decode_image(image(),'image/png'))['portrait']
    snapshot=repo.get_snapshot(sid);other=repo.create_save(repo.get_save(sid)['world_id'],'branch')
    with repo.connect() as db:db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(snapshot),other))
    portraits.edit(repo,other,ACTOR_ID,0,portrait_id=p['id'],changes={'crop':dict(x=.8,y=.2,zoom=3.0)})
    assert portraits.asset(repo,other,ACTOR_ID,p['asset_id'])==portraits.asset(repo,sid,ACTOR_ID,p['asset_id'])
    assert portraits.listing(repo,sid,ACTOR_ID)['portrait']['crop']['zoom']==1


def test_cross_origin_hidden_newborn_and_missing_assets(setup):
    repo,sid,client=setup;rev=repo.get_save(sid)['revision'];path=f'/api/saves/{sid}/characters/{ACTOR_ID}/portraits'
    assert client.post(path,params={'revision':rev},content=image(),headers={'content-type':'image/png','origin':'https://evil.test'}).status_code==403
    p=portraits.edit(repo,sid,ACTOR_ID,rev,image=decode_image(image(),'image/png'))['portrait']
    with repo.connect() as db:db.execute('DELETE FROM portrait_assets WHERE id=?',(p['asset_id'],))
    assert client.get(path+'/assets/'+p['asset_id']).status_code==404


def test_failed_upload_settings_do_not_leave_orphans(setup):
    repo,sid,client=setup;rev=repo.get_save(sid)['revision'];path=f'/api/saves/{sid}/characters/{ACTOR_ID}/portraits'
    res=client.post(path,params={'revision':rev,'settings':json.dumps({'min_age':50,'max_age':4})},content=image(),headers={'content-type':'image/png'})
    assert res.status_code==409
    with repo.connect() as db: assert db.execute('SELECT COUNT(*) FROM portrait_assets').fetchone()[0]==0


def test_replacement_history_selection_period_and_retry(setup):
    repo,sid,client=setup;cid='qa_vera';rev=repo.get_save(sid)['revision']
    first=portraits.edit(repo,sid,cid,rev,image=decode_image(image(),'image/png'))['portrait']
    second=portraits.edit(repo,sid,cid,rev+1,image=decode_image(image('JPEG'),'image/jpeg'),portrait_id=first['id'],changes={'min_age':30,'max_age':50})
    assert len(second['portraits'])==2 and second['portrait']['id']!=first['id']
    chosen=next(p for p in second['portraits'] if p['id']==second['portrait']['id'])
    assert chosen['min_age']==30 and chosen['max_age']==50
    with pytest.raises(ValueError): portraits.edit(repo,sid,cid,rev+1,image=decode_image(image(),'image/png'))
    with repo.connect() as db: assert db.execute('SELECT COUNT(*) FROM portrait_assets').fetchone()[0]==2
    selected=portraits.edit(repo,sid,cid,rev+2,portrait_id=first['id'],changes={'make_current':True})
    assert selected['portrait']['id']==first['id']
    graph=client.get(f'/api/saves/{sid}/genealogy').json()
    assert next(n for n in graph['nodes'] if n['id']==cid)['portrait']==selected['portrait']
    portraits.edit(repo,sid,cid,rev+3,portrait_id=first['id'],remove=True)
    assert portraits.listing(repo,sid,cid)['portrait']['id']==chosen['id']


def test_hidden_newborn_assets_and_deleted_world_fail_closed(setup):
    repo,_,client=setup;sid=load_fixture(repo,'newborn')['save'];snap=repo.get_snapshot(sid)
    child=next(cid for cid,c in snap['world_state']['characters'].items() if c.get('birth_provenance'))
    p=portraits.edit(repo,sid,child,repo.get_save(sid)['revision'],image=decode_image(image(),'image/png'))['portrait']
    url=f'/api/saves/{sid}/characters/{child}/portraits/assets/'+p['asset_id']
    assert client.get(url).status_code==200
    snap=repo.get_snapshot(sid);s=snap['world_state'];s['knowledge']={}
    with repo.connect() as db: db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(snap),sid))
    assert client.get(url).status_code==404
    with pytest.raises(ValueError):portraits.listing(repo,sid,child)
    sid2=load_fixture(repo,'family')['save'];p2=portraits.edit(repo,sid2,ACTOR_ID,repo.get_save(sid2)['revision'],image=decode_image(image(),'image/png'))['portrait']
    with repo.connect() as db:db.execute('UPDATE worlds SET deleted=1 WHERE id=?',(repo.get_save(sid2)['world_id'],))
    assert client.get(f'/api/saves/{sid2}/characters/{ACTOR_ID}/portraits/assets/'+p2['asset_id']).status_code==404


def test_separate_user_database_does_not_grant_access_from_foreign_reference(setup,tmp_path):
    repo,sid,_=setup;p=portraits.edit(repo,sid,ACTOR_ID,repo.get_save(sid)['revision'],image=decode_image(image(),'image/png'))['portrait']
    other=create_app(tmp_path/'other-user.sqlite',recover=False).state.repository;other_sid=load_fixture(other,'family')['save']
    foreign=repo.get_snapshot(sid);snap=other.get_snapshot(other_sid)
    snap['world_state']['characters'][ACTOR_ID]['portraits']=foreign['world_state']['characters'][ACTOR_ID]['portraits']
    with other.connect() as db:db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(snap),other_sid))
    with pytest.raises(ValueError): portraits.asset(other,other_sid,ACTOR_ID,p['asset_id'])
