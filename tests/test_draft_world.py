import json
from copy import deepcopy
import pytest
from test_api import api, REMOTE, wait_job
from test_worlds import summary
from world_parser import parse_summary
from backend.services import draft_world as domain
from backend.services.draft_generation import decode_result


def fixture():
    state=domain.prepare(parse_summary(summary()))
    a,b,c=[x['id'] for x in state['characters'][:3]]
    state['world']['facts']['meeting']={'id':'meeting','text':'Тайная встреча у маяка','secret':True,'character_ids':[b,c],'evidence':['Записка']}
    state['world']['knowledge'].update({b+':meeting':{'actor_id':b,'fact_id':'meeting','status':'known','source_event_id':None},c+':meeting':{'actor_id':c,'fact_id':'meeting','status':'suspected','source_event_id':None}})
    state['world']['relationships'][b+':'+c]={'source_id':b,'target_id':c,'context':'Любовь','dimensions':{'trust':35}}
    state['world']['relationships'][c+':'+b]={'source_id':c,'target_id':b,'context':'Недоверие','dimensions':{'trust':-20}}
    scene=state['world']['scenes'][state['camera']['scene_id']]
    scene.update(location='Кухня',participants=[a,b,c])
    return domain.sync(state)


def test_roundtrip_and_projection():
    state=fixture()
    assert not domain.validate(state)['errors']
    assert parse_summary(domain.export_markdown(state))==state
    state['actor_scenes']={'secret':{'text':'Никогда не раскрывать'}}
    public=domain.player_view(state)
    assert 'Тайная встреча' not in json.dumps(public,ensure_ascii=False)
    assert 'Никогда не раскрывать' not in json.dumps(public,ensure_ascii=False)
    with pytest.raises(ValueError):parse_summary(domain.export_markdown(state).replace('# Новый мир','# Другой мир'))


def test_field_isolation_and_dependencies():
    state=fixture();cid=state['characters'][1]['id']
    updated=domain.patch(state,'character',cid,'fields.Внешность','Короткие волосы')
    assert updated['world']==state['world']
    assert updated['characters'][0]==state['characters'][0]
    assert updated['characters'][1]['id']==cid
    assert updated['characters'][1]['fields']['Внешность']=='Короткие волосы'
    with pytest.raises(ValueError):domain.remove(state,'character',cid)
    with pytest.raises(ValueError):domain.patch(state,'character',cid,'id','replacement')
    with pytest.raises(ValueError):decode_result('{"value":"Имя","extra":"oops"}',state,{'_draft_task':'field','_draft_target':{'kind':'character','id':cid,'field':'name'}})
    new,eid=domain.add(state,'character')
    assert domain.remove(new,'character',eid)==state


def make(client):
    w=client.post('/api/workspaces',json={'name':'Тест черновика'}).json()
    path=f"/api/workspaces/{w['id']}/draft"
    r=client.post(path+'/import',json={'revision':w['revision'],'text':domain.export_markdown(fixture())})
    assert r.status_code==200,r.text
    return path,client.get(path+'?author=true').json()


def test_revision_restore_confirm_and_save_isolation(api):
    client,app=api;path,draft=make(client)
    original=deepcopy(draft['state']);cid=original['characters'][0]['id']
    body={'revision':draft['revision'],'operation':'patch','kind':'actor','entity_id':cid,'field':'goals','value':['Проверить маяк']}
    r=client.patch(path,json=body);assert r.status_code==200,r.text
    updated=r.json();assert client.patch(path,json=body).status_code==409
    payload={'revision':updated['revision'],'version_id':updated['version_id']}
    saved=client.post(path+'/confirm',json=payload);assert saved.status_code==200,saved.text
    assert client.post(path+'/confirm',json=payload).json()==saved.json()
    sid=saved.json()['save'];game=client.get(f'/api/saves/{sid}').json()
    assert game['state']['world']['characters'][cid]['goals']==['Проверить маяк']
    restored=client.patch(path,json={'revision':updated['revision'],'operation':'restore','source_id':draft['version_id']})
    assert restored.status_code==200,restored.text
    assert restored.json()['state']==original
    assert client.get(f'/api/saves/{sid}').json()==game
    assert client.get(path).json()['state']['world']['facts'].get('meeting') is None
    with app.state.repository.connect() as db:
        assert db.execute('SELECT count(*) FROM saves').fetchone()[0]==1


