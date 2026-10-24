"""Manual authoring contracts, without a real provider or second state model."""
from copy import deepcopy
import json
from unittest.mock import patch
from test_api import api, REMOTE, wait_job
from backend.services import world_builder as builder
from backend.runtime_v3.models import Character, Location, Fact, Knowledge, ObjectiveRelation, Relationship


def create(client):
    w=client.post('/api/workspaces',json={'name':'Ручной мир'}).json()
    r=client.post(f"/api/workspaces/{w['id']}/builder",json={'revision':w['revision']})
    assert r.status_code==200,r.text
    return r.json()


def playable(snapshot):
    s=deepcopy(snapshot);w=s['world_state']
    w['locations']['room']=Location(id='room',name='Комната').model_dump()
    for cid,name in [('a','Анна'),('b','Борис')]:
        w['characters'][cid]=Character(id=cid,display_name=name,life_status='alive',location_id='room').model_dump()
    w['meta']['current_protagonist_id']='a'
    w['camera'].update(mode='actor',controlled_actor_id='a',pov_actor_id='b',location_id='room',present_character_ids=['a','b'],situation='Разговор за столом.')
    w['facts']['secret']=Fact(id='secret',text='Скрытая записка',visibility='secret',character_ids=['b']).model_dump()
    w['knowledge']['b:secret']=Knowledge(actor_id='b',fact_id='secret').model_dump()
    w['relationships']['a:b']=Relationship(source_id='a',target_id='b',dimensions={'trust':25}).model_dump()
    w['relationships']['b:a']=Relationship(source_id='b',target_id='a',dimensions={'trust':-20}).model_dump()
    return s


def save(client,d,state):
    return client.put(f"/api/workspaces/{d['id']}/builder",json={'revision':d['revision'],'world':state['world_state'],'campaign':state['campaign']['campaign'],'cards':state['character_cards']})


def test_incomplete_save_conflict_delete_and_launch(api):
    client,app=api;d=create(client);state=playable(d['state'])
    state['world_state']['characters']['a']['display_name']=''
    r=save(client,d,state);assert r.status_code==200,r.text
    partial=r.json();assert partial['validation']['errors']
    assert client.post(f"/api/workspaces/{d['id']}/draft/confirm",json={'revision':partial['revision'],'version_id':partial['version_id']}).status_code==409
    assert save(client,d,state).status_code==409
    state['world_state']['characters']['a']['display_name']='Анна'
    r=save(client,partial,state);assert r.status_code==200,r.text
    d=r.json();assert not d['validation']['errors'],d['validation']
    broken=deepcopy(d['state']);del broken['world_state']['characters']['b']
    assert save(client,d,broken).status_code==409
    r=client.post(f"/api/workspaces/{d['id']}/draft/confirm",json={'revision':d['revision'],'version_id':d['version_id']})
    assert r.status_code==200,r.text
    loaded_world=client.get(f"/api/worlds/{r.json()['world']}")
    assert loaded_world.status_code==200,loaded_world.text
    assert loaded_world.json()['scene_meta']['location']=='Комната'
    another=client.post(f"/api/worlds/{r.json()['world']}/saves",json={'name':'Другое прохождение'})
    assert another.status_code==200,another.text
    snapshot=app.state.repository.get_snapshot(r.json()['save'])
    assert snapshot['world_state']['camera']['pov_actor_id']=='b'
    assert snapshot['world_state']['camera']['controlled_actor_id']=='a'
    assert set(snapshot['world_state']['knowledge'])=={'b:secret'}
    assert snapshot['world_state']['relationships']['b:a']['dimensions']['trust']==-20


def test_calendar_modes_and_invalid_dates():
    s=playable(builder.empty('Мир'));cal=s['world_state']['meta']['calendar']
    cal['start_date']='2024-02-29';cal['start_weekday']=0
    s=builder.normalize(s);assert s['world_state']['meta']['calendar']['start_weekday']==3
    assert '2024-02-29' in builder.time_label(s)
    s['world_state']['meta']['calendar']['start_date']='2023-02-29'
    assert builder.report(s)['errors']
    cal=s['world_state']['meta']['calendar'];cal['start_date']=None
    assert not builder.report(s)['errors']
    cal.update(start_date='1370-02-30',profile={'id':'fantasy','system':'custom','month_lengths':[30,30],'month_names':['Первый','Второй'],'weekday_names':['A','B','C','D'],'observances':[],'seasons':[]})
    assert not builder.report(s)['errors']
    assert '1370-02-30' in builder.time_label(s)


