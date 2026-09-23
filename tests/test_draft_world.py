import json
from copy import deepcopy
import pytest
from test_api import api, REMOTE, wait_job
from test_worlds import summary
from world_parser import parse_summary
from backend.services import draft_world as domain
from backend.services.draft_generation import decode_result
from backend.services.world import CARD_FIELDS, normalize
from context_builder import build_context


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


def test_legacy_character_card_migrates_without_inventing_details(api):
    client,app=api
    old=domain.prepare(parse_summary(summary()))
    first=old['characters'][0]['fields']
    legacy=first['Характер']
    first['Суть']=first.pop('Характер')
    updated=normalize(old)
    assert first['Суть']==legacy  # the persisted source is never mutated
    assert updated['characters'][0]['fields']['Характер']==legacy
    assert 'Суть' not in updated['characters'][0]['fields']
    assert all(updated['characters'][0]['fields'][key]=='' for key in CARD_FIELDS if key not in ('Характер','Статус','Внешность'))
    assert normalize(updated)==updated
    assert updated['world']['characters']==old['world']['characters']
    assert parse_summary(domain.export_markdown(domain.prepare(updated)))==domain.prepare(updated)
    w=client.post('/api/workspaces',json={'name':'Старый мир'}).json()
    with app.state.repository.connect() as db:
        app.state.repository._record_document(db,'world_draft',w['id'],json.dumps({'state':old,'source':'','generated':False},ensure_ascii=False),True,'legacy')
    draft=client.get(f"/api/workspaces/{w['id']}/draft?author=true").json()
    assert draft['state']['characters'][0]['fields']['Характер']==legacy
    assert draft['state']['characters'][0]['fields']['Стиль общения']==''
    reply=client.patch(f"/api/workspaces/{w['id']}/draft",json={'revision':draft['revision'],'operation':'patch','kind':'character','entity_id':old['characters'][0]['id'],'field':'fields.Стиль общения','value':'Говорит отрывисто.'})
    assert reply.status_code==200,reply.text
    assert reply.json()['state']['characters'][0]['fields']['Стиль общения']=='Говорит отрывисто.'


def test_current_scene_voices_reach_gm_without_all_npc_cards():
    state=fixture()
    a,b,c=[card['id'] for card in state['characters'][:3]]
    state['world']['scenes'][state['camera']['scene_id']]['participants']=[a,b]
    state['scene_meta']['present_ids']=[a,b]
    state['characters'][1]['fields'].update({'Стиль общения':'Говорит рублеными фразами, любит ироничные уточнения.',
        'Привычки':'Поправляет рукав перед ответом.', 'Сильные стороны':'Умеет убеждать команду.',
        'Слабости':'Не признаёт ошибки.', 'Страхи и уязвимости':'Боится повторить провал.'})
    state['characters'][2]['fields']['Стиль общения']='Исключительный голос отсутствующего персонажа.'
    context=build_context(state,[],'Осмотреть кабинет.','turn',32768,4000)
    gm=next(m['content'] for m in context if m['content'].startswith('NPC и отношения'))
    assert 'Говорит рублеными фразами' in gm
    assert 'Исключительный голос отсутствующего персонажа' not in gm
    assert 'Характер' in gm and 'Биография' in gm
    assert 'При написании диалогов используй «Стиль общения»' in str(context)
    assert [x['id'] for x in json.loads(gm.split('\n',1)[1])['characters']]==[a,b]


def test_whole_character_regeneration_keeps_dynamic_state():
    state=fixture();cid=state['characters'][1]['id']
    old=deepcopy(state['world']['characters'][cid])
    card=deepcopy(state['characters'][1]);card.setdefault('aliases',[])
    card['fields'].update({key:f'Новая деталь: {key}' for key in CARD_FIELDS})
    config={'_draft_task':'character','_draft_target':{'kind':'character','id':cid}}
    updated=decode_result(json.dumps({'value':{key:card[key] for key in ('name','aliases','fields')}},ensure_ascii=False),state,config)
    assert updated['world']['characters'][cid]==old
    assert all(updated['characters'][1]['fields'][key]==f'Новая деталь: {key}' for key in CARD_FIELDS)
    del card['fields']['Стиль общения']
    with pytest.raises(ValueError,match='постоянные поля'):
        decode_result(json.dumps({'value':{key:card[key] for key in ('name','aliases','fields')}},ensure_ascii=False),state,config)


