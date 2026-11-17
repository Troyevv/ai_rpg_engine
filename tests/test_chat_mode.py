"""Production API/SQLite/context/service; only provider IO is substituted (no paid calls)."""
import copy
import json
import sqlite3
import threading
import time
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from backend.api.app import create_app
from backend.chat.context import TEMPLATE, SUMMARY_PROMPT, RP_PROMPT
from backend.chat.repository import ChatRepository, row
from backend.repositories.preparation import Repository
from test_worlds import summary as world_summary

MEMORY = '''ВЫЖИМКА
ПРАВИЛА И НЕИЗМЕННЫЕ ФАКТЫ
12 мая 2010 — рождение Лены; дата установлена.
ОТНОШЕНИЯ
Лена → Илья: доверяет. Илья → Лена: подозревает.
ЧТО ЗНАЮТ / ЧТО ТАЙНА
Ключ спрятан в саду; знает только Лена. Илья ошибочно считает, что ключ у Марии.
АКТИВНЫЕ СОБЫТИЯ И ОБЯЗАТЕЛЬСТВА
Обещание вернуть книгу выполнено.
ГЛАВНОЕ СЕЙЧАС
Дата: не установлено. Незавершённый разговор: «Ты хотел сказать…»
'''


def tok(): return uuid4().hex


@pytest.fixture
def env(tmp_path):
    app = create_app(tmp_path/'chat.sqlite3')
    with TestClient(app) as client:
        yield client, app


def create(client, memory=MEMORY, **overrides):
    settings=client.get('/api/chat/defaults').json()['settings']
    for stage in ('reply','summary'):
        settings[stage].update(auto_context=False,auto_output=False)
    settings['reply']['model']='fixture-model'
    settings['summary']['model']='fixture-summary'
    body=dict(token=tok(),name='RP история',memory=memory,settings=settings,**overrides)
    response=client.post('/api/chat/campaigns',json=body)
    assert response.status_code==200,response.text
    return response.json()


def state(client,c): return client.get('/api/chat/campaigns/'+c['id']).json()
def url(c,suffix=''): return '/api/chat/campaigns/'+c['id']+suffix

def body(c,**kw): return dict(revision=c['revision'],token=tok(),**kw)


def wait(client,c,j):
    for _ in range(400):
        value=client.get(url(c,'/jobs/'+j['id'])).json()
        if value['status']!='running': return value
        time.sleep(.005)
    raise AssertionError('worker did not complete')


def provider(text='— Продолжай, — тихо отвечает Лена.', finish='stop'):
    def stream(**kw):
        assert kw.get('response_format') is None
        kw['on_usage']({'prompt_tokens':321,'completion_tokens':24,'prompt_cache_hit_tokens':100})
        for part in [text[:12],text[12:]]:
            if part: yield part
        kw['on_finish'](finish)
        if finish=='length':
            from llm import OutputLimitReached
            raise OutputLimitReached('length')
    return stream


def generate(client,c,kind='reply',text='Я слушаю.',**kw):
    result=client.post(url(c,'/generate'),json=body(c,kind=kind,text=text,**kw))
    assert result.status_code==200,result.text
    return wait(client,c,result.json())


def checkpoint(client,c,text=MEMORY+'\nНовая сцена',next_chapter=True):
    with patch('llm.chat_stream',side_effect=provider(text)):
        j=generate(client,c,'summary','')
    assert j['status']=='complete'
    c=state(client,c)
    response=client.post(url(c,'/drafts/'+j['output_id']+'/confirm'),json=body(c,text=text,next_chapter=next_chapter))
    assert response.status_code==200,response.text
    return response.json(),j


