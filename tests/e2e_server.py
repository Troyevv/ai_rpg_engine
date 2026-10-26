"""Browser-only fixture server. Never imported by the production application."""
from hashlib import sha256
from canonical_fixture import canonical
import json
import re
import os
os.environ["TABLETOP_DEBUG"] = "1"
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import engine
import llm
import backend.services.preparation as preparation
from backend.api.app import create_app
from test_worlds import summary
from test_engine import result
from test_pov_documents import background, SECRET
import uvicorn

NARRATIVE = '''Персонаж 1 подвигает свободный стул. «Садись, поговорим».

За окном медленно гаснет вечерний свет. На кухне пахнет свежим кофе, и кто-то оставил на столе раскрытую книгу. Персонаж 2 убирает телефон в карман и смотрит на собравшихся.

— Ну что, — говорит он, чуть улыбаясь, — рассказывай. Мы ведь не просто так здесь собрались?

Он ставит перед тобой тёплую чашку и отодвигает сахарницу. В соседней комнате затихает музыка. Несколько секунд никто не торопит разговор — только чайник щёлкает, остывая у окна.
'''


def runtime_v3_request(messages):
    """Dispatch the fixture by schema, not by mutable prompt wording."""
    for message in messages:
        if message['content'].startswith('JSON Schema\n'):
            schema=json.loads(message['content'].split('\n',1)[1])
            return 'final_scene' in schema.get('properties', {})
    # Exact old prompt snapshots remain playable during regeneration tests.
    return any('RawTurnResult v3' in message['content'] for message in messages)


review_protocol_attempts={}
fragment_attempts={}

