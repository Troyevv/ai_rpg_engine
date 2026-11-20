"""Full production service/API/SQLite, only transport/metadata IO are substituted."""
import json
import time
from unittest.mock import patch

from backend.chat.context import TEMPLATE, INITIAL_PROMPT, OPENING_PROMPT, SUMMARY_PROMPT, RP_PROMPT
from backend.chat import capabilities
from backend.chat.models import ModelSettings
from test_chat_mode import env, tok, provider, wait, state, url, body, generate, checkpoint, MEMORY


def draft(client, idea='Город у маяка. Лена знает тайну, Илья не знает. Дата 9 октября.', source=None):
    settings=client.get('/api/chat/defaults').json()['settings']
    for stage in ('reply','summary'):
        settings[stage].update(model='fixture',auto_context=False,auto_output=True,context_length=131072)
    payload=dict(token=tok(),name='По идее',idea=idea,text='' if idea else MEMORY,settings=settings,source=source)
    response=client.post('/api/chat/creations',json=payload)
    assert response.status_code==200,response.text
    return response.json(),payload


def cp(d,suffix=''):return '/api/chat/creations/'+d['id']+suffix


def finish(client,d,j):
    for _ in range(400):
        value=client.get(cp(d,'/jobs/'+j['id'])).json()
        if value['status']!='running':return value
        time.sleep(.005)
    raise AssertionError('creation worker did not finish')


def initial(client,d,kind='initial'):
    response=client.post(cp(d,'/generate'),json=body(d,kind=kind))
    assert response.status_code==200,response.text
    return finish(client,d,response.json())


def current(client,d):return client.get(cp(d)).json()


def approve(client,d,**kw):
    response=client.post(cp(d,'/confirm'),json=body(d,**kw))
    assert response.status_code==200,response.text
    return response.json()


