"""Six fresh API workspaces with explicitly controlled world/review/gameplay.

These are integration fixtures, not measurements of DeepSeek generation quality.
No candidate_snapshot is imported into these new jobs.
"""
import json
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import pytest
from test_initial_draft_v4 import rich,api,REMOTE,wait_job
from backend.services import draft_completeness as review
from backend.repositories.preparation import Repository
from backend.runtime_v3.calendar import age_on,current_time

SCENARIOS=json.loads((Path(__file__).parent/'fixtures/generation_scenarios/inputs_final.json').read_text())

def controlled_world(scenario):
    s=rich();world=s['world'];ids=[c['id'] for c in s['characters']]
    names={
        'e4_new':['Илья Волков','Марина Волкова','Тимур Волков','Соня Величкина','Катя Соколова','Юра Яковлев','Сергей Волков','Алексей Волков'],
        'daily':['Нина','Олег'], 'historical':['Мирек','Яна'], 'fantasy':['Элин','Тар'],
        'adoption':['Ася','Павел','Рада'], 'organizations':['Лада','Борис']}[scenario['id']]
    s['campaign'].update(description=scenario['idea'],era=scenario['start']['date'][:4])
    for index,card in enumerate(s['characters']):
        card['name']=names[index] if index<len(names) else 'Житель '+str(index)
        card['aliases']=[]
        card['fields']={'Возраст':str([25,46,26,25,25,25,54,30][index] if scenario['id']=='e4_new' else 24+index),
            'Роль':'Житель города','Статус':'Свободен','Внешность':'Тёмные волосы, серые глаза, рабочая одежда.',
            'Характер':'Терпелив в работе, раздражается при пустых обещаниях.',
            'Стиль общения':'Короткие фразы, задаёт прямые вопросы.', 'Привычки':'Перечитывает записки перед встречей.',
            'Сильные стороны':'Помнит подробности разговора.','Слабости':'Трудно просит помощи.',
            'Страхи и уязвимости':'Боится подвести семью.','Биография':'Помогает соседям чинить вещи, хранит письма семьи.'}
    if scenario['id']=='e4_new':
        starts=sorted(scenario['idea'].index(name) for name in names)+[scenario['idea'].index('Сейчас ')]
        for card in s['characters']:
            start=scenario['idea'].index(card['name']);end=next(n for n in starts if n>start)
            card['fields']['Биография']=scenario['idea'][start:end].strip()
            card['fields']['Характер']=card['fields']['Биография']
        s['characters'][0]['fields']['Внешность']='Тёмные волосы, жилистое тело, зелёные глаза.'
        s['characters'][3]['fields']['Внешность']='Светлые волосы с двумя косичками, маленькая девушка.'
    for section in world:
        if isinstance(world[section],dict) and section not in ('characters','scenes'):world[section]={}
    for cid,actor in world['characters'].items():
        actor.update(goals=[] if cid==s['controlled_actor_id'] else ['Закончить текущую работу'],short_goal='',intentions=[],obligations=[],emotion='',birth_date=None,location='square')
        actor.pop('birth_provenance',None)
    place='Вокзал' if scenario['id']=='e4_new' else 'Городская площадь'
    s['locations']=[dict(id='square',name=place,text='Место встречи.',kind='place')]
    scene=world['scenes'][s['camera']['scene_id']]
    scene.update(location='square',participants=ids[:3],event_ids=[],text='Персонажи встретились и ждут начала разговора.')
    world['scenes']={scene['id']:scene}
    s['world_clock']={'minute':0,'calendar':{'start_date':scenario['start']['date'],'start_minute':0,'start_weekday':0,'profile':scenario['start'].get('profile',{})}}
    scene.update(start_minute=0,end_minute=0)
    world['facts']={'keepsake':dict(id='keepsake',text='Письмо хранится у второго участника.',secret=True,character_ids=[ids[1]])}
    world['knowledge']={'knows':dict(actor_id=ids[1],fact_id='keepsake',status='known'),'suspects':dict(actor_id=ids[2],fact_id='keepsake',status='suspected')}
    world['relationships']={'out':dict(source_id=ids[0],target_id=ids[2],context='Давнее знакомство',dimensions={'affection':20}),'back':dict(source_id=ids[2],target_id=ids[0],context='Дорожит дружбой',dimensions={'affection':70})}
    if scenario['id']=='e4_new':
        scene.update(participants=[ids[0],ids[4]],text=scenario['idea'].split('Сейчас ',1)[1])
        for parent in (1,6):
            for child in (0,7):
                key=f'parent_{parent}_{child}'
                world['objective_relations'][key]=dict(id=key,source_id=ids[parent],target_id=ids[child],kind='parent')
        world['objective_relations']['brothers']=dict(id='brothers',source_id=ids[0],target_id=ids[7],kind='sibling')
        world['relationships']={'out':dict(source_id=ids[0],target_id=ids[4],context='Близки с детства',dimensions={'attraction':40}),'back':dict(source_id=ids[4],target_id=ids[0],context='Илья для неё целый мир',dimensions={'attraction':85})}
        world['facts']={'injury':dict(id='injury',text='Илья был ранен левее сердца во второй год войны и после лазарета вернулся на фронт.',secret=False,character_ids=[ids[0]]),'father':dict(id='father',text='Сергей недолюбливает Илью; Илья об этом знает.',secret=False,character_ids=[ids[0],ids[6]])}
        world['knowledge']={'self':dict(actor_id=ids[0],fact_id='injury',status='known'),'father_known':dict(actor_id=ids[0],fact_id='father',status='known')}
        world['possessions']={'rifle':dict(id='rifle',name='Винтовка',kind='weapon',owner_id=ids[0],holder_id=ids[0]),'pack':dict(id='pack',name='Рюкзак с вещами и трофеями',kind='bag',owner_id=ids[0],holder_id=ids[0])}
    if scenario['id']=='adoption':
        world['objective_relations']={'adopted':dict(id='adopted',source_id=ids[1],target_id=ids[0],kind='adoptive_parent')}
        world['facts']['adopted']=dict(id='adopted',text='Павел усыновил Асю.',secret=True,character_ids=ids[:2])
        world['knowledge'].update({'father':dict(actor_id=ids[1],fact_id='adopted',status='known'),'friend':dict(actor_id=ids[2],fact_id='adopted',status='suspected')})
    if scenario['id']=='organizations':
        world['organizations']={'union':dict(id='union',name='Союз перевозчиков'),'workshop':dict(id='workshop',name='Мастерская')}
        world['scheduled_events']={
            'unknown':dict(id='unknown',description='Осмотр груза',participants=[ids[1]],due_minute=None,status='pending'),
            'meeting':dict(id='meeting',description='Обсудить результат осмотра',participants=[ids[1]],due_minute=None,status='pending',commitment=True,depends_on=['unknown'],temporal={'day_offset':1,'time':'10:00'},end_temporal={'day_offset':1,'time':'11:00'},time_reference_minute=600,location_id='square')}
    return s