def stream(**kwargs):
    from backend.services.draft_completeness import MARKER
    if kwargs['messages'][0]['content'].startswith(MARKER):
        request=json.loads(kwargs['messages'][1]['content'])
        source=request.get('author_context','')
        from draft_provider_fixture import protocol_review
        controlled=protocol_review(request)
        if controlled is not None:
            yield controlled;return
        yield '{"issues":[]}'
        return
    full='\n'.join(m['content'] for m in kwargs['messages'])
    if kwargs['messages'][0]['content'].startswith('Один необязательный пакет') and 'TEST_RELEASE_QUALITY' in full:
        yield '{"patches":[],"preserved_unknown":null}';return
    observer='Тип хода: background' in full or 'Режим observer:' in full or 'mode=observer' in full
    if kwargs['messages'][0]['content'].startswith('Select at most ONE optional grounded autonomous remote action.'):
        yield '{"action":null}'
        return
    current_message=next((m['content'] for m in kwargs['messages'] if m['content'].startswith('Текущее состояние / GM-only\n')),None)
    current_phone=json.loads(current_message.split('\n',1)[1]) if current_message else {}
    if current_phone.get('communication'):
        camera=current_phone['camera']
        if kwargs.get('response_format'):
            yield json.dumps(dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids'],elapsed_minutes=0),choices=[dict(action='Посмотреть в окно',speech='')]),ensure_ascii=False)
        else: yield 'В комнате тихо. За окном шелестят листья.'
        return
    if 'qa_meeting' in full:
        current=json.loads(next(m['content'] for m in kwargs['messages'] if m['content'].startswith('Текущее состояние / GM-only\n')).split('\n',1)[1])
        task=json.loads(next(m['content'] for m in kwargs['messages'] if m['content'].startswith('Текущий ввод\n')).split('\n',1)[1])
        depart=task['player_input']=='Разойтись.'
        alone='qa_vera' not in current['camera']['present_character_ids']
        text='Илья и Соня попрощались и разошлись.' if depart else 'Илья смотрит на улицу.' if alone else 'Илья и Соня встретились в «Гвозде» и поговорили.'
        if kwargs.get('response_format'):
            camera=current['camera']
            payload=dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=['qa_kirill'] if depart else camera['present_character_ids'],elapsed_minutes=1),
                events=[dict(id='meeting',text=text,evidence=text,participants=['qa_kirill','qa_vera'] if not alone else ['qa_kirill'],witnesses=['qa_kirill','qa_vera'] if not alone else ['qa_kirill'],medium='conversation')],
                choices=[dict(action='Посмотреть вокруг',speech='',kind='decision',basis_ids=['qa_meeting']),dict(action='Осмотреться',speech='',kind='decision',basis_ids=['qa_meeting'])])
            if not alone:payload['scene_transitions']=[dict(source_event_id='meeting',phase='ended' if depart else 'started',actor_ids=['qa_kirill','qa_vera'],thread_ids=['qa_meeting'],evidence=text)]
            value=json.dumps(payload,ensure_ascii=False)
        else:value=text
    elif 'провести вечер вдвоём' in full and 'qa_vera' in full:
        current=json.loads(next(m['content'] for m in kwargs['messages'] if m['content'].startswith('Текущее состояние / GM-only\n')).split('\n',1)[1])
        task=json.loads(next(m['content'] for m in kwargs['messages'] if m['content'].startswith('Текущий ввод\n')).split('\n',1)[1])
        refused='Нет, сегодня не хочу.' in task['player_input']
        text='Вера кивает и заканчивает разговор: «Хорошо, тогда в другой раз».' if refused else 'Вера протягивает ладонь: «Побудем вечером вдвоём?» — и ждёт ответа.'
        if kwargs.get('response_format'):
            camera=current['camera'];external=camera['controlled_actor_id']
            payload=dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids'],elapsed_minutes=1),
                events=[dict(id='initiative',text=text,evidence=text,participants=['qa_vera','qa_kirill'],witnesses=camera['present_character_ids'],medium='conversation')],
                scene_actions=[dict(actor_id='qa_vera',target_ids=['qa_kirill'],source_event_id='initiative',phase='end' if refused else 'offer',modality='speech',adult=True,interruptible=not refused,response='player_supplied' if refused else 'open',player_evidence=task['player_input'] if refused else '',evidence=text)],
                choices=[dict(action='Отказаться',speech='Нет, сегодня не хочу.')])
            if refused:
                # A player refusal answers this invitation, not every open beat.
                pending=current.get('continuity', {}).get('pending_response_ids', [])
                assert len(pending)==1, pending
                payload['scene_actions'][0]['response_event_id']=pending[0]
            value=json.dumps(payload,ensure_ascii=False)
        else: value=text
    elif 'Ты редактор черновика Character' in full:
        task=json.loads(kwargs['messages'][-1]['content'])
        value='Новая сцена у двери.'
        if task['path']=='whole_draft':
            value=task['draft'];value['card']['name']='Сгенерированная героиня'
            value['character']['location_id']=task['context']['locations'][0]['id']
            value['starting_scene']='У входа в дом.'
        value=json.dumps({'value':value},ensure_ascii=False)
    elif 'TEST_CANDIDATE_RECOVERY' in full and 'patches' in kwargs['messages'][0]['content']:
        value='{"patches":[]}'
    elif 'Каноническая JSON Schema WorldState' in full:
        from test_draft_world import fixture
        candidate=fixture()
        if 'TEST_MOTIVATION_OBJECTS' in full:
            from test_draft_motivations import motivated
            candidate,_=motivated()
        for card in candidate['characters']:
            for field,text in {'Характер':'Спокоен, внимателен к деталям.','Сильные стороны':'Помнит детали разговора.','Слабости':'Неохотно просит о помощи.','Биография':'Давно живёт в районе и знает соседей.','Внешность':'Короткие волосы, серая куртка.','Стиль общения':'Говорит короткими фразами, уточняет детали.','Привычки':'Записывает договорённости в блокнот.'}.items():
                if card.get('fields',{}).get(field,'').strip().lower() in ('','неизвестно','не указано','—'):card['fields'][field]=text
        if 'TEST_RELEASE_QUALITY' in full:candidate['characters'][1]['fields']['Внешность']='неизвестно'
        if 'TEST_CANDIDATE_RECOVERY' in full:candidate['protagonist_id']='missing'
        value=json.dumps(candidate,ensure_ascii=False)
        if 'TEST_FRAGMENT_RECOVERY' in full:
            key=kwargs['messages'][1]['content'];count=fragment_attempts.get(key,0);fragment_attempts[key]=count+1
            cut=value.index('"world":')+len('"world":')
            if count<2:
                from llm import OutputLimitReached
                yield value[:cut] if count==0 else 'INVALID CONTINUATION'
                if kwargs.get('on_finish'):kwargs['on_finish']('length')
                raise OutputLimitReached()
            value=value[cut:]
        if 'TEST_JSON_CONTINUATION' in full:
            cut=len(value)//2
            if not any(m['role']=='assistant' for m in kwargs['messages']):
                from llm import OutputLimitReached
                yield value[:cut]
                if kwargs.get('on_finish'):kwargs['on_finish']('length')
                raise OutputLimitReached()
            value=value[cut:]
    elif 'Ты редактор RPG' in full:
        value=json.dumps({'value':'Обновлённая внешность'},ensure_ascii=False)
    elif kwargs.get('response_format') and runtime_v3_request(kwargs['messages']):
        block=next(m['content'] for m in kwargs['messages'] if m['content'].startswith('Текущее состояние / GM-only'))
        state=json.loads(block.split('\n',1)[1]);camera=state['camera']
        observer=camera['mode']=='observer'
        task=json.loads(next(m['content'] for m in kwargs['messages'] if m['content'].startswith('Текущий ввод')).split('\n',1)[1])
        present=camera['present_character_ids']
        location_id=camera['location_id'];locations=[]
        if task['kind']=='start' or (observer and location_id is None):
            from backend.runtime_v3.models import identity
            place='Подвал' if observer else 'Кухня'
            location_id=identity('location',place.casefold())
            present=['character_3','character_4'] if observer and 'character_3' in present else present if observer else ['character_1','character_2']
            if location_id not in state['locations']:locations=[dict(id=location_id,name=place,evidence=SECRET if observer else NARRATIVE)]
        payload=dict(locations=locations,final_scene=dict(location_id=location_id,
            present_character_ids=present,situation='Тайная встреча.' if observer else 'Разговор на кухне.',elapsed_minutes=1),
            choices=[] if observer else [dict(action='Действие '+str(i),speech='Реплика '+str(i)) for i in range(6)])
        evidence=SECRET if observer else 'Садись, поговорим'
        fid='key_'+sha256(full.encode()).hexdigest()[:12]
        payload['events']=[dict(id='event',text='Передача ключа.' if observer else 'Собеседник предложил поговорить.',
            participants=present,witnesses=present,fact_ids=[fid] if observer else [],medium='conversation',evidence=evidence)]
        if observer:
            payload['facts']=[dict(id=fid,text='Тайный ключ передан.',character_ids=present,evidence=evidence)]
            payload['knowledge_gained']=[dict(actor_id=cid,fact_id=fid,source_event_id='event',evidence=evidence) for cid in present]
        value=json.dumps(payload,ensure_ascii=False)
    elif kwargs.get('response_format'):
        payload=background() if observer else result()
        match=re.search(r'Единое время мира: (День \d+(?: \([А-Яа-я]+\))? \d{2}:\d{2})',full)
        if match and match[1]!='День 1 00:00':payload['scene']['time']=match[1]
        if 'pov' in kwargs['messages'][-1]['content'] or 'Режим observer:' in full:
            block=next(m['content'] for m in kwargs['messages'] if m['content'].startswith('Текущая сцена'))
            scene=json.loads(block.split('\n',1)[1]);payload['scene'].update(scene['scene_meta']);payload['scene']['text']=scene['scene']
            if 'Режим observer:' in full:
                payload['facts']=[];payload['events']=[];payload['relationships']=[]
        payload['events']=[e for e in payload.get('events',[]) if set(e['character_ids'])<=set(payload['scene']['present_ids'])]
        value=json.dumps(canonical(payload,sha256(full.encode()).hexdigest()[:12]),ensure_ascii=False)
    elif observer:
        value = SECRET
    elif 'шаблон' in kwargs['messages'][-1]['content'].lower():
        value = summary()
    elif 'сценар' in kwargs['messages'][0]['content'].lower():
        value = '# Вечер в общем доме\n\nКомпания друзей собирается на кухне после долгого дня. Современная драмеди: живые разговоры, дружба и открытые линии.'
    else:
        value = NARRATIVE
    if kwargs.get('on_usage'):
        kwargs['on_usage']({'prompt_tokens':1000,'completion_tokens':100,'prompt_cache_hit_tokens':800})
    for i in range(0, len(value), 60):
        time.sleep(.025)
        if kwargs.get('cancel_event') and kwargs['cancel_event'].is_set():
            raise RuntimeError('Генерация остановлена.')
        yield value[i:i+60]