def test_one_call_persistence_pipeline_isolation_and_usage(env):
    client,app=env;c=create(client)
    with app.state.repository.connect() as db:
        original={t:db.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in ('worlds','saves','turns','game_jobs')}
    with patch('llm.chat_stream',side_effect=provider()) as transport,patch('engine.submit',side_effect=AssertionError('Narrative forbidden')), \
         patch('backend.runtime_v3.resolver.StateResolver',side_effect=AssertionError('Resolver forbidden')), \
         patch('backend.services.long_term_advance.execute',side_effect=AssertionError('Advance forbidden')), \
         patch('engine.chat_stream',side_effect=AssertionError('Narrative/extraction provider forbidden')):
        j=generate(client,c)
        assert j['status']=='complete'
        assert transport.call_count==1
        assert transport.call_args.kwargs['require_complete']
        assert j['usage'][0]['input_tokens']==321
        assert j['usage'][0]['output_tokens']==24
        assert j['usage'][0]['stage']=='chat_reply'
        c=state(client,c)
        generate(client,c,text='Что дальше?')
        assert transport.call_count==2
    with app.state.repository.connect() as db:
        assert all(db.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]==n for t,n in original.items())
        log=db.execute('SELECT * FROM llm_requests WHERE job_id=?',(j['id'],)).fetchone()
        assert json.loads(log['context_json'])[0]['content'].startswith(RP_PROMPT)
        assert log['save_id'] is None and log['workspace_id'] is None
    reopened=ChatRepository(Repository(app.state.repository.path))
    assert len(reopened.page(c['id'])['messages'])==4
    sse=client.get(url(c,'/jobs/'+j['id']+'/events'))
    assert sse.text.count('event: snapshot')==1
    assert 'Продолжай' in sse.text


def test_summary_review_atomic_cutoff_tail_and_double_confirm(env):
    client,app=env;c=create(client)
    with patch('llm.chat_stream',side_effect=provider()): generate(client,c)
    c=state(client,c);old=c['memory']['id']
    with patch('llm.chat_stream',side_effect=provider(MEMORY+'\nРазговор продолжается.')) as io:
        j=generate(client,c,'summary','')
        assert io.call_count==1
        inputs=io.call_args.kwargs['messages']
        assert TEMPLATE in inputs[0]['content'] and SUMMARY_PROMPT in inputs[0]['content']
        assert sum('Я слушаю.'==m['content'] for m in inputs)==1
    c=state(client,c)
    assert c['memory']['id']==old and len(c['chapters'])==1
    d=client.get(url(c,'/drafts/'+j['output_id'])).json()
    assert d['text']==d['original'] and not d['stale']
    edited=d['text']+'\nАвтор исправил дату: 13 мая.'
    payload=body(c,text=edited,next_chapter=True)
    endpoint=url(c,'/drafts/'+d['id']+'/confirm')
    first=client.post(endpoint,json=payload); assert first.status_code==200,first.text
    second=client.post(endpoint,json=payload);assert second.status_code==200
    c=second.json();assert len(c['chapters'])==2 and c['memory']['text']==edited
    assert len(client.get(url(c,'/messages')).json()['messages'])==2
    with patch('llm.chat_stream',side_effect=provider()) as io:
        generate(client,c,text='Продолжай с этого места.')
        sent=io.call_args.kwargs['messages']
        assert sum(x['content']=='Я слушаю.' for x in sent)==0  # carry-over is labelled, not a new action
        assert edited in sent[1]['content']
        assert 'Уже произошедший конец сцены' in sent[2]['content']
    c=state(client,c)
    c,_=checkpoint(client,c,next_chapter=False)
    assert len(c['chapters'])==2 and c['memory']['cutoff']==4


def test_stale_draft_and_conflict_do_not_advance(env):
    client,_=env;c=create(client)
    with patch('llm.chat_stream',side_effect=provider(MEMORY)): j=generate(client,c,'summary','')
    c=state(client,c)
    with patch('llm.chat_stream',side_effect=provider()):generate(client,c)
    c=state(client,c)
    assert client.get(url(c,'/drafts/'+j['output_id'])).json()['stale']
    res=client.post(url(c,'/drafts/'+j['output_id']+'/confirm'),json=body(c,text=MEMORY,next_chapter=True))
    assert res.status_code==409
    assert len(state(client,c)['chapters'])==1