def test_roundtrip_and_projection():
    state=fixture()
    assert not domain.validate(state)['errors']
    assert parse_summary(domain.export_markdown(state))==state
    state['actor_scenes']={'secret':{'text':'Никогда не раскрывать'}}
    public=domain.player_view(state)
    assert 'Тайная встреча' not in json.dumps(public,ensure_ascii=False)
    assert 'Никогда не раскрывать' not in json.dumps(public,ensure_ascii=False)
    with pytest.raises(ValueError):parse_summary(domain.export_markdown(state).replace('# Новый мир','# Другой мир'))


def test_player_preview_preserves_known_world_without_spoilers():
    state=fixture()
    a,b,c=[x['id'] for x in state['characters'][:3]]
    for card,name in zip(state['characters'],['Илья','Катя','Соня']):card['name']=name
    state['locations']=[{'id':'morgue','name':'Морг','text':'Илья работает здесь.'}]
    scene=state['world']['scenes'][state['camera']['scene_id']]
    scene.update(location='Морг',text='Илья проводит вскрытие.',participants=[a,b])
    state['world_clock']={'minute':5160,'last_event_time':'День 4 (Чт) 14:00'}
    scene.update(start_minute=5160,end_minute=5160)
    state['world']['characters'][a].update(minute=5160,location='Морг',situation='Проводит вскрытие')
    for character in state['world']['characters'].values():
        if character.get('minute') is not None:character['minute']=5160
    state['world']['facts'].update(public={'id':'public','text':'Клиника открыта','secret':False,'character_ids':[]},
        actor_only={'id':'actor_only','text':'Илья знает о дежурстве','secret':True,'character_ids':[a]},
        private={'id':'private','text':'Соня знает про измену','secret':True,'character_ids':[c]},
        director={'id':'director','text':'Невидимый режиссёрский факт','secret':False,'director_only':True,'character_ids':[]})
    state['world']['knowledge'].update(ak={'actor_id':a,'fact_id':'actor_only','status':'known','source_event_id':None},
        pk={'actor_id':c,'fact_id':'private','status':'known','source_event_id':None},
        uk={'actor_id':a,'fact_id':'private','status':'unknown','source_event_id':None})
    state['world']['relationships'].update(ab={'source_id':a,'target_id':b,'context':'Илья доверяет Кате','dimensions':{'trust':70}},
        ba={'source_id':b,'target_id':a,'context':'Катя тайно влюблена','dimensions':{'attraction':80}})
    state['world']['threads'].update(known={'id':'known','description':'Известный конфликт','state':'Режиссёрский план','public_state':'Нерешённая ссора','status':'active','character_ids':[a,b],'relevance':.5,'visible_to_ids':[a]},
        hidden={'id':'hidden','description':'Скрытая линия Сони','state':'Секрет','status':'active','character_ids':[a,c],'relevance':.5})
    state=domain.sync(state)
    player=domain.player_view(state);world=player['world']
    assert set(world['facts'])=={'public','actor_only'}
    assert set(world['relationships'])>= {'ab'} and 'ba' not in world['relationships']
    assert set(world['threads'])=={'known'} and world['threads']['known']['state']=='Нерешённая ссора'
    assert player['locations'][0]['name']=='Морг'
    assert player['scene']=='Илья проводит вскрытие.'
    assert player['scene_meta']['location']=='Морг' and player['world_clock']['minute']==5160
    assert 'Соня знает про измену' not in json.dumps(player,ensure_ascii=False)
    assert 'Катя тайно влюблена' not in json.dumps(player,ensure_ascii=False)
    author=domain.prepare(state)
    assert set(author['world']['facts'])>set(world['facts'])
    assert {'ab','ba'}<=set(author['world']['relationships'])


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