def tabletop_stream(**kwargs):
    from tabletop_fixture import definition
    prompt=kwargs['messages'][0]['content']
    if 'playable CampaignDefinition' in prompt:
        campaign = definition()
        campaign.ruleset_id = 'd20-fantasy-v1'
        campaign.ruleset_version = 3
        for actor in campaign.characters + campaign.creatures:
            actor.build.feature_choices = ['defense_style']
        idea = json.loads(kwargs['messages'][-1]['content'])['options']['idea']
        if idea == 'gameplay acceptance':
            from tabletop_gameplay_fixture import gameplay_definition
            campaign = gameplay_definition()
        if idea == 'invalid references':
            campaign.characters[1].knowledge.append('missing_secret')
            campaign.characters[1].relationships['missing_actor'] = 10
        value=campaign.model_dump_json()
    elif 'roleplay-портрет героя' in prompt:
        requested = json.loads(kwargs['messages'][-1]['content'])['field']
        portrait = {'name':'Александр','appearance':'Серый плащ','biography':'Бывший городской стражник.','personality':'Немногословный и упрямый.','ideals':'Защищать слабых.','bonds':'Старая стража.','flaws':'Не доверяет начальству.'}
        value = json.dumps(portrait if requested == 'all' else {requested:portrait[requested]})
    elif 'CampaignMutation JSON' in prompt:
        value=json.dumps({'operations':[{'type':'CreateLocation','value':{'id':'observatory','name':'Обсерватория','region_id':'district'}},{'type':'ConnectLocations','first':'market','second':'observatory'}]})
    elif kwargs.get('response_format'):
        action = json.loads(kwargs['messages'][-1]['content']).get('action', '')
        command = {'type': 'look'}
        if action == 'Пробираюсь через затопленный тоннель':
            command = {'type':'check','ability':'strength','skill':'athletics','difficulty':'MEDIUM','reason':'Сильное течение'}
        elif action == 'Уточнить путь':
            command = {'type':'request_choice','prompt':'Как обследуешь проход?', 'options':[
                {'id':'look','label':'Осмотреть стены','command':{'type':'look'}},
                {'id':'check','label':'Проверить течение','command':{'type':'check','ability':'strength','skill':'athletics'}},
            ]}
        checks={'Ищу следы':'investigation_check','Я от капитана':'deception_check','Карабкаюсь по стене':'climb_check','Изучаю руну':'arcana_check','Прокрадываюсь мимо стража':'stealth_check'}
        if action in checks:command={'type':'check','check_id':checks[action]}
        value=json.dumps(command)
    else:
        context=json.loads(kwargs['messages'][-1]['content'])['context']
        value='\n'.join(e['text'] for e in context['events'] if 'roll' not in e)
    if kwargs.get('on_usage'):kwargs['on_usage']({'prompt_tokens':100,'completion_tokens':50})
    yield value