def test_edit_archive_recovers_checkpoint_and_never_inherits_future(env):
    client,app=env;c=create(client);initial=c['memory']['id'];original_branch=c['active_branch']
    with patch('llm.chat_stream',side_effect=provider('Свадьба произошла.')):generate(client,c,text='Я согласен на свадьбу.')
    c=state(client,c)
    original_messages=client.get(url(c,'/messages')).json()['messages']
    c,_=checkpoint(client,c,MEMORY+'\nСВАДЬБА В БУДУЩЕМ СУФФИКСЕ')
    with patch('llm.chat_stream',side_effect=provider('Поздний ответ')):generate(client,c,text='Теперь переезд.')
    c=state(client,c)
    response=client.post(url(c,'/edit'),json=body(c,branch=original_branch,message=original_messages[0]['id'],text='Я отказываюсь.'))
    assert response.status_code==200,response.text
    c=response.json()
    assert c['active_branch']!=original_branch and c['memory']['id']==initial
    assert len(c['chapters'])==1
    assert len(client.get(url(c,'/messages')).json()['messages'])==1
    with patch('llm.chat_stream',side_effect=provider()) as io:
        generate(client,c,text='Продолжай.')
        sent=json.dumps(io.call_args.kwargs['messages'],ensure_ascii=False)
        assert 'СВАДЬБА' not in sent and 'переезд' not in sent
    original=app.state.chat.repo.page(c['id'],original_branch)
    assert len(original['messages'])==4 and 'Свадьба' in original['messages'][1]['content']


def test_regeneration_replays_recorded_context_settings_not_future(env):
    client,app=env;c=create(client)
    with patch('llm.chat_stream',side_effect=provider()) as io:
        j=generate(client,c)
        sent=copy.deepcopy(io.call_args.kwargs['messages'])
    c=state(client,c)
    c,_=checkpoint(client,c,MEMORY+'\nСМЕРТЬ ПОЗЖЕ')
    settings=copy.deepcopy(c['settings']);settings['prompt']='Будущие правила';settings['reply']['model']='another'
    c=client.put(url(c,'/settings'),json=body(c,settings=settings)).json()
    with patch('llm.chat_stream',side_effect=provider('Другой вариант')) as io:
        new=generate(client,c,'regenerate','',target=j['output_id'])
        assert new['status']=='complete'
        assert io.call_args.kwargs['messages']==sent
        assert io.call_args.kwargs['model']=='fixture-model'
    assert len(state(client,c)['branches'])==2


@pytest.mark.parametrize('finish,expected',[('length','length'),('stop','empty')])
def test_incomplete_summary_is_not_approved(env,finish,expected):
    client,_=env;c=create(client)
    with patch('llm.chat_stream',side_effect=provider('Неполный' if finish=='length' else '',finish)):
        j=generate(client,c,'summary','')
    assert j['status']==expected
    c=state(client,c)
    res=client.post(url(c,'/drafts/'+j['output_id']+'/confirm'),json=body(c,text=MEMORY,next_chapter=True))
    assert res.status_code==409 and len(state(client,c)['chapters'])==1
    res=client.post(url(c,'/drafts/'+j['output_id']+'/confirm'),json=body(c,text=MEMORY,next_chapter=True,accept_partial=True))
    assert res.status_code==200