def test_draft_soft_delete_restores_versions_and_keeps_confirmed_save(api):
    client,_=api;path,draft=make(client)
    confirmed=client.post(path+'/confirm',json={'revision':draft['revision'],'version_id':draft['version_id']})
    assert confirmed.status_code==200
    save_id=confirmed.json()['save'];before=client.get(f'/api/saves/{save_id}').json()
    wid=draft['id'];deleted=client.request('DELETE',f'/api/workspaces/{wid}',json={'revision':draft['revision']})
    assert deleted.status_code==200
    assert wid not in [item['id'] for item in client.get('/api/workspaces').json()]
    removed=next(item for item in client.get('/api/workspaces?deleted=true').json() if item['id']==wid)
    assert client.get(f'/api/saves/{save_id}').json()==before
    assert client.post(f'/api/workspaces/{wid}/restore',json={'revision':removed['revision']}).status_code==200
    restored=client.get(path+'?author=true').json()
    assert restored['version_id']==draft['version_id'] and restored['state']==draft['state']


def test_invalid_references_block_start_without_damage(api):
    client,app=api;path,draft=make(client)
    r=client.patch(path,json={'revision':draft['revision'],'operation':'patch','kind':'start','field':'controlled_actor_id','value':'missing'})
    assert r.status_code==200,r.text
    d=r.json();assert d['validation']['errors']
    r=client.post(path+'/confirm',json={'revision':d['revision'],'version_id':d['version_id']})
    assert r.status_code==409,r.text
    with app.state.repository.connect() as db:assert db.execute('SELECT count(*) FROM saves').fetchone()[0]==0


def test_generation_uses_one_request_and_saves_valid_world(api):
    from unittest.mock import patch
    client,app=api;path,draft=make(client)
    expected=fixture();expected['campaign']['title']='Маяк'
    calls=[];phases=[]
    def stream(**kwargs):
        calls.append(kwargs)
        with app.state.repository.connect() as db:
            phases.append(db.execute('SELECT phase FROM preparation_jobs ORDER BY rowid DESC LIMIT 1').fetchone()[0])
        assert 'Ты автор полноценного живого RPG-мира' in kwargs['messages'][0]['content']
        yield json.dumps(expected,ensure_ascii=False)
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        response=client.post(path+'/generate',json={'revision':draft['revision'],'task':'world','text':'Сложный мир','config':REMOTE,'api_key':'test'})
        assert response.status_code==200,response.text
        job=wait_job(client,response.json()['id']);assert job['status']=='saved',job
        assert not job['narrative']
    updated=client.get(path+'?author=true').json()
    assert updated['state']['campaign']['title']=='Маяк'
    assert not updated['validation']['errors'] and len(updated['history'])==2
    assert len(calls)==1 and phases==['world']
    prompt=calls[0]['messages'][0]['content']
    assert 'НЕ полная спецификация' in prompt and 'минимальными текстами' in prompt
    assert 'A → B и B → A' in prompt and 'knowledge["k1"]' in prompt
    with app.state.repository.connect() as db:
        stages=[row[0] for row in db.execute('SELECT stage FROM llm_requests')]
    assert stages==['draft_world']


def test_deepseek_json_mode_repairs_only_bad_format(api):
    from unittest.mock import patch
    client,app=api;path,draft=make(client)
    calls=[]
    def stream(**kwargs):
        calls.append(kwargs)
        if len(calls)==1:yield '{"world":'
        else:yield json.dumps(fixture(),ensure_ascii=False)
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        job=client.post(path+'/generate',json={'revision':draft['revision'],'task':'world',
                                                'text':'Сложный мир','config':REMOTE,'api_key':'fixture'})
        assert wait_job(client,job.json()['id'])['status']=='saved'
    assert len(calls)==2
    assert all(c['response_format']=={'type':'json_object'} for c in calls)
    assert 'ТОЛЬКО технические ошибки' in calls[1]['messages'][0]['content']
    with app.state.repository.connect() as db:
        assert sorted(r[0] for r in db.execute('SELECT stage FROM llm_requests'))==['draft_world','draft_world_repair']