def test_invalid_references_block_start_without_damage(api):
    client,app=api;path,draft=make(client)
    r=client.patch(path,json={'revision':draft['revision'],'operation':'patch','kind':'start','field':'controlled_actor_id','value':'missing'})
    assert r.status_code==200,r.text
    d=r.json();assert d['validation']['errors']
    r=client.post(path+'/confirm',json={'revision':d['revision'],'version_id':d['version_id']})
    assert r.status_code==409,r.text
    with app.state.repository.connect() as db:assert db.execute('SELECT count(*) FROM saves').fetchone()[0]==0


def test_generation_uses_jobs_preserves_variants_and_no_json_in_public_job(api):
    from unittest.mock import patch
    client,app=api;path,draft=make(client)
    expected=fixture();expected['campaign']['title']='Маяк'
    def stream(**kwargs):
        yield ('# Сценарный план\nПерсонажи и жизнь у маяка развиваются сами.'
               if 'Ты — сценарист' in kwargs['messages'][0]['content'] else json.dumps(expected,ensure_ascii=False))
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        response=client.post(path+'/generate',json={'revision':draft['revision'],'task':'world','text':'Сложный мир','config':REMOTE,'api_key':'test'})
        assert response.status_code==200,response.text
        job=wait_job(client,response.json()['id']);assert job['status']=='saved',job
        assert not job['narrative']
    updated=client.get(path+'?author=true').json()
    assert updated['state']['campaign']['title']=='Маяк'
    assert 'Сценарный план' in updated['outline']
    assert len(updated['history'])==2
    with app.state.repository.connect() as db:
        stages=[row[0] for row in db.execute('SELECT stage FROM llm_requests ORDER BY created_at,id')]
    assert 'draft_scenario' in stages and 'draft_world' in stages


def test_semantic_warning_and_rename_preserves_directed_relationships(api):
    client,_=api;path,d=make(client);cid=d['state']['characters'][0]['id']
    body={'revision':d['revision'],'operation':'patch','kind':'character','entity_id':cid,'field':'fields.Статус','value':'12 лет. Врач.'}
    assert client.patch(path,json=body).status_code==409
    r=client.patch(path,json={**body,'warnings_ack':True});assert r.status_code==200
    assert r.json()['validation']['warnings']
    d=r.json();relations=deepcopy(d['state']['world']['relationships'])
    r=client.patch(path,json={'revision':d['revision'],'operation':'patch','kind':'character','entity_id':cid,'field':'name','value':'Другое имя'})
    assert r.status_code==200 and r.json()['state']['world']['relationships']==relations


def test_field_regeneration_instruction_and_restart(api):
    from unittest.mock import patch
    from backend.repositories.preparation import Repository
    client,app=api;path,d=make(client);cid=d['state']['characters'][0]['id'];before=d['state']
    captured=[]
    def stream(**kwargs):
        captured.extend(kwargs['messages']);yield '{"value":"Седые волосы"}'
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        r=client.post(path+'/generate',json={'revision':d['revision'],'task':'field','kind':'character','entity_id':cid,'field':'fields.Внешность','text':'Сохрани всё, измени только цвет волос','config':REMOTE,'api_key':'test'})
        assert r.status_code==200,r.text
        assert wait_job(client,r.json()['id'])['status']=='saved'
    after=client.get(path+'?author=true').json()['state']
    assert after['world']==before['world']
    assert after['characters'][0]['fields']['Внешность']=='Седые волосы'
    assert 'измени только цвет волос' in str(captured)
    with app.state.repository.connect() as db:path_db=db.execute('PRAGMA database_list').fetchone()[2]
    assert Repository(path_db).draft(d['id'],True)['state']==after


def test_legacy_import_preserves_source_and_reports_repairs(api):
    client,_=api;w=client.post('/api/workspaces',json={'name':'Legacy'}).json();path=f"/api/workspaces/{w['id']}/draft"
    r=client.post(path+'/import',json={'revision':w['revision'],'text':'\ufeff'+summary()})
    assert r.status_code==200,r.text
    d=client.get(path+'?author=true').json()
    assert d['source_text'].lstrip('\ufeff')==summary() and d['import_warnings']
    assert len(d['state']['characters'])==8


def test_first_context_uses_confirmed_revision(api):
    from context_builder import build_context
    client,_=api;path,d=make(client)
    r=client.patch(path,json={'revision':d['revision'],'operation':'patch','kind':'campaign','field':'setting','value':'Город на плавучих островах'})
    d=r.json();r=client.post(path+'/confirm',json={'revision':d['revision'],'version_id':d['version_id']})
    s=client.get(f"/api/saves/{r.json()['save']}").json()['state']
    assert s==d['state']
    ctx=build_context(s,[],'','start',32768,4000)
    assert 'Город на плавучих островах' in str(ctx)