def test_idea_review_opening_chapter_one_attempt_each(env):
    client,app=env;d,payload=draft(client)
    # Authored transport fixture: verifies routing/persistence, not model compliance.
    scene = ('Лена прислушивается к стуку.\n\n---\n\n### Варианты действий\n\n'
             '1. **Спросить гостя:** «Кто там?»\n2. **Осмотреть окно:** проверить раму.\n'
             '3. **Спросить Лену:** «Ты ждёшь гостей?»\n4. **Подождать:** остаться у стола.\n\n'
             '**Свободный ввод:** свой вариант.\n\n---\n\n### Текущая сцена\n\n'
             '**Время:** 9 октября, точное время не установлено.\n\n'
             '**Место:** комната у маяка.\n\n**Рядом:** Лена, стол, стук за дверью.')
    def stream(**kw):
        text = TEMPLATE if INITIAL_PROMPT in kw['messages'][0]['content'] else scene
        return provider(text)(**kw)
    with patch('llm.chat_stream',side_effect=stream) as transport, \
         patch('engine.submit',side_effect=AssertionError('Narrative forbidden')), \
         patch('engine.chat_stream',side_effect=AssertionError('Extraction forbidden')):
        request=body(d,kind='initial')
        result=client.post(cp(d,'/generate'),json=request).json();j=finish(client,d,result)
        assert j['status']=='complete' and transport.call_count==1
        assert client.post(cp(d,'/generate'),json=request).json()['id']==j['id']
        assert client.get('/api/chat/campaigns').json()==[]
        assert j['usage'][0]['input_tokens']==321
        with app.state.repository.connect() as db:
            sent=json.loads(db.execute('SELECT context_json FROM chat_creation_jobs WHERE id=?',(j['id'],)).fetchone()[0])
            assert INITIAL_PROMPT in sent[0]['content'] and TEMPLATE in sent[0]['content']
            assert SUMMARY_PROMPT not in sent[0]['content']
            assert payload['idea']==sent[1]['content']
        d=current(client,d)
        edit={**payload,**body(d), 'text':TEMPLATE+'\nАвтор сохранил дату 9 октября.'}
        saved=client.put(cp(d),json=edit);assert saved.status_code==200,saved.text
        d=saved.json()
        c=approve(client,d);opening=wait(client,c,c['job'])
        assert opening['kind']=='start' and opening['status']=='complete'
        assert transport.call_count==2
        assert approve(client,d)['id']==c['id'] and transport.call_count==2
        messages=client.get(url(c,'/messages')).json()['messages']
        assert len(messages)==1 and messages[0]['role']=='assistant'
        assert messages[0]['content']==scene and opening['response']==scene
        assert c['memory']['text']==edit['text']
        with app.state.repository.connect() as db:
            ctx=json.loads(db.execute('SELECT context_json FROM chat_jobs WHERE id=?',(opening['id'],)).fetchone()[0])
            assert RP_PROMPT in ctx[0]['content'] and OPENING_PROMPT in ctx[0]['content']
            assert len(ctx)==2 and 'Авторская память' in ctx[1]['content']
            assert db.execute('SELECT COUNT(*) FROM game_jobs').fetchone()[0]==0
        c=state(client,c)
        duplicate=client.post(url(c,'/generate'),json=body(c,kind='start'))
        assert duplicate.status_code==409 and transport.call_count==2
        reply=generate(client,c,text='Я спрашиваю о маяке.')
        assert transport.call_count==3
        sent=transport.call_args.kwargs['messages']
        assert RP_PROMPT in sent[0]['content'] and OPENING_PROMPT not in sent[0]['content']
        assert reply['response']==scene
        c=state(client,c)
    c,summary=checkpoint(client,c,text=TEMPLATE)
    assert len(c['chapters'])==2
    with app.state.repository.connect() as db:
        ctx=json.loads(db.execute('SELECT context_json FROM chat_jobs WHERE id=?',(summary['id'],)).fetchone()[0])
        assert SUMMARY_PROMPT in ctx[0]['content'] and INITIAL_PROMPT not in ctx[0]['content']
        assert any(m['content']==scene for m in ctx)
    assert c['memory']['text']==TEMPLATE  # Game footer is not appended to memory by the engine.
    with patch('llm.chat_stream',side_effect=provider(scene)) as transport:
        generate(client,c,text='Продолжим разговор.')
        assert transport.call_count==1
        assert RP_PROMPT in transport.call_args.kwargs['messages'][0]['content']
    with app.state.repository.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM chat_messages').fetchone()[0]==5


def test_partial_continue_edit_cas_and_no_campaign_until_confirmation(env):
    client,app=env;d,p=draft(client)
    with patch('llm.chat_stream',side_effect=provider('ГЛАВНОЕ СЕЙЧАС\nДата: 9 октября.',finish='length')):
        j=initial(client,d)
    assert j['status']=='length';d=current(client,d)
    assert client.post(cp(d,'/confirm'),json=body(d)).status_code==409
    assert client.get('/api/chat/campaigns').json()==[]
    with patch('llm.chat_stream',side_effect=provider('\n'+TEMPLATE)) as io:
        j=initial(client,d,'continue')
        assert io.call_count==1 and j['response'].startswith('ГЛАВНОЕ СЕЙЧАС')
    d=current(client,d);assert len(d['jobs'])==2 and d['status']=='complete'
    edit={**p,**body(d),'text':d['text']+'\nИсправлено.'}
    assert client.put(cp(d),json=edit).status_code==200
    assert client.put(cp(d),json={**edit,'token':tok()}).status_code==409
    assert client.post(cp(d,'/confirm'),json=body(d)).status_code==409
    assert client.get('/api/chat/campaigns').json()==[]