def test_failed_structural_repair_keeps_previous_version(api):
    from unittest.mock import patch
    client,app=api;path,draft=make(client)
    invalid=fixture();invalid['protagonist_id']='missing'
    calls=[]
    def stream(**kwargs):
        calls.append(kwargs)
        yield json.dumps(invalid,ensure_ascii=False)
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        job=client.post(path+'/generate',json={'revision':draft['revision'],'task':'world','text':'Идея',
                                                'config':REMOTE,'api_key':'fixture'})
        assert wait_job(client,job.json()['id'])['status']=='error'
    assert len(calls)==2
    assert client.get(path+'?author=true').json()['version_id']==draft['version_id']


def test_output_limit_does_not_start_a_continuation(api):
    from unittest.mock import patch
    from llm import OutputLimitReached
    client,app=api;path,draft=make(client)
    calls=[]
    def stream(**kwargs):
        calls.append(kwargs)
        yield '{"world":'
        raise OutputLimitReached('limit')
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        job=client.post(path+'/generate',json={'revision':draft['revision'],'task':'world','text':'Идея',
                                                'config':REMOTE,'api_key':'fixture'})
        assert wait_job(client,job.json()['id'])['status']=='error'
    assert len(calls)==1
    with app.state.repository.connect() as db:
        assert [r[0] for r in db.execute('SELECT stage FROM llm_requests')]==['draft_world']
    assert client.get(path+'?author=true').json()['version_id']==draft['version_id']


def test_scenario_route_stays_separate_from_quick_generation(api):
    from unittest.mock import patch
    client,app=api
    workspace=client.post('/api/workspaces',json={'name':'История со Сценаристом'}).json()
    path=f"/api/workspaces/{workspace['id']}"
    calls=[]
    def stream(**kwargs):
        calls.append(kwargs['messages'])
        if 'Ты — сценарист' in kwargs['messages'][0]['content']:
            yield '# Сценарий\n\nГерой встречает старого друга у маяка.'
        else:
            yield json.dumps(fixture(),ensure_ascii=False)
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        scenario=client.post(path+'/generate',json={'revision':workspace['revision'],'kind':'idea','text':'История у маяка','config':REMOTE,'api_key':'test'})
        assert scenario.status_code==200,scenario.text
        assert wait_job(client,scenario.json()['id'])['status']=='saved'
        current=client.get(path).json()
        assert current['idea'].startswith('# Сценарий')
        generated=client.post(path+'/draft/generate',json={'revision':current['revision'],'task':'world','text':'','use_idea':True,'config':REMOTE,'api_key':'test'})
        assert generated.status_code==200,generated.text
        assert wait_job(client,generated.json()['id'])['status']=='saved'
    assert len(calls)==2
    assert current['idea'] in calls[1][-1]['content']
    with app.state.repository.connect() as db:
        stages=[row[0] for row in db.execute('SELECT stage FROM llm_requests ORDER BY created_at,id')]
    assert sorted(stages)==['draft_world','idea']


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
        captured.extend(kwargs['messages']);yield '{"value":"Говорит коротко, с сухими шутками."}'
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        r=client.post(path+'/generate',json={'revision':d['revision'],'task':'field','kind':'character','entity_id':cid,'field':'fields.Стиль общения','text':'Дай персонажу узнаваемый голос','config':REMOTE,'api_key':'test'})
        assert r.status_code==200,r.text
        assert wait_job(client,r.json()['id'])['status']=='saved'
    after=client.get(path+'?author=true').json()['state']
    assert after['world']==before['world']
    assert after['characters'][0]['fields']['Стиль общения']=='Говорит коротко, с сухими шутками.'
    assert after['characters'][0]['fields']['Внешность']==before['characters'][0]['fields']['Внешность']
    assert 'узнаваемый голос' in str(captured)
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
    world['characters'][0]['fields']['Характер']='Привык скрывать усталость за короткими шутками; во время сложного дежурства спокойнее всех.'
    world['characters'][1]['fields']['Характер']='Прямая и внимательная начальница: шутит с Ильёй, но строго разделяет работу и дружбу.'
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
        yield json.dumps(world,ensure_ascii=False)
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        j=client.post(f"/api/workspaces/{workspace['id']}/draft/generate",json={'revision':workspace['revision'],'task':'world','text':original,'config':REMOTE,'api_key':'fixture'}).json()
        assert wait_job(client,j['id'])['status']=='saved'
    assert 'придумай самостоятельно' in messages[0]['content']
    assert any(original in m['content'] for m in messages)
    draft=client.get(f"/api/workspaces/{workspace['id']}/draft?author=true").json()
    result=draft['state'];assert not draft['validation']['errors']
    assert result['world']['relationships'][a+':'+b]['context']!=result['world']['relationships'][b+':'+a]['context']
    assert 'заботится' in result['world']['relationships'][b+':'+a]['context']
    assert {v['actor_id'] for v in result['world']['knowledge'].values() if v['fact_id']=='meeting'}=={c,d}
    assert a not in {v['actor_id'] for v in result['world']['knowledge'].values() if v['fact_id']=='meeting'}
    assert result['world_clock']['minute']==5160
    assert 'Прямая' in result['characters'][1]['fields']['Характер']
    assert result['campaign']['public_description'] != result['campaign']['description']
    assert 'Тайная встреча' not in json.dumps(client.get(f"/api/workspaces/{workspace['id']}/draft").json()['state'],ensure_ascii=False)


