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


def stream(**kwargs):
    full='\n'.join(m['content'] for m in kwargs['messages'])
    observer='Тип хода: background' in full or 'Режим observer:' in full or 'mode=observer' in full
    if 'Каноническая JSON Schema WorldState' in full:
        from test_draft_world import fixture
        value=json.dumps(fixture(),ensure_ascii=False)
    elif 'Ты редактор RPG' in full:
        value=json.dumps({'value':'Обновлённая внешность'},ensure_ascii=False)
    elif kwargs.get('response_format') and 'RawTurnResult v3' in full:
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
        idea = json.loads(kwargs['messages'][-1]['content'])['options']['idea']
        if idea == 'invalid references':
            campaign.characters[1].knowledge.append('missing_secret')
            campaign.characters[1].relationships['missing_actor'] = 10
        value=campaign.model_dump_json()
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
            value=({'initiative':1,'attack':12,'damage':2}.get(kwargs.get('purpose'),10) if kwargs.get('actor')=='sentinel' else 8 if kwargs.get('purpose')=='damage' else 20)
            return DiceEngine(Fixed(*([value]*10))).roll(expression,**kwargs)
    dice=BrowserDice()
    app.state.tabletop_runtime.dice=dice
    app.state.tabletop_runtime.combat.dice=dice
    @app.post('/test/hold-preparation')
    def hold_preparation():
        global hold_next_preparation
        hold_next_preparation=True
        return {'held':True}

    @app.post('/test/seed')
    def seed():
        repo = app.state.repository
        wid = repo.save_world('Тест вариантов и памяти',summary())
        sid = repo.create_save(wid,'Тестовое прохождение')
        return {'world':wid,'save':sid}
    uvicorn.run(app, host='127.0.0.1', port=int(os.getenv('E2E_PORT','8011')), log_level='warning')