@pytest.mark.parametrize('scenario',SCENARIOS,ids=lambda s:s['id'])
def test_fresh_generation_editor_start_turn_reload(api,scenario):
    client,app=api;repo=app.state.repository
    wid=client.post('/api/workspaces',json={'name':scenario['id']}).json()['id'];url=f'/api/workspaces/{wid}/draft'
    generated=controlled_world(scenario);calls=[];review_calls=0
    def stream(**kw):
        nonlocal review_calls
        calls.append(kw)
        if kw['messages'][0]['content'].startswith(review.MARKER):
            review_calls+=1
            payload=json.loads(kw['messages'][1]['content'])
            if payload.get('strategy')=='scoped_reaudit':
                yield json.dumps({'resolutions':[dict(issue_id=p['issue_id'],resolution='disproved',reason='Коллекция существует; структурированное отсутствие конкретной записи не установлено. Неизвестное жильё допустимо.',basis=[dict(path='/world/residences')]) for p in payload['pending_issues']]})
            elif review_calls<=2:
                yield json.dumps({'issues':[dict(path='/world/residences',assertion='missing_reference',message='Recorded malformed collection claim',patch_paths=['/world/residences'])]})
            else:yield '{"issues":[]}'
        else:
            assert len(calls)==1
            assert scenario['idea'] in kw['messages'][1]['content']
            yield json.dumps(generated,ensure_ascii=False)
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        response=client.post(url+'/generate',json={'revision':0,'text':scenario['idea'],'creation_settings':{'calendar_start':scenario['start']},'config':dict(REMOTE,context_length=262144),'api_key':'offline'})
        assert response.status_code==200,response.text
        jid=response.json()['id'];job=wait_job(client,jid);assert job['status']=='saved',job
        d=client.get(url+'?author=true').json()
        assert d['state']['world']['residences']=={}
        d=client.patch(url,json={'revision':d['revision'],'operation':'patch','kind':'campaign','field':'title','value':'Автор: '+scenario['id']}).json()
        assert client.post(url+'/resume',json={'revision':d['revision'],'api_key':'offline'}).status_code==200
        assert wait_job(client,jid)['status']=='saved'
    d=client.get(url+'?author=true').json()
    confirmed=client.post(url+'/confirm',json={'revision':d['revision'],'version_id':d['version_id']})
    assert confirmed.status_code==200,confirmed.text
    sid=confirmed.json()['save'];before=repo.get_snapshot(sid);w=before['world_state']
    assert before['campaign']['campaign']['title']=='Автор: '+scenario['id']
    assert w['meta']['calendar']['start_date']==scenario['start']['date']
    assert w['relationships'] and w['knowledge'] and w['facts']
    assert scenario['idea']==before['campaign']['campaign']['description']
    if scenario['id']=='e4_new':
        assert [c['name'] for c in d['state']['characters']]==[c['name'] for c in generated['characters']]
        assert all(c['fields']['Биография']==g['fields']['Биография'] for c,g in zip(d['state']['characters'],generated['characters']))
        pc=generated['controlled_actor_id'];assert not w['characters'][pc]['intentions']
    if scenario['id']=='adoption':
        pc=generated['controlled_actor_id'];assert pc+':adopted' not in w['knowledge']
    for card in d['state']['characters']:
        assert age_on(w['characters'][card['id']]['birth_date'],scenario['start']['date'],w['meta']['calendar']['profile'])==int(card['fields']['Возраст'])
    if scenario['id']=='fantasy':
        future=deepcopy(w);future['meta']['world_time']+=20
        assert current_time(future)['date']=='0413-01-01'
    if scenario['id']=='organizations':
        assert w['scheduled_events']['unknown']['due_minute'] is None
        assert w['scheduled_events']['meeting']['depends_on']==['unknown']
        assert w['scheduled_events']['meeting']['end_temporal']['time']=='11:00'
        assert w['scheduled_events']['meeting']['location_id']=='square'
    from test_runtime_v3_engine import run as play,raw_for
    from test_engine import CONFIG
    for kind in ('start','turn','turn'):
        snapshot=repo.get_snapshot(sid)
        turn=repo.begin_job(sid,'Осматриваюсь.' if kind=='turn' else '',kind,CONFIG)
        play(repo,turn,raw_for(snapshot))
        assert repo.get_job(turn)['status']=='saved'
        repo=Repository(repo.path)
    after=repo.get_snapshot(sid)
    for section in ('relationships','knowledge','facts','objective_relations','possessions'):
        assert after['world_state'][section]==w[section]
    assert after['campaign']['campaign']['title']==before['campaign']['campaign']['title']
    assert Repository(repo.path).get_snapshot(sid)==after