def test_quick_generation_creative_completion_is_playable_and_one_request(api):
    from unittest.mock import patch
    client,app=api
    w=client.post('/api/workspaces',json={'name':'Клиника'}).json()
    idea=('Илья Волков, 27, диагност и руководитель команды. Люда Воронина, 30, главврач. '
          'Тимур Савельев, 24, талантливый, но ленивый терапевт. Соня Орлова, 25, бывшая Тимура. '
          'Катя Соболева, 24, кардиолог, Илья часто с ней обедает. '
          'Четверг, 14:00: у Ильи день рождения, он в морге проводит вскрытие.')
    state=fixture();state['characters']=state['characters'][:5]
    ids=[c['id'] for c in state['characters']];a,b,c,d,e=ids
    names=['Илья Волков','Люда Воронина','Тимур Савельев','Соня Орлова','Катя Соболева']
    for card,name in zip(state['characters'],names):
        card.update(name=name,fields={'Возраст':{'Илья Волков':'27 лет','Люда Воронина':'30 лет','Тимур Савельев':'24 года','Соня Орлова':'25 лет','Катя Соболева':'24 года'}[name],
            'Роль':{'Илья Волков':'Врач-диагност, руководитель команды','Люда Воронина':'Главврач клиники',
                    'Тимур Савельев':'Терапевт','Соня Орлова':'Менеджер','Катя Соболева':'Кардиолог'}[name],
            'Статус':'Работает в клинике и отвечает за свою часть ежедневного дежурства.',
            'Внешность':'Привычный рабочий образ, движения и мимика различимы даже после длинного дежурства.',
            'Характер':f'{name} ведёт себя узнаваемо: сочетает компетентность с личными привычками и противоречиями, которые влияют на повседневное общение.',
            'Биография':f'{name} давно работает рядом с коллегами; рабочий опыт и недавние разговоры объясняют его нынешнее поведение.'})
    # These details were not present in the short user idea. The generated
    # aggregate must retain creative content, not merely the named roles.
    details=[
        ('Вечно сбитая прядь и потёртые перчатки; по ночам он забывает снять очки после смены.',
         'Говорит обрывисто и замечает мелочи в чужой речи. Боится подвести команду и потому плохо делегирует.',
         'Несколько лет назад он пропустил редкий симптом в учебной практике. Люда тогда защищала его перед комиссией, но он до сих пор берёт сложные случаи лично.'),
        ('Седая прядь у виска и выцветший халат с аккуратно заштопанным карманом.',
         'Говорит мягко, пока речь не заходит о риске для пациентов. Хочет доверять команде, но слишком хорошо помнит цену поспешных решений.',
         'До назначения главврачом она работала с Ильёй в ночных сменах. После тяжёлой смены изменила порядок дежурств и до сих пор спорит с ним о самостоятельности команды.'),
        ('Неровно застёгнутый халат и чернильное пятно на пальце; он неизменно рисует схемы на салфетках.',
         'Отшучивается вместо извинений, хотя первым замечает ухудшение пациента. Опоздания скрывают страх не справиться с новой должностью.',
         'Тимур однажды вытащил сложный случай, когда команда уже сдалась. После разрыва с Соней всё чаще ночует у знакомых и не успевает к началу смены.'),
        ('Короткая стрижка и заметное кольцо на цепочке; всегда ровно раскладывает документы.',
         'Спокойно разговаривает с больными, а с бывшим партнёром теряет терпение. Ей трудно признаться в том, что она по-прежнему следит за его успехами.',
         'Соня устраивала первую совместную благотворительную акцию отделения. После разрыва с Тимуром осталась работать здесь, потому что клиника стала её собственным делом.'),
        ('Веснушки и старая брошь в виде компаса; машинально считает удары пульса.',
         'Легко поддевает Илью за обедом, но тщательно скрывает усталость. Хочет сменить график, не признаваясь коллегам, что дома на ней держится семья.',
         'Катя вернулась в город ради матери и взяла больше ночных смен, чем может выдержать. С Ильёй подружилась после спорного диагноза, который они решали вместе.'),
    ]
    for card,(appearance,character,biography) in zip(state['characters'],details):
        card['fields'].update(Внешность=appearance,Характер=character,Биография=biography,
            **{'Стиль общения':f'{card["name"]} говорит короткими точными фразами и редко повышает голос. С близкими позволяет себе сухие шутки, при начальстве отвечает прямо и формально.',
               'Привычки':f'{card["name"]} перед разговором поправляет рукав халата и делает короткую паузу, прежде чем назвать диагноз. После тяжёлой смены записывает наблюдения в бумажный блокнот.',
               'Сильные стороны':f'{card["name"]} умеет быстро выделять важный симптом и сохранять спокойствие, когда коллеги спорят. Сверяет риск с реальными последствиями для пациента.',
               'Слабости':f'{card["name"]} болезненно принимает публичные замечания и начинает проверять чужую работу вместо того, чтобы попросить помощи. Из-за этого задерживается допоздна.',
               'Страхи и уязвимости':f'{card["name"]} боится потерять доверие команды после ошибки и избегает разговоров о давнем провале. При намёке на него слишком быстро закрывается.'})
    world=state['world'];world['characters']={i:world['characters'][i] for i in ids}
    for i,item in world['characters'].items():
        item.update(goals=['Разобраться с текущей рабочей задачей'] if i!=a else ['Завершить сегодняшнее дежурство'],
                    intentions=['Поговорить с нужным коллегой после смены'] if i!=a else [],minute=5160,
                    situation='Занят делами клиники',scene_id=None)
    npc_goals={b:'Перераспределить ночные смены без срыва работы отделения',
               c:'Доказать Илье, что способен вести сложный случай самостоятельно',
               d:'Решить, подавать ли заявление об уходе после благотворительной акции',
               e:'Согласовать новый график, чтобы ухаживать за матерью'}
    npc_intentions={b:'После планёрки спросить Илью, почему он снова остался сверхурочно',
                    c:'Принести собственные записи по пациенту до разговора с Ильёй',
                    d:'Сначала выяснить, кто возьмёт на себя организацию акции',
                    e:'За обедом осторожно узнать, кто сможет взять её ночную смену'}
    for cid in npc_goals:
        world['characters'][cid].update(goals=[npc_goals[cid]],intentions=[npc_intentions[cid]])
    world['characters'][a].update(location='Морг клиники',situation='Проводит вскрытие',scene_id=state['camera']['scene_id'])
    world['relationships']={
        'ab':{'source_id':a,'target_id':b,'context':'Илья доверяет Люде как начальнице, но спорит о нагрузке на команду.','dimensions':{'respect':65}},
        'ba':{'source_id':b,'target_id':a,'context':'Люда ценит Илью как диагноста, хотя считает его слишком упрямым.','dimensions':{'trust':55}},
        'ac':{'source_id':a,'target_id':c,'context':'Илья уважает талант Тимура, но раздражён его опозданиями.','dimensions':{'respect':50,'irritation':45}},
        'ca':{'source_id':c,'target_id':a,'context':'Тимур уважает Илью, хотя устал от постоянного контроля.','dimensions':{'respect':40}},
        'ae':{'source_id':a,'target_id':e,'context':'Илья с удовольствием обедает с Катей и доверяет её работе.','dimensions':{'trust':60}},
        'ea':{'source_id':e,'target_id':a,'context':'Катя ценит прямоту Ильи и часто поддерживает его в сложную смену.','dimensions':{'respect':50}},
        'dc':{'source_id':d,'target_id':c,'context':'Соня избегает Тимура после их прежнего разрыва.','dimensions':{'trust':-40}}}
    world['facts']={'birthday':{'id':'birthday','text':'Сегодня день рождения Ильи','secret':False,'character_ids':[a],'evidence':[]},
                    'cheat':{'id':'cheat','text':'Тимур изменял Соне','secret':True,'character_ids':[c,d],'evidence':[]}}
    world['knowledge']={'d:cheat':{'actor_id':d,'fact_id':'cheat','status':'known','source_event_id':None}}
    private_details=[
        'Илья скрыл от комиссии, что заметил редкий симптом уже после выписки пациента.',
        'Люда сохранила письмо предыдущего главврача с предупреждением о неучтённых переработках.',
        'Тимур отказался от предложения работать в другом городе, не рассказав об этом Соне.',
        'Соня хранит черновик заявления об уходе, который так и не передала Люде.',
        'Катя оплатила лечение матери из денег, отложенных на собственное обучение.',
    ]
    for cid,private_text in zip(ids,private_details):
        fid='private_'+cid
        world['facts'][fid]={'id':fid,'text':private_text,
                             'secret':True,'character_ids':[cid],'evidence':[]}
        world['knowledge'][cid+':'+fid]={'actor_id':cid,'fact_id':fid,'status':'known','source_event_id':None}
    world['threads']={
        'work':{'id':'work','description':'Талант Тимура и его опоздания осложняют работу диагностической команды.',
                'state':'Илья пока продолжает доверять его работе.','public_state':'Илья пока продолжает доверять его работе.',
                'status':'active','character_ids':[a,c],'visible_to_ids':[a],'relevance':.7,'last_event_id':None},
        'past':{'id':'past','description':'Разрыв Сони и Тимура пока не обсуждался с остальными.',
                'state':'Соня избегает Тимура.','status':'dormant','character_ids':[c,d],'relevance':.4,'last_event_id':None}}
    scene=world['scenes'][state['camera']['scene_id']]
    scene.update(location='Морг клиники',participants=[a],text='Илья проводит вскрытие. Сегодня у него день рождения.',start_minute=5160,end_minute=5160)
    state['locations']=[{'id':'morgue','name':'Морг клиники','text':'Место сегодняшнего дежурства.'}]
    state['world_clock']={'minute':5160,'last_event_time':'День 4 (Чт) 14:00'}
    state['campaign'].update(title='Клиника',setting='Городская клиника',public_description='История о коллегах и дежурстве.')
    state=domain.prepare(state)
    assert not domain.validate(state)['errors']
    assert not domain.review_initial(state)
    calls=[]
    def stream(**kwargs):
        calls.append(kwargs['messages'])
        yield json.dumps(state,ensure_ascii=False)
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        job=client.post(f"/api/workspaces/{w['id']}/draft/generate",json={'revision':w['revision'],'task':'world','text':idea,'config':REMOTE,'api_key':'fixture'})
        assert job.status_code==200,job.text
        assert wait_job(client,job.json()['id'])['status']=='saved'
    assert len(calls)==1 and idea in calls[0][-1]['content']
    assert 'Ты автор полноценного живого RPG-мира' in calls[0][0]['content']
    draft=client.get(f"/api/workspaces/{w['id']}/draft?author=true").json()
    assert not draft['validation']['errors'] and not draft['validation']['warnings']
    assert len(draft['state']['characters'])==5 and len(draft['state']['world']['relationships'])==7
    assert 'редкий симптом' in draft['state']['characters'][0]['fields']['Биография']
    assert all(all(draft['state']['characters'][i]['fields'][key] for key in CARD_FIELDS) for i in range(5))
    assert len({draft['state']['world']['facts']['private_'+cid]['text'] for cid in ids})==5
    assert {tuple(draft['state']['world']['characters'][cid]['goals']) for cid in npc_goals}=={(goal,) for goal in npc_goals.values()}
    assert draft['state']['world']['threads']['work']['visible_to_ids']==[a]
    assert 'cheat' not in client.get(f"/api/workspaces/{w['id']}/draft").json()['state']['world']['facts']
    confirmed=client.post(f"/api/workspaces/{w['id']}/draft/confirm",json={'revision':draft['revision'],'version_id':draft['version_id']})
    assert confirmed.status_code==200,confirmed.text
    assert client.get(f"/api/saves/{confirmed.json()['save']}").json()['state']['world_clock']['minute']==5160
    with app.state.repository.connect() as db:
        assert [row[0] for row in db.execute('SELECT stage FROM llm_requests')]==['draft_world']


