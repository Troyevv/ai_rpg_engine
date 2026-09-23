"""Browser-only fixture server. Never imported by the production application."""
import json
import re
import os
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
    observer='Тип хода: background' in full or 'Режим observer:' in full
    if 'Ты Сценарист и Генератор мира' in full:
        from test_draft_world import fixture
        value=json.dumps(fixture(),ensure_ascii=False)
    elif 'Ты редактор RPG' in full:
        value=json.dumps({'value':'Обновлённая внешность'},ensure_ascii=False)
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
        value=json.dumps(payload,ensure_ascii=False)
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


engine.chat_stream = stream
preparation.chat_stream = stream
engine.find_loaded_model = preparation.find_loaded_model = lambda _: {'config': {'context_length':32768}}
llm.get_available_models = lambda: ['local-model']
llm.get_loaded_models = lambda: [{'model_key':'local-model','display_name':'Test local model'}]
llm.get_deepseek_models = lambda _: ['deepseek-flash','deepseek-v4-pro']
llm.load_model = lambda **_: {}
llm.unload_all_models = lambda: 1

if __name__ == '__main__':
    path = os.getenv('E2E_DB_PATH') or str(Path(tempfile.mkdtemp())/'e2e.sqlite3')
    app = create_app(path)
    @app.post('/test/seed')
    def seed():
        repo = app.state.repository
        wid = repo.save_world('Тест вариантов и памяти',summary())
        sid = repo.create_save(wid,'Тестовое прохождение')
        return {'world':wid,'save':sid}
    uvicorn.run(app, host='127.0.0.1', port=int(os.getenv('E2E_PORT','8011')), log_level='warning')