def test_stop_late_result_duplicate_post_and_manual_retry(env):
    client,app=env;c=create(client);entered=threading.Event();release=threading.Event()
    def slow(**kw):
        yield 'Частично';entered.set();release.wait(3);yield ' ПОЗДНО';kw['on_finish']('stop')
    payload=body(c,kind='reply',text='Привет')
    with patch('llm.chat_stream',side_effect=slow) as io:
        j=client.post(url(c,'/generate'),json=payload).json();assert entered.wait(2)
        duplicate=client.post(url(c,'/generate'),json=payload).json();assert duplicate['id']==j['id']
        assert io.call_count==1
        stopped=client.post(url(c,'/jobs/'+j['id']+'/stop')).json();assert stopped['status']=='stopped'
        release.set();time.sleep(.05)
        assert client.get(url(c,'/jobs/'+j['id'])).json()['response']=='Частично'
    c=state(client,c)
    with patch('llm.chat_stream',side_effect=provider()) as io:
        retried=generate(client,c,'retry','',target=j['id'])
        assert retried['status']=='complete' and io.call_count==1
    assert len(state(client,c)['branches'])==2
    assert len(app.state.chat.repo.page(c['id'])['messages'])==2


def test_restart_preserves_partial_never_calls_provider(env):
    client,app=env;c=create(client)
    payload=body(c,kind='reply',text='Записанный ввод',target=None)
    jid,_=app.state.chat.reserve(c['id'],payload)
    app.state.chat.persist(c['id'],jid,'Частичный ответ')
    with patch('llm.chat_stream',side_effect=AssertionError('No replay')):
        app.state.chat.recover()
        j=client.get(url(c,'/jobs/'+jid)).json()
        assert j['status']=='interrupted' and j['response']=='Частичный ответ'
        assert len(client.get(url(c,'/messages')).json()['messages'])==2


def test_hard_limit_model_change_big_input_and_summary_reserve(env):
    client,app=env;c=create(client)
    with patch('llm.chat_stream',side_effect=AssertionError('No oversized call')):
        res=client.post(url(c,'/generate'),json=body(c,kind='reply',text='Большой ввод '*6000))
        assert res.status_code==409 and not client.get(url(c,'/messages')).json()['messages']
        settings=copy.deepcopy(c['settings']);settings['reply']['context_length']=4096;settings['reply']['max_tokens']=512
        settings['summary']['context_length']=16384;settings['summary']['max_tokens']=8192
        c=client.put(url(c,'/settings'),json=body(c,settings=settings)).json()
        b=client.post(url(c,'/budget'),json=body(c,text='Я слушаю.')).json()
        assert b['summary']['ratio']>b['reply']['ratio']
        assert b['warning']
        assert b['reply']['approximate'] and b['summary']['output']==8192


def test_campaign_scope_origin_and_keys(env):
    client,app=env;a=create(client);b=create(client)
    with patch('llm.chat_stream',side_effect=provider()):j=generate(client,a)
    for endpoint in ('/jobs/'+j['id'],'/jobs/'+j['id']+'/events'):
        assert client.get(url(b,endpoint)).status_code==409
    assert client.post(url(b,'/jobs/'+j['id']+'/stop')).status_code==409
    assert client.get(url(b,'/messages?branch='+a['active_branch'])).status_code==409
    assert client.post(url(b,'/select'),json=body(b,branch=a['active_branch'])).status_code==409
    assert client.post(url(b,'/generate'),json=body(b,kind='regenerate',target=j['output_id'])).status_code==409
    assert client.post(url(b,'/generate'),json=body(b,kind='reply',text='x'),headers={'origin':'https://evil.example'}).status_code==403
    settings=copy.deepcopy(b['settings']);settings['reply']['api_key']='do-not-store'
    assert client.put(url(b,'/settings'),json=body(b,settings=settings)).status_code==422
    with app.state.repository.connect() as db: assert 'do-not-store' not in '\n'.join(db.iterdump())


def test_manual_memory_point_in_time_and_oversize_confirm(env):
    client,_=env;c=create(client)
    with patch('llm.chat_stream',side_effect=provider()):generate(client,c)
    c=state(client,c);first=client.get(url(c,'/messages')).json()['messages'][0]
    draft=client.post(url(c,'/memory'),json=body(c,text=MEMORY+'\nБУДУЩАЯ АВТОРСКАЯ ПРАВКА')).json()
    c=state(client,c)
    fail=client.post(url(c,'/drafts/'+draft['draft']+'/confirm'),json=body(c,text='длинная память '*10000,next_chapter=True))
    assert fail.status_code==409
    c=client.post(url(c,'/drafts/'+draft['draft']+'/confirm'),json=body(c,text=MEMORY+'\nБУДУЩАЯ АВТОРСКАЯ ПРАВКА',next_chapter=False)).json()
    assert c['memory']['cutoff']==0  # manual edit does not silently cover unsummarized messages
    c=client.post(url(c,'/edit'),json=body(c,branch=c['active_branch'],message=first['id'],text='Вместо этого')).json()
    assert 'БУДУЩАЯ' not in c['memory']['text']


