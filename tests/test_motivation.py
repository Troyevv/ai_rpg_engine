import json
import pytest
from test_api import api, new_save
from context_builder import build_context


def test_motivation_persists_isolated_and_enters_context(api):
    client, app = api
    world, save = new_save(client)
    other = client.post(f"/api/worlds/{world['id']}/saves",json={'name':'Другая ветка'}).json()
    actor = save['state']['controlled_actor_id']
    path=f"/api/saves/{save['id']}/characters/{actor}/motivation"
    payload={'revision':save['revision'],'short_goal':'Проверить маяк','intentions':['Позвонить смотрителю']}
    response=client.patch(path,json=payload)
    assert response.status_code==200
    updated=response.json()
    fresh=client.get(f"/api/saves/{save['id']}").json()
    assert fresh['state']['world']['characters'][actor]['short_goal']=='Проверить маяк'
    assert fresh['state']['world']['characters'][actor]['intentions']==['Позвонить смотрителю']
    assert fresh['revision']==save['revision']+1
    assert client.get(f"/api/saves/{other['id']}").json()['state']==other['state']
    assert client.get(f"/api/worlds/{world['id']}").json()['state']==world['state']
    context=build_context(fresh['state'],[],'Осмотреться','turn',32768,4000)
    assert 'Проверить маяк' in str(context) and 'Позвонить смотрителю' in str(context)
    assert client.patch(path,json=payload).status_code==409
    payload.update(revision=updated['revision'],short_goal='',intentions=[])
    assert client.patch(path,json=payload).status_code==200
    final=client.get(f"/api/saves/{save['id']}").json()['state']
    card=next(c for c in final['characters'] if c['id']==actor)
    assert card['fields']['Чего хочет']=='' and card['fields']['Намерения']==''
    assert final['world']['characters'][actor]['obligations']==save['state']['world']['characters'][actor]['obligations']


def test_motivation_authorization_validation_and_pov(api):
    client,app=api
    _,save=new_save(client)
    actor=save['state']['controlled_actor_id']
    npc=next(c['id'] for c in save['state']['characters'] if c['id']!=actor)
    path=lambda cid:f"/api/saves/{save['id']}/characters/{cid}/motivation"
    body={'revision':save['revision'],'short_goal':'Цель','intentions':[]}
    assert client.patch(path(npc),json=body).status_code==409
    for patch in [{'intentions':[' ']},{'intentions':['x'*2001]},{'obligations':[]}]:
        assert client.patch(path(actor),json={**body,**patch}).status_code in (409,422)
    app.state.repository.switch_actor(save['id'],npc,save['revision'])
    body['revision']+=1
    assert client.patch(path(actor),json=body).status_code==409
    assert client.patch(path(npc),json=body).status_code==200


def test_motivation_does_not_rewrite_generation_snapshots(api):
    from unittest.mock import patch
    from test_api import REMOTE, wait_job
    from test_engine import NARRATIVE, result
    client,app=api
    _,save=new_save(client)
    def stream(**kwargs):
        yield json.dumps(result(),ensure_ascii=False) if kwargs.get('response_format') else NARRATIVE
    with patch('engine.chat_stream',side_effect=stream):
        job=client.post(f"/api/saves/{save['id']}/turns",json={'kind':'start','revision':save['revision'],'config':REMOTE,'api_key':'test'}).json()
        assert wait_job(client,job['id'])['status']=='saved'
    repo=app.state.repository
    with repo.connect() as db:
        before=[tuple(r) for r in db.execute('SELECT payload,context_json,memory_before_json FROM response_variants')]
    save=client.get(f"/api/saves/{save['id']}").json()
    actor=save['state']['controlled_actor_id']
    assert client.patch(f"/api/saves/{save['id']}/characters/{actor}/motivation",json={'revision':save['revision'],'short_goal':'Новая цель','intentions':[]}).status_code==200
    with repo.connect() as db:
        assert before==[tuple(r) for r in db.execute('SELECT payload,context_json,memory_before_json FROM response_variants')]
