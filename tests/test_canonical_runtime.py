"""Canonical v3 snapshots, timing and the existing manual relationship API."""
import json
from context_builder import build_context
from test_engine import db,CONFIG,run
from test_api import api,new_save


def test_canonical_v3_turn_persists_its_timing(db):
    storage,_,sid=db
    job=storage.begin_job(sid,'','start',CONFIG)
    calls=run(storage,job)
    assert storage.get_snapshot(sid)['schema_version']==3
    assert len(calls)==2
    turn=storage.list_turns(sid)[0]
    timing=json.loads(turn['timing_json'])
    assert set(['narrative','extraction','validation_apply','total'])<=timing.keys()
    assert timing['memory_compaction']==0
    assert not {'background_simulation','extraction_repair'} & timing.keys()
    assert timing['total']+0.005>=sum(timing[k] for k in ('narrative','extraction','validation_apply'))
    assert storage.get_job(job)['timing_json']==turn['timing_json']
    with storage.connect() as conn:
        assert json.loads(conn.execute('SELECT payload FROM response_variants WHERE id=?',(turn['active_variant_id'],)).fetchone()[0])['timing_json']==turn['timing_json']
        conn.execute('UPDATE turns SET timing_json=NULL WHERE id=?',(turn['id'],))
    assert storage.list_turns(sid)[0]['timing_json'] is None


def test_relationship_api_is_save_scoped_and_follows_controlled_actor(api):
    from test_api import new_save
    client,app=api
    world,save=new_save(client)
    other=client.post(f"/api/worlds/{world['id']}/saves",json={'name':'Независимое прохождение'}).json()
    actor=save['state']['controlled_actor_id'];target=next(c['id'] for c in save['state']['characters'] if c['id']!=actor)
    url=lambda cid:f"/api/saves/{save['id']}/characters/{cid}/relationships"
    dims=client.get('/api/relationships/dimensions').json()
    assert 'trust' in dims
    body={'revision':save['revision'],'target_id':target,'context':'Доверяет на работе','dimensions':{'trust':12}}
    assert client.patch(url(target),json={**body,'target_id':actor}).status_code==409
    created=client.patch(url(actor),json=body)
    assert created.status_code==200,created.text
    updated=created.json();assert updated['state']['world']['relationships'][actor+':'+target]['context']=='Доверяет на работе'
    assert client.get(f"/api/saves/{other['id']}").json()['state']==other['state']
    assert 'Доверяет на работе' in str(build_context(app.state.repository.get_snapshot(save['id']),[],target,'turn',32768,2000))
    body.update(revision=updated['revision'],context='Разочарован поступком',dimensions={'trust':-10})
    changed=client.patch(url(actor),json=body).json()
    assert changed['state']['world']['relationships'][actor+':'+target]['dimensions']['trust']==-10
    app.state.repository.switch_actor(save['id'],target,changed['revision'])
    switched=client.get(f"/api/saves/{save['id']}").json()
    assert client.patch(url(actor),json={**body,'revision':switched['revision']}).status_code==409
    reverse=client.patch(url(target),json={'revision':switched['revision'],'target_id':actor,'context':'Не уверен в нём','dimensions':{'trust':-3}})
    assert reverse.status_code==200
    state=reverse.json()['state']
    assert state['world']['relationships'][actor+':'+target]['dimensions']['trust']==-10
    assert state['world']['relationships'][target+':'+actor]['dimensions']['trust']==-3
    removed=client.patch(url(target),json={'revision':reverse.json()['revision'],'target_id':actor,'delete':True})
    assert removed.status_code==200
    assert target+':'+actor not in removed.json()['state']['world']['relationships']
    assert actor+':'+target in removed.json()['state']['world']['relationships']


def test_context_separates_current_knowledge_from_provenance_and_keeps_static_style(db):
    from backend.runtime_v3.models import Fact,Knowledge
    repo,_,sid=db;snapshot=repo.get_snapshot(sid);state=snapshot['world_state']
    actor=state['camera']['controlled_actor_id']
    state['facts']['known']=Fact(id='known',text='Игрок знает пароль',visibility='secret').model_dump()
    state['knowledge'][actor+':known']=Knowledge(actor_id=actor,fact_id='known').model_dump()
    card=next(c for c in snapshot['character_cards'] if c['id']==actor)
    card['fields']['Стиль общения']='Короткие фразы, сухой юмор'
    messages=build_context(snapshot,[],'Вспоминаю пароль','turn',32768,2000,world_history={'events':[]})
    knowledge=json.loads(next(m['content'] for m in messages if m['content'].startswith('Знания POV')).split('\n',1)[1])
    assert knowledge[0]==dict(actor_id=actor,fact_id='known',status='known')
    assert str(messages).count('Игрок знает пароль')==1
    assert 'Короткие фразы, сухой юмор' in str(messages)
    current=json.loads(next(m['content'] for m in messages if m['content'].startswith('Текущее состояние')).split('\n',1)[1])
    assert 'scenes' not in current and 'events' not in current
    assert all('source_event_id' not in k for k in current['knowledge'])