def test_confirmation_db_failure_rolls_back_everything(env):
    client,app=env;c=create(client)
    with patch('llm.chat_stream',side_effect=provider(MEMORY)):j=generate(client,c,'summary','')
    c=state(client,c)
    with app.state.repository.connect() as db:
        db.execute("CREATE TRIGGER fail_chat_chapter BEFORE INSERT ON chat_chapters BEGIN SELECT RAISE(ABORT, 'test failure'); END")
    res=client.post(url(c,'/drafts/'+j['output_id']+'/confirm'),json=body(c,text=MEMORY,next_chapter=True))
    assert res.status_code==409
    after=state(client,c)
    assert after['revision']==c['revision'] and after['memory']==c['memory'] and len(after['chapters'])==1
    assert client.get(url(c,'/drafts/'+j['output_id'])).json()['status']=='complete'


def test_legacy_narrative_and_world_source_are_unchanged(env):
    client,app=env
    world=client.post('/api/worlds',json={'name':'Исходный мир','markdown':world_summary()}).json()
    save=client.post(f"/api/worlds/{world['id']}/saves",json={'name':'Narrative'}).json()
    with app.state.repository.connect() as db:
        before=db.execute('SELECT state_json FROM saves WHERE id=?',(save['id'],)).fetchone()[0]
    for data in [dict(world_id=world['id']),dict(save_id=save['id'],revision=save['revision'],history_turns=2)]:
        p=client.post('/api/chat/source',json=data)
        assert p.status_code==200,p.text
        c=create(client,memory='Проверенный снимок',source={'id':p.json()['id']})
        assert c['source']['origin']['mode'] in ('world','narrative')
    with app.state.repository.connect() as db:
        assert db.execute('SELECT state_json FROM saves WHERE id=?',(save['id'],)).fetchone()[0]==before
    ChatRepository(Repository(app.state.repository.path))
    assert client.get('/api/saves/'+str(save['id'])).status_code==200
    assert client.post('/api/chat/source',json=dict(save_id=save['id'],revision=999)).status_code==409


def test_long_history_thousand_messages_multiple_checkpoints_and_bounded_pages(env):
    client,app=env;c=create(client);r=app.state.chat.repo
    # Capacity for 250-message chunks under the byte-level conservative estimator.
    settings=copy.deepcopy(c['settings'])
    settings['summary']['context_length']=65536
    c=client.put(url(c,'/settings'),json=body(c,settings=settings)).json()
    for chapter in range(4):
        with r.transaction() as db:
            b=r.branch(db,c['id'])
            for i in range(250):r.add_message(db,c['id'],b,'user' if i%2==0 else 'assistant',f'Глава {chapter}, сообщение {i}')
        c=state(client,c)
        c,_=checkpoint(client,c,MEMORY+f'\nПамять главы {chapter}')
    assert c['branch']['head']==1000 and len(c['chapters'])==5
    page=client.get(url(c,'/messages?limit=40')).json()
    assert len(page['messages'])==40 and page['more']
    seen=[];before=2147483647
    while True:
        page=r.page(c['id'],before=before,limit=100);seen.extend(m['id'] for m in page['messages'])
        if not page['more']:break
        before=page['messages'][0]['seq']
    assert len(set(seen))==1000
    with patch('llm.chat_stream',side_effect=provider()) as io:
        generate(client,c,text='Ещё один ход')
        assert len(io.call_args.kwargs['messages'])<=4
        assert 'сообщение 0' not in json.dumps(io.call_args.kwargs['messages'],ensure_ascii=False)