def test_generation_review_is_advisory_and_import_is_unchanged(api):
    client,_=api
    sparse=fixture();sparse['world']['relationships']={};sparse['world']['threads']={};sparse['campaign']['title']='Готовая выжимка';sparse=domain.prepare(sparse)
    assert any('отношения' in note for note in domain.review_initial(sparse))
    assert any('сюжетных линий' in note for note in domain.review_initial(sparse))
    w=client.post('/api/workspaces',json={'name':'Готовая выжимка'}).json()
    imported=client.post(f"/api/workspaces/{w['id']}/draft/import",json={'revision':w['revision'],'text':domain.export_markdown(sparse)})
    assert imported.status_code==200,imported.text
    assert imported.json()['state']==domain.player_view(sparse)
    assert not imported.json()['validation']['warnings']


def test_sparse_but_structurally_valid_world_saves_without_completion(api):
    from unittest.mock import patch
    client,app=api;path,previous=make(client)
    state=fixture();state['world']['relationships']={};state['world']['threads']={}
    calls=[]
    def stream(**kwargs):
        calls.append(kwargs);yield json.dumps(state,ensure_ascii=False)
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        job=client.post(path+'/generate',json={'revision':previous['revision'],'task':'world',
            'text':'Мир у маяка','config':REMOTE,'api_key':'fixture'})
        assert wait_job(client,job.json()['id'])['status']=='saved'
    after=client.get(path+'?author=true').json()
    assert len(calls)==1 and after['validation']['warnings']
    assert after['state']['world']['threads']=={} and after['state']['world']['relationships']=={}
    with app.state.repository.connect() as db:
        assert [r[0] for r in db.execute('SELECT stage FROM llm_requests')]==['draft_world']


def test_shared_secret_does_not_count_as_every_characters_personal_secret():
    state=fixture();b,c=[card['id'] for card in state['characters'][1:3]]
    state['world']['knowledge'][c+':meeting']['status']='known'
    assert b not in domain.secret_holders(state) and c not in domain.secret_holders(state)
    state['world']['facts']['meeting']['owner_id']=b
    assert domain.secret_holders(state)=={b}


def test_json_continuation_keeps_json_format():
    from backend.services.continuation import request_context
    messages=[{'role':'system','content':'Отвечай JSON'}]
    result,_=request_context(messages,'{"world":',32768,500,format_hint='json')
    assert 'JSON-объект' in result[-1]['content'] and 'Markdown' in result[-1]['content']
    assert 'Продолжи документ' not in result[-1]['content']