def test_incomplete_stop_finish_and_opening_retry_variants(env):
    client,app=env;d,p=draft(client)
    with patch('llm.chat_stream',side_effect=provider('Только короткий абзац.')):
        j=initial(client,d)
    assert j['status']=='incomplete';d=current(client,d)
    assert client.post(cp(d,'/confirm'),json=body(d)).status_code==409
    # Author explicitly repairs and accepts, no automatic semantic repair.
    d=client.put(cp(d),json={**p,**body(d),'text':TEMPLATE}).json()
    with patch('llm.chat_stream',side_effect=provider('Начало…',finish='length')):
        c=approve(client,d,accept_partial=True);j=wait(client,c,c['job'])
    assert j['status']=='length'
    c=state(client,c)
    assert client.post(url(c,'/generate'),json=body(c,kind='reply',text='Я отвечаю')).status_code==409
    with patch('llm.chat_stream',side_effect=provider()) as io:
        j=generate(client,c,'retry','',target=j['id']);assert io.call_count==1
        c=state(client,c)
        j=generate(client,c,'regenerate','',target=j['output_id']);assert io.call_count==2
    c=state(client,c)
    assert len(c['branches'])==3 and c['branch']['head']==1
    assert [m['role'] for m in client.get(url(c,'/messages')).json()['messages']]==['assistant']
    with app.state.repository.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM chat_messages').fetchone()[0]==3


def test_ready_creation_restart_and_reservation_recovery(env):
    client,app=env;d,p=draft(client,idea='')
    with patch('llm.chat_stream',side_effect=provider()) as io:
        c=approve(client,d);wait(client,c,c['job']);assert io.call_count==1
        app.state.chat.recover()
        assert current(client,d)['campaign_id']==c['id']
        assert state(client,c)['branch']['head']==1
        assert io.call_count==1
    # A reserved initial request interrupted before a worker starts never retries on recovery.
    d,p=draft(client)
    jid,_=app.state.chat.creations.reserve(d['id'],body(d,kind='initial'))
    app.state.chat.recover()
    assert client.get(cp(d,'/jobs/'+jid)).json()['status']=='interrupted'
    assert current(client,d)['status']=='interrupted'


def test_capabilities_are_free_explicit_and_bound_models(env):
    client,app=env
    with patch('llm.chat_stream',side_effect=AssertionError('No probing inference')):
        config=ModelSettings(provider='deepseek',model='deepseek-flash',auto_context=True,auto_output=True).model_dump()
        assert client.post('/api/chat/capabilities',json=config).json()['context_length']==1000000
        assert capabilities.resolve(config,None)['context_length']==1000000
        assert capabilities.resolve(dict(config,auto_context=False,context_length=2000000),None)['context_length']==1000000
        unknown=dict(config,model='unverified-model')
        import pytest
        with pytest.raises(ValueError,match='неизвестен'):capabilities.resolve(unknown,None)
        metadata={'models':[{'key':'local-a','max_context_length':999999,'loaded_instances':[{'id':'a','config':{'context_length':16384}},{'id':'b','config':{'context_length':8192}}]}]}
        with patch('llm.get_models_info',return_value=metadata):
            assert capabilities.discover('local','local-a',None)['context_length']==8192
            assert capabilities.discover('local','a',None)['context_length']==16384
            assert capabilities.discover('local','unknown',None)['context_length'] is None
        with patch('llm.get_models_info',return_value={'models':[{'key':'x','max_context_length':100000}]}):
            assert capabilities.discover('local','x',None)['context_length'] is None


def test_cancel_initial_late_result_cross_scope_and_restart(env):
    import threading
    from fastapi.testclient import TestClient
    from backend.api.app import create_app
    client,app=env;d,p=draft(client);other,_=draft(client)
    started=threading.Event();release=threading.Event()
    def stream(**kw):
        yield 'Сохранённое начало'
        started.set();release.wait(5)
        yield 'ПОЗДНИЙ ТЕКСТ'
        kw['on_finish']('stop')
    with patch('llm.chat_stream',side_effect=stream) as io:
        j=client.post(cp(d,'/generate'),json=body(d,kind='initial')).json()
        assert started.wait(3)
        assert client.post(cp(other,'/jobs/'+j['id']+'/stop'),json={}).status_code==409
        assert client.post(cp(d,'/jobs/'+j['id']+'/stop'),json={}).json()['status']=='stopped'
        release.set()
        for _ in range(100):
            if j['id'] not in app.state.chat.workers:break
            time.sleep(.01)
        assert io.call_count==1
    saved=current(client,d)
    assert saved['text']=='Сохранённое начало'
    with patch('llm.chat_stream',side_effect=AssertionError('No restart inference')):
        with TestClient(create_app(app.state.repository.path)) as reopened:
            assert current(reopened,d)['text']==saved['text']
            assert current(reopened,d)['status']=='stopped'
            assert reopened.get('/api/chat/campaigns').json()==[]