llm.chat_stream = tabletop_stream

engine.chat_stream = stream
hold_next_preparation = False

def preparation_stream(**kwargs):
    global hold_next_preparation
    hold = hold_next_preparation
    hold_next_preparation = False
    for chunk in stream(**kwargs):
        yield chunk
        if hold:
            # Browser reconnection must observe an in-flight generation, independent
            # of device speed. Only the cancellation test enables this one-shot gate.
            deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                if kwargs.get('cancel_event') and kwargs['cancel_event'].is_set():
                    raise RuntimeError('Генерация остановлена.')
                time.sleep(.05)
            hold=False

preparation.chat_stream = preparation_stream
engine.find_loaded_model = preparation.find_loaded_model = lambda _: {'config': {'context_length':32768}}
def authoring_stream(**kwargs):
    if any('Ты редактор черновика Character' in m['content'] for m in kwargs['messages']):
        yield from stream(**kwargs)
    else:
        yield from tabletop_stream(**kwargs)

llm.chat_stream = authoring_stream
llm.get_available_models = lambda: ['local-model']
llm.get_loaded_models = lambda: [{'model_key':'local-model','display_name':'Test local model'}]
llm.get_deepseek_models = lambda _: ['deepseek-flash','deepseek-v4-pro']
llm.load_model = lambda **_: {}
llm.unload_all_models = lambda: 1