def test_proposal_does_not_write_and_old_revision_cannot_apply(api):
    client,app=api;d=create(client);d=save(client,d,playable(d['state'])).json()
    before=deepcopy(d['state']);path=['world_state','camera','situation']
    with patch('backend.services.preparation.chat_stream',return_value=iter([json.dumps({'value':'Новый разговор.'})])):
        r=client.post(f"/api/workspaces/{d['id']}/builder/generate",json={'revision':d['revision'],'path':path,'instruction':'Новая сцена','config':REMOTE,'api_key':'test-secret'})
        assert r.status_code==200,r.text
        job=wait_job(client,r.json()['id']);assert job['status']=='saved',job
    after=client.get(f"/api/workspaces/{d['id']}/builder").json()
    assert after['state']==before
    assert after['revision']==d['revision']
    assert after['proposal']=={'path':path,'value':'Новый разговор.'}
    before['world_state']['camera']['situation']=after['proposal']['value']
    accepted=save(client,after,before);assert accepted.status_code==200,accepted.text
    assert accepted.json()['proposal'] is None
    assert accepted.json()['state']['world_state']['knowledge']==d['state']['world_state']['knowledge']
    restored=client.post(f"/api/workspaces/{d['id']}/builder/restore/{d['version_id']}",json={'revision':accepted.json()['revision']})
    assert restored.status_code==200,restored.text
    assert restored.json()['state']==d['state']


def test_history_ordinary_turn_save_reload_and_next_turn(api):
    client,app=api;d=create(client);state=playable(d['state'])
    state['initial_history']['events']=[{'id':'past','text':'Борис нашёл записку.','participants':['b'],'witnesses':['b'],'fact_ids':['secret'],'medium':'discovery','evidence':'Авторский факт','minute':0,'turn_id':0,'recorded_minute':0}]
    state['world_state']['knowledge']['b:secret']['source_event_id']='past'
    r=client.put(f"/api/workspaces/{d['id']}/builder",json={'revision':d['revision'],'world':state['world_state'],'campaign':state['campaign']['campaign'],'cards':[], 'history':state['initial_history']})
    assert r.status_code==200,r.text
    d=r.json();assert not d['validation']['errors'],d['validation']
    r=client.post(f"/api/workspaces/{d['id']}/draft/confirm",json={'revision':d['revision'],'version_id':d['version_id']})
    assert r.status_code==200,r.text
    sid=r.json()['save'];repo=app.state.repository
    from backend.runtime_v3.repository import read_history
    with repo.connect() as db:
        history,_=read_history(db,repo.get_snapshot(sid)['history_head'])
        assert history['events'][0]['id']=='past'
    def stream(**kwargs):
        if kwargs.get('response_format'):
            yield json.dumps({'final_scene':{'location_id':'room','present_character_ids':['a','b'],'elapsed_minutes':1},'choices':[{'action':'Посмотреть в окно','speech':''}]})
        else:yield 'В комнате тихо. Борис смотрит в окно.'
    for kind in ('start','turn','turn'):
        loaded=client.get(f'/api/saves/{sid}').json()
        with patch('engine.chat_stream',side_effect=stream):
            response=client.post(f'/api/saves/{sid}/turns',json={'kind':kind,'text':'' if kind=='start' else 'Осмотреть комнату.','revision':loaded['revision'],'config':REMOTE,'api_key':'test-secret'})
            assert response.status_code==200,response.text
            job=wait_job(client,response.json()['id']);assert job['status']=='saved',job
        after=repo.get_snapshot(sid)
        assert after['world_state']['knowledge']['b:secret']['status']=='known'
        assert 'a:secret' not in after['world_state']['knowledge']
        assert after['world_state']['camera']['pov_actor_id']=='b'