def test_template_and_prompt_preserve_user_fields():
    for text in ('Финансы:','Ошибочно считает:','От кого скрывается:','Незавершённый разговор / действие:',
                 'День недели:','Что произойдёт без вмешательства ГГ:','Невысказанное / скрытое:',
                 'ПРАВИЛА И НЕИЗМЕННЫЕ ФАКТЫ','ХРОНОЛОГИЯ','Манера речи:'):
        assert text in TEMPLATE
    assert 'выполненные обещания' in SUMMARY_PROMPT and 'A → B не равно B → A' in SUMMARY_PROMPT


def test_draft_edit_compare_and_swap_and_repeated_save(env):
    client,_=env;c=create(client)
    with patch('llm.chat_stream',side_effect=provider(MEMORY)):j=generate(client,c,'summary','')
    c=state(client,c);endpoint=url(c,'/drafts/'+j['output_id'])
    payload=body(c,text=MEMORY+'\nПравка в первой вкладке',draft_revision=0)
    first=client.put(endpoint,json=payload)
    assert first.status_code==200 and first.json()['edit_revision']==1
    assert client.put(endpoint,json=payload).json()['edit_revision']==1
    stale=client.put(endpoint,json=body(c,text='Другая вкладка',draft_revision=0))
    assert stale.status_code==409
    assert client.post(endpoint+'/confirm',json=body(c,text='Старая вкладка',next_chapter=False,draft_revision=0)).status_code==409
    accepted=client.post(endpoint+'/confirm',json=body(c,text=first.json()['text'],next_chapter=False,draft_revision=1))
    assert accepted.status_code==200
    assert 'Правка в первой' in accepted.json()['memory']['text']


def test_db_write_error_preserves_request_journal_and_restart_prefix(env):
    client,app=env;c=create(client)
    with app.state.repository.connect() as db:
        db.execute("CREATE TRIGGER fail_chat_write BEFORE UPDATE ON chat_messages BEGIN SELECT RAISE(ABORT, 'DB failure'); END")
    with patch('llm.chat_stream',side_effect=provider('Доступный частичный текст')):
        j=client.post(url(c,'/generate'),json=body(c,kind='reply',text='Ввод сохранён')).json()
        for _ in range(200):
            if j['id'] not in app.state.chat.workers:break
            time.sleep(.01)
    with app.state.repository.connect() as db:
        receipt=db.execute('SELECT response_text FROM llm_requests WHERE job_id=?',(j['id'],)).fetchone()
        assert receipt and receipt['response_text']
        db.execute('DROP TRIGGER fail_chat_write')
    app.state.chat.recover()
    j=client.get(url(c,'/jobs/'+j['id'])).json()
    assert j['status']=='error' and j['response']
    saved=client.get(url(c,'/messages')).json()['messages']
    assert saved[0]['content']=='Ввод сохранён'
    assert saved[1]['status']=='error' and saved[1]['content']


def test_summary_stop_and_late_provider_does_not_replace_approved_memory(env):
    client,app=env;c=create(client);entered=threading.Event();release=threading.Event()
    def stream(**kw):
        yield 'Частичная выжимка';entered.set();release.wait(3);yield ' ПОЗДНИЙ';kw['on_finish']('stop')
    with patch('llm.chat_stream',side_effect=stream):
        j=client.post(url(c,'/generate'),json=body(c,kind='summary',text='')).json();assert entered.wait(2)
        client.post(url(c,'/jobs/'+j['id']+'/stop'));release.set();time.sleep(.05)
    after=state(client,c)
    assert after['memory']['text']==c['memory']['text'] and len(after['chapters'])==1
    d=client.get(url(c,'/drafts/'+j['output_id'])).json()
    assert d['status']=='stopped' and d['text']=='Частичная выжимка'
    assert client.post(url(after,'/drafts/'+d['id']+'/cancel'),json=body(after)).status_code==200
    assert client.get(url(c,'/drafts/'+d['id'])).json()['status']=='cancelled'