if __name__ == '__main__':
    path = os.getenv('E2E_DB_PATH') or str(Path(tempfile.mkdtemp())/'e2e.sqlite3')
    app = create_app(path)
    from backend.tabletop.dice import DiceEngine
    from tabletop_fixture import Fixed
    class BrowserDice(DiceEngine):
        def roll(self,expression,**kwargs):
            value=(4 if kwargs.get('purpose') in ('spell_damage','spell_healing','feature_healing') else ({'initiative':1,'attack':12,'damage':2}.get(kwargs.get('purpose'),10) if kwargs.get('actor')=='sentinel' else 8 if kwargs.get('purpose')=='damage' else 20))
            if os.getenv("E2E_GAMEPLAY")=="1" and kwargs.get("purpose")=="check" and kwargs.get("modifier",0)>=3: value=1
            class Bounded:
                def randint(self,lo,hi):return min(hi,max(lo,value))
            return DiceEngine(Bounded()).roll(expression,**kwargs)
    dice=BrowserDice()
    app.state.tabletop_runtime.dice=dice
    app.state.tabletop_runtime.combat.dice=dice
    @app.post('/test/calendar-policy-e5')
    def calendar_policy_e5():
        from test_calendar_start_policy import evidence
        from test_api import REMOTE
        j=evidence();s=j['candidate_snapshot'];repo=app.state.repository
        w=repo.create_workspace('E5 calendar policy')
        jid=repo.begin_preparation(w['id'],'draft_world',j['author_input']['text'],dict(REMOTE,_draft_task='world',_draft_input=j['author_input']['text']),0)
        journal={k:v for k,v in j.items() if k not in ('requests','recovery','binding','candidate_snapshot','candidate_version','current_diagnostics','current_start_block_reason','author_input')}
        journal.update(recovery_epoch=0,candidate_text=json.dumps(s,ensure_ascii=False))
        repo.save_response_journal(jid,journal)
        repo.save_draft_candidate(jid,s,[],review=j['recovery']['review'])
        repo.preparation_progress(jid,'','stopped')
        return {'id':w['id']}

    @app.post('/test/hold-preparation')
    def hold_preparation():
        global hold_next_preparation
        hold_next_preparation=True
        return {'held':True}

    @app.post('/test/appearance-seed')
    def appearance_seed():
        from devtools.narrative_test_world import load_fixture
        result=load_fixture(app.state.repository,'appearance')
        return {'world':result['world'],'save':result['save']}

    @app.post('/test/long-term-seed')
    def long_term_seed():
        from devtools.narrative_test_world import load_fixture
        result=load_fixture(app.state.repository,'long-term')
        return {'world':result['world'],'save':result['save']}

    @app.post('/test/newborn-seed')
    def newborn_seed():
        from devtools.narrative_test_world import load_fixture
        result=load_fixture(app.state.repository,'newborn-twins')
        return {'world':result['world'],'save':result['save']}

    @app.post('/test/choices-seed')
    def choices_seed():
        from devtools.narrative_test_world import load_fixture
        result=load_fixture(app.state.repository,'choices')
        return {'world':result['world'],'save':result['save']}

    @app.post('/test/continuity-seed')
    def continuity_seed():
        from devtools.narrative_test_world import load_fixture
        from test_narrative_test_world import CONFIG
        result=load_fixture(app.state.repository,'continuity')
        job=app.state.repository.begin_job(result['save'],'','start',CONFIG)
        engine.run_job(app.state.repository.path,job,engine.Worker())
        assert app.state.repository.get_job(job)['status']=='saved'
        return {'world':result['world'],'save':result['save']}

    @app.post('/test/phone-seed')
    def phone_seed(unread: bool = False):
        from devtools.narrative_test_world import load_fixture
        from test_narrative_test_world import CONFIG
        from backend.runtime_v3.remote import apply
        from backend.runtime_v3.repository import append_history
        result=load_fixture(app.state.repository,'phone')
        repo=app.state.repository;sid=result['save']
        job=repo.begin_job(sid,'','start',CONFIG)
        engine.run_job(repo.path,job,engine.Worker())
        assert repo.get_job(job)['status']=='saved', repo.get_job(job)['error']
        snap=repo.get_snapshot(sid)
        snap,batch=apply(snap,dict(action='call',operation_id='qa-incoming-call',contact_id='phone-qa_vera-qa-kirill'),actor_id='qa_vera',autonomous=True)
        if unread:
            snap, message_batch = apply(snap, dict(action='send', operation_id='qa-incoming-message', contact_id='phone-qa_vera-qa-kirill', content='Прочти, когда будет удобно.'), actor_id='qa_vera', autonomous=True)
            for section, rows in message_batch.items():
                batch.setdefault(section, []).extend(rows)
        with repo.connect() as db:
            snap['history_head']=append_history(db,snap.get('history_head'),batch)
            db.execute('UPDATE saves SET state_json=?,revision=revision+1 WHERE id=?',(json.dumps(snap,ensure_ascii=False),sid))
        return {'world':result['world'],'save':sid}

    @app.post('/test/initiative-seed')
    def initiative_seed():
        from devtools.narrative_test_world import load_fixture
        from test_narrative_test_world import CONFIG
        result=load_fixture(app.state.repository,'initiative')
        job=app.state.repository.begin_job(result['save'],'','start',CONFIG)
        engine.run_job(app.state.repository.path,job,engine.Worker())
        assert app.state.repository.get_job(job)['status']=='saved'
        return {'world':result['world'],'save':result['save']}

    @app.post('/test/protagonist-seed')
    def protagonist_seed():
        from devtools.narrative_test_world import load_fixture
        result=load_fixture(app.state.repository,'protagonist')
        return {'world':result['world'],'save':result['save']}

    @app.post('/test/knowledge-seed')
    def knowledge_seed():
        from devtools.narrative_test_world import load_fixture, knowledge_correction
        from test_narrative_test_world import CONFIG
        from runtime_v3_fixture import execute
        repo=app.state.repository;result=load_fixture(repo,'knowledge');sid=result['save']
        text,payload=knowledge_correction(repo.get_snapshot(sid))
        jid=repo.begin_job(sid,'Читаю сообщение Олега.','turn',CONFIG)
        execute(repo,jid,payload,text)
        assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
        return {'world':result['world'],'save':sid}

    @app.post('/test/goals-seed')
    def goals_seed():
        from devtools.narrative_test_world import load_fixture
        from test_goals_values import completion, MEET
        from test_narrative_test_world import CONFIG
        from runtime_v3_fixture import execute
        repo=app.state.repository;result=load_fixture(repo,'goals')
        sid=result['save'];state=repo.get_snapshot(sid)['world_state']
        jid=repo.begin_job(sid,'Иду навстречу.','turn',CONFIG)
        execute(repo,jid,completion(state,'qa_ilya'),MEET)
        assert repo.get_job(jid)['status']=='saved'
        return {'world':result['world'],'save':sid}

    @app.post('/test/personality-seed')
    def personality_seed():
        from devtools.narrative_test_world import load_fixture
        repo=app.state.repository
        result=load_fixture(repo,'personality')
        repo.switch_actor(result['save'],'qa_asya',repo.get_save(result['save'])['revision'])
        return {'world':result['world'],'save':result['save']}

    @app.post('/test/residence-seed')
    def residence_seed():
        from devtools.narrative_test_world import load_fixture
        from test_narrative_test_world import ordinary_job
        repo=app.state.repository
        result=load_fixture(repo,'residence-roles')
        ordinary_job(repo,result['save'],'start')
        return {'world':result['world'],'save':result['save']}

    @app.post('/test/family-seed')
    def family_seed():
        from devtools.narrative_test_world import load_fixture
        from test_narrative_test_world import ordinary_job
        repo=app.state.repository
        result=load_fixture(repo,'family')
        ordinary_job(repo,result['save'],'start')
        return {'world':result['world'],'save':result['save']}

    @app.post('/test/commitments-seed')
    def commitments_seed():
        from devtools.narrative_test_world import load_fixture
        from test_narrative_test_world import ordinary_job
        repo = app.state.repository
        result = load_fixture(repo, 'commitments')
        ordinary_job(repo,result['save'],'start')
        return {'world':result['world'],'save':result['save']}

    @app.post('/test/calendar-seed')
    def calendar_seed():
        from devtools.narrative_test_world import load_fixture
        from test_narrative_test_world import ordinary_job
        repo = app.state.repository
        result = load_fixture(repo, 'calendar-evening')
        ordinary_job(repo,result['save'],'start')
        return {'world':result['world'],'save':result['save']}

    @app.post('/test/seed')
    def seed():
        repo = app.state.repository
        wid = repo.save_world('Тест вариантов и памяти',summary())
        sid = repo.create_save(wid,'Тестовое прохождение')
        return {'world':wid,'save':sid}
    uvicorn.run(app, host='127.0.0.1', port=int(os.getenv('E2E_PORT','8011')), log_level='warning')