def test_proposal_rejects_structural_changes_and_types():
    from backend.services.builder_generation import verify,target
    import pytest
    with pytest.raises(ValueError):verify({'id':'a','name':'Anna'},{'id':'b','name':'Anna'})
    with pytest.raises(ValueError):verify({'status':'alive'},{'status':'dead'})
    with pytest.raises(ValueError):target(playable(builder.empty('World')),['world_state','camera','controlled_actor_id'])
    verify({'text':'Old','dimensions':{'trust':10}},{'text':'New','dimensions':{'trust':10}})


def test_schema_covers_every_current_model_field():
    from backend.runtime_v3.models import WorldStateV3
    s=builder.schema()
    assert set(s['properties'])==set(WorldStateV3.model_fields)
    assert set(s['$defs']['Character']['properties'])==set(Character.model_fields)
    assert 'CalendarProfile' in s['$defs'] and 'Knowledge' in s['$defs']


def test_character_proposal_includes_personality_without_changing_links(api):
    from backend.services.builder_generation import template
    client,app=api;d=create(client);d=save(client,d,playable(d['state'])).json()
    path=['world_state','characters','b'];answer=template(d['state'],path)
    for item in answer['personality']['items'].values():item['text']='Спокойный и внимательный, отвечает коротко.'
    answer['appearance']['legacy_text']='Тёмные волосы и зелёные глаза.'
    with patch('backend.services.preparation.chat_stream',return_value=iter([json.dumps({'value':answer})])):
        r=client.post(f"/api/workspaces/{d['id']}/builder/generate",json={'revision':d['revision'],'path':path,'config':REMOTE,'api_key':'test-secret'})
        assert r.status_code==200,r.text
        job=wait_job(client,r.json()['id']);assert job['status']=='saved',job
    current=client.get(f"/api/workspaces/{d['id']}/builder").json()
    assert current['state']==d['state']
    assert current['proposal']['value']['personality']['items']['traits']['text']
    current['state']['world_state']['characters']['b']=current['proposal']['value']
    r=save(client,current,current['state']);assert r.status_code==200,r.text
    assert not r.json()['validation']['errors'],r.json()['validation']
    assert r.json()['state']['world_state']['relationships']==d['state']['world_state']['relationships']


def test_rich_authoring_uses_existing_qa_world_and_canonical_family():
    from devtools.narrative_test_world import build_fixture
    from backend.runtime_v3.migration import migrate_v2
    from backend.runtime_v3.models import assert_world_state_v3_invariants
    # Extend the #78 fixture path; no separate fixture language or runtime.
    for checkpoint in ('family','residence-roles','appearance'):
        migrated=migrate_v2(build_fixture(checkpoint))
        snapshot=migrated.snapshot
        snapshot['initial_history']={'events':migrated.history['events']}
        edited=builder.normalize(snapshot)
        assert not builder.report(edited)['errors'],(checkpoint,builder.report(edited))
        launched=builder.launch(edited)
        assert_world_state_v3_invariants(launched['world_state'])
        for section in ('objective_relations','locations','organizations','roles','knowledge'):
            assert launched['world_state'][section]==snapshot['world_state'][section]


def test_symmetric_family_endpoints_normalized_not_directed_feelings():
    s=playable(builder.empty('Мир'))
    s['world_state']['objective_relations']['friends']=ObjectiveRelation(id='friends',kind='friend',source_id='b',target_id='a').model_dump()
    normalized=builder.normalize(s)
    assert normalized['world_state']['objective_relations']['friends']['source_id']=='a'
    assert normalized['world_state']['relationships']==s['world_state']['relationships']
    assert not builder.report(normalized)['errors']


def test_initial_values_cannot_silently_disappear_in_salvage():
    from backend.runtime_v3.models import DurableValue
    s=playable(builder.empty('Мир'))
    s['world_state']['characters']['a']['values']={'value1':DurableValue(id='wrong',text='Честность').model_dump()}
    errors=builder.report(s)['errors']
    assert any('values' in e['path'] for e in errors),errors
    s['world_state']['characters']['a']['values']['value1']['id']='value1'
    assert not builder.report(s)['errors']
    assert builder.launch(s)['world_state']['characters']['a']['values']['value1']['text']=='Честность'