def test_idea_generation_expands_into_independent_world_entities(api):
    from unittest.mock import patch
    from test_api import wait_job
    client,_=api
    workspace=client.post('/api/workspaces',json={'name':'Клиника'}).json()
    original='Клиника. Илья — врач. Люда — его начальница, они по-дружески подкалывают друг друга. Катя скрывает встречу с Тимуром. Придумай всем интересные характеры, рабочие привычки и начало в четверг 14:00.'
    world=fixture();actors=world['characters'][:4]
    for card,name in zip(actors,['Илья','Люда','Катя','Тимур']):card['name']=name
    a,b,c,d=[x['id'] for x in actors]
    world['campaign'].update(title='Клиника',description='В клинике смена начинается с привычного шума и давнего напряжения между коллегами.',public_description='Долгая история коллег, дружбы и трудных решений в городской клинике.')
    world['characters'][0]['fields']['Суть']='Привык скрывать усталость за короткими шутками; во время сложного дежурства спокойнее всех.'
    world['characters'][1]['fields']['Суть']='Прямая и внимательная начальница: шутит с Ильёй, но строго разделяет работу и дружбу.'
    world['world']['relationships'][a+':'+b]={'source_id':a,'target_id':b,'context':'Уважает как начальницу и часто подшучивает.','dimensions':{'respect':65}}
    world['world']['relationships'][b+':'+a]={'source_id':b,'target_id':a,'context':'Ценит и заботится, хотя строгая на работе.','dimensions':{'trust':80}}
    world['world']['facts']['meeting']['character_ids']=[c,d]
    world['world']['knowledge']={c+':meeting':{'actor_id':c,'fact_id':'meeting','status':'known','source_event_id':None},d+':meeting':{'actor_id':d,'fact_id':'meeting','status':'known','source_event_id':None}}
    world['world']['scenes'][world['camera']['scene_id']]['end_minute']=5160
    world['world']['scenes'][world['camera']['scene_id']]['start_minute']=5160
    world['world_clock']={'minute':5160,'last_event_time':'День 4 (Чт) 14:00'}
    for item in world['world']['characters'].values():
        if item['minute'] is not None:item['minute']=5160
    messages=[]
    def stream(**kwargs):
        messages.extend(kwargs['messages'])
        yield ('# Клиника\nЛюда разряжает напряжение короткими шутками, даже когда отвечает за сложное отделение.'
               if 'Ты — сценарист' in kwargs['messages'][0]['content'] else json.dumps(world,ensure_ascii=False))
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        j=client.post(f"/api/workspaces/{workspace['id']}/draft/generate",json={'revision':workspace['revision'],'task':'world','text':original,'config':REMOTE,'api_key':'fixture'}).json()
        assert wait_job(client,j['id'])['status']=='saved'
    assert 'Не ограничивайся перечислением фактов' in next(m['content'] for m in messages if 'Ты Сценарист и Генератор' in m['content'])
    assert original in messages[-1]['content']
    draft=client.get(f"/api/workspaces/{workspace['id']}/draft?author=true").json()
    result=draft['state'];assert not draft['validation']['errors']
    assert result['world']['relationships'][a+':'+b]['context']!=result['world']['relationships'][b+':'+a]['context']
    assert 'заботится' in result['world']['relationships'][b+':'+a]['context']
    assert {v['actor_id'] for v in result['world']['knowledge'].values()}=={c,d}
    assert a not in {v['actor_id'] for v in result['world']['knowledge'].values()}
    assert result['world_clock']['minute']==5160
    assert 'Прямая' in result['characters'][1]['fields']['Суть']
    assert result['campaign']['public_description'] != result['campaign']['description']
    assert 'Тайная встреча' not in json.dumps(client.get(f"/api/workspaces/{workspace['id']}/draft").json()['state'],ensure_ascii=False)


def test_json_continuation_keeps_json_format():
    from backend.services.continuation import request_context
    messages=[{'role':'system','content':'Отвечай JSON'}]
    result,_=request_context(messages,'{"world":',32768,500,format_hint='json')
    assert 'JSON-объект' in result[-1]['content'] and 'Markdown' in result[-1]['content']
    assert 'Продолжи документ' not in result[-1]['content']