def test_edit_after_cutoff_preserves_compatible_memory(env):
    client,_=env;c=create(client)
    with patch('llm.chat_stream',side_effect=provider()):generate(client,c)
    c,_=checkpoint(client,state(client,c))
    mid=c['memory']['id']
    with patch('llm.chat_stream',side_effect=provider()):generate(client,c,text='Новый ввод после выжимки')
    c=state(client,c);messages=client.get(url(c,'/messages')).json()['messages']
    changed=client.post(url(c,'/edit'),json=body(c,branch=c['active_branch'],message=messages[-2]['id'],text='Исправленный новый ввод')).json()
    assert changed['memory']['id']==mid
    assert changed['branch']['head']==3


def test_server_credentials_and_actual_attempts_remain_separate_between_campaigns(env):
    client,app=env;a=create(client);b=create(client)
    from backend.services.credentials import Credentials
    Credentials(app.state.repository).put('deepseek','secret-chat-key')
    for c in (a,b):
        settings=copy.deepcopy(c['settings']);settings['reply'].update(provider='deepseek',model='test-remote')
        client.put(url(c,'/settings'),json=body(c,settings=settings))
    captured=[]
    def stream(**kw):
        assert kw['api_key']=='secret-chat-key';captured.append(kw['messages']);yield 'Ответ';kw['on_finish']('stop')
    with patch('llm.chat_stream',side_effect=stream):
        j=generate(client,state(client,a),text='Только в кампании A')
        k=generate(client,state(client,b),text='Только в кампании B')
    assert len(captured)==2 and 'Только в кампании A' not in json.dumps(captured[1],ensure_ascii=False)
    assert j['usage'][0]['cost_usd'] is None and j['usage'][0]['input_tokens'] is None
    logs=client.get(url(a,'/jobs/'+j['id']+'/requests'))
    assert logs.status_code==200 and 'secret-chat-key' not in logs.text
    assert client.get(url(b,'/jobs/'+j['id']+'/requests')).status_code==409
    with app.state.repository.connect() as db:
        assert 'secret-chat-key' not in '\n'.join(db.iterdump())


def test_narrative_copy_captures_only_accepted_turns(env):
    client,app=env
    from test_api import new_save,wait_job,REMOTE,NARRATIVE,result,wire,canonical
    world,save=new_save(client)
    def stream(**kw):
        yield json.dumps(wire(canonical(result(),0),NARRATIVE,app.state.repository.get_snapshot(save['id'])),ensure_ascii=False) if kw.get('response_format') else NARRATIVE
    with patch('engine.chat_stream',side_effect=stream):
        job=client.post(f"/api/saves/{save['id']}/turns",json={'kind':'start','revision':0,'config':REMOTE,'api_key':'fixture-key'}).json()
        assert wait_job(client,job['id'])['status']=='saved'
    save=client.get('/api/saves/'+str(save['id'])).json()
    # An uncommitted candidate is not in the accepted turns projection.
    with app.state.repository.connect() as db:
        db.execute("UPDATE game_jobs SET narrative=narrative||' НЕПРИНЯТЫЙ КАНДИДАТ' WHERE id=?",(job['id'],))
        before=db.execute('SELECT state_json FROM saves WHERE id=?',(save['id'],)).fetchone()[0]
    p=client.post('/api/chat/source',json=dict(save_id=save['id'],revision=save['revision'],history_turns=1))
    assert p.status_code==200,p.text
    assert NARRATIVE in p.json()['memory'] and 'НЕПРИНЯТЫЙ КАНДИДАТ' not in p.json()['memory']
    assert len(p.json()['origin']['turns'])==1
    with app.state.repository.connect() as db:
        assert db.execute('SELECT state_json FROM saves WHERE id=?',(save['id'],)).fetchone()[0]==before