def test_confirmation_rolls_back_campaign_when_start_does_not_fit(env):
    client,app=env;d,p=draft(client,idea='')
    p['settings']['reply'].update(auto_output=False,max_tokens=4096,context_length=8192)
    p['text']='Большой документ '*10000
    response=client.put(cp(d),json={**p,**body(d)})
    assert response.status_code==200;d=response.json()
    with patch('llm.chat_stream',side_effect=AssertionError('Overflow must not call provider')):
        assert client.post(cp(d,'/confirm'),json=body(d)).status_code==409
    assert client.get('/api/chat/campaigns').json()==[]
    assert current(client,d)['text']==p['text']


def test_additive_v2_migration_preserves_legacy_chat_and_narrative(env):
    from test_chat_mode import create
    from backend.chat.repository import ChatRepository
    client,app=env;c=create(client)
    with patch('llm.chat_stream',side_effect=provider()):generate(client,c)
    with app.state.repository.connect() as db:
        messages=[tuple(r) for r in db.execute('SELECT * FROM chat_messages')]
        for table in ('chat_creation_operations','chat_creation_jobs','chat_creations'):
            db.execute('DROP TABLE '+table)
        db.execute('ALTER TABLE chat_campaigns DROP COLUMN opening_required')
        db.execute("DELETE FROM schema_migrations WHERE name='chat_creation_v2'")
        cfg=db.execute('SELECT id,payload FROM chat_configs').fetchone()
        value=json.loads(cfg['payload'])
        for stage in ('reply','summary'):
            value[stage].pop('auto_context');value[stage].pop('auto_output')
        db.execute('UPDATE chat_configs SET payload=? WHERE id=?',(json.dumps(value),cfg['id']))
    repo=ChatRepository(app.state.repository)
    assert repo.state(c['id'])['opening_required']==0
    legacy=repo.state(c['id'])
    assert legacy['settings']['reply']['auto_context'] is False
    assert legacy['settings']['summary']['auto_output'] is False
    saved=client.put(url(c,'/settings'),json=body(legacy,settings=legacy['settings']))
    assert saved.status_code==200,saved.text
    with repo.connect() as db:assert [tuple(r) for r in db.execute('SELECT * FROM chat_messages')]==messages
    with patch('llm.chat_stream',side_effect=provider()) as io:
        generate(client,state(client,c));assert io.call_count==1


def test_small_model_switch_blocks_before_transport_and_recomputes_budget(env):
    client,app=env;d,p=draft(client,idea='')
    with patch('llm.chat_stream',side_effect=provider()):c=approve(client,d);wait(client,c,c['job'])
    c=state(client,c)
    settings=c['settings'];settings['reply'].update(model='small',auto_context=True,auto_output=True)
    metadata={'models':[{'key':'small','loaded_instances':[{'id':'small','config':{'context_length':8192}}]}]}
    with patch('llm.get_models_info',return_value=metadata),patch('llm.chat_stream',side_effect=AssertionError('No overflowing calls')):
        r=client.put(url(c,'/settings'),json=body(c,settings=settings));assert r.status_code==200,r.text
        c=r.json();assert c['budgets']['reply']['context_length']==8192
        assert c['settings']['reply']['max_tokens']==2730
        rejected=client.post(url(c,'/generate'),json=body(c,kind='reply',text='Очень большой ввод '*2000))
        assert rejected.status_code==409
        assert state(client,c)['branch']['head']==1


def test_retry_rechecks_loaded_window_without_calling_provider(env):
    from test_chat_mode import create
    import threading
    client,app=env;c=create(client)
    jid,_=app.state.chat.reserve(c['id'],body(c,kind='reply',text='Шум '+('!?'*5000)))
    # Reservation fits the recorded window; loaded instance shrinks before execution.
    with patch('backend.chat.capabilities.discover',return_value={'context_length':2048}),patch('llm.chat_stream') as io:
        app.state.chat.run(c['id'],jid,threading.Event())
        assert io.call_count==0
    assert client.get(url(c,'/jobs/'+jid)).json()['status']=='error'


def test_compatible_metadata_never_guesses_from_training_maximum(env, monkeypatch):
    from unittest.mock import MagicMock
    import llm
    monkeypatch.setitem(llm.PROVIDERS, 'compatible', llm.ProviderSpec('https://fixture.invalid/v1', 'COMPATIBLE_API_KEY'))
    client,app=env
    model=MagicMock();model.id='remote';model.model_dump.return_value={'id':'remote','max_context_length':200000}
    transport=MagicMock();transport.models.list.return_value.data=[model]
    with patch('llm.OpenAI') as ctor:
        ctor.return_value.__enter__.return_value=transport
        assert capabilities.discover('compatible','remote',app.state.chat.credentials)['context_length'] is None
        model.model_dump.return_value={'id':'remote','context_length':32768,'context_window':16384}
        assert capabilities.discover('compatible','remote',app.state.chat.credentials)['context_length']==16384
        config=ModelSettings(provider='compatible',model='remote',auto_context=False,context_length=131072).model_dump()
        assert capabilities.resolve(config,app.state.chat.credentials)['context_length']==16384
        monkeypatch.setenv('COMPATIBLE_MODEL_LIMITS', json.dumps({'https://fixture.invalid/v1':{'remote':{'context_length':65536,'max_output':512}}}))
        model.model_dump.return_value.update(max_output_tokens=1024)
        bounded = capabilities.discover('compatible','remote',app.state.chat.credentials)
        assert (bounded['context_length'], bounded['max_output']) == (16384, 512)
        assert not transport.chat.completions.create.called


def test_warning_reserves_next_reply_before_summary_overflow(env):
    from test_chat_mode import create
    client,app=env;c=create(client)
    found=None
    for size in range(100,10000,100):
        b=client.post(url(c,'/budget'),json=body(c,text='а'*size)).json()
        if b['warning'] and b['summary']['ratio']<.85 and b['reply']['ratio']<.85:
            found=b;break
    assert found and found['summary']['fits'] and found['reply']['fits']
    assert found['summary']['next_reply_reserve']==c['settings']['reply']['max_tokens']+64


def test_cancel_between_reservation_and_worker_start_never_calls_provider(env):
    import threading
    from test_chat_mode import create
    client,app=env
    d,_=draft(client)
    initial_id,_=app.state.chat.creations.reserve(d['id'],body(d,kind='initial'))
    c=create(client)
    opening_id,_=app.state.chat.reserve(c['id'],body(c,kind='start',text=''))
    for owner,jid in ((d['id'],initial_id),(c['id'],opening_id)):
        app.state.chat.stop(owner,jid)  # Another request cancels before launch registers its Event.
        with patch('llm.chat_stream',side_effect=provider(TEMPLATE)) as io:
            app.state.chat.run(owner,jid,threading.Event())
            assert io.call_count==0
        assert app.state.chat.job(owner,jid)['status']=='stopped'


def test_new_ui_defaults_auto_but_legacy_api_payload_stays_manual(env):
    client,app=env
    settings=client.get('/api/chat/defaults').json()['settings']
    for stage in ('reply','summary'):
        assert settings[stage]['auto_context'] and settings[stage]['auto_output']
        settings[stage].pop('auto_context');settings[stage].pop('auto_output')
        settings[stage]['model']='legacy-model'
    response=client.post('/api/chat/campaigns',json=dict(token=tok(),name='Legacy API',memory=MEMORY,settings=settings))
    assert response.status_code==200,response.text
    assert response.json()['settings']['reply']['auto_context'] is False
    assert response.json()['settings']['summary']['auto_output'] is False
