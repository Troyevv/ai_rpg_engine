"""Issue #262: real API/service/SQLite; only external provider IO is replaced."""
import copy
import json
from unittest.mock import patch

import pytest

from backend.chat.documents import characters, changes, patch_character
from backend.chat.repository import ChatRepository
from backend.repositories.preparation import Repository
from test_chat_mode import env, create, state, url, body, provider, generate, checkpoint

MEMORY='''# ВЫЖИМКА

## ГЛАВНЫЙ ГЕРОЙ

### 👤 Илья

- **Внешность:** тёмные волосы.
- **Характер:** сдержанный.

## КЛЮЧЕВЫЕ NPC

### 👤 Лена

- **Внешность:** рыжие волосы.
- **Манера речи:** короткие фразы.

#### Знания

- **Знает:** ключ под камнем.
- **Не знает:** кто стучал.

#### Текущее состояние

- **Чего хочет:** вернуть книгу.

## ОТНОШЕНИЯ

Лена → Илья: доверяет. Илья → Лена: подозревает.

## ЧТО ЗНАЮТ / ЧТО ТАЙНА

Ключ под камнем. Знает только Лена.

## ХРОНОЛОГИЯ

12 мая 2010 — рождение Лены.
'''


def mark(client,c,message,**kw):
    response=client.put(url(c,'/bookmarks'),json=body(c,branch=c['active_branch'],message=message,**kw))
    assert response.status_code==200,response.text
    return response.json()


def test_bookmarks_migration_idempotency_prefix_scope_and_restart(env):
    client,app=env;c=create(client,memory=MEMORY)
    with patch('llm.chat_stream',side_effect=provider()):
        generate(client,c);c=state(client,c);generate(client,c)
    c=state(client,c);original=c['active_branch'];messages=client.get(url(c,'/messages')).json()['messages']
    request=body(c,branch=original,message=messages[1]['id'],note='Важное ЗНАНИЕ',priority=2)
    first=client.put(url(c,'/bookmarks'),json=request);assert first.status_code==200
    assert client.put(url(c,'/bookmarks'),json=request).status_code==200
    c=first.json();c=mark(client,c,messages[3]['id'])
    assert len(client.get(url(c,'/bookmarks?q=знание')).json()['items'])==1
    result=client.post(url(c,'/edit'),json=body(c,branch=original,message=messages[3]['id'],text='Другой исход.'))
    assert result.status_code==200,result.text
    c=result.json();visible=client.get(url(c,'/bookmarks')).json()['items']
    assert [b['message_id'] for b in visible]==[messages[1]['id']]
    assert client.get(url(c,f"/messages/{messages[3]['id']}/locate")).status_code!=200
    page=client.get(url(c,'/messages')).json()['messages']
    assert page[1]['bookmark']['priority']==2 and page[-1]['bookmark'] is None
    other=create(client,memory=MEMORY)
    assert client.put(url(other,'/bookmarks'),json=body(other,branch=original,message=messages[1]['id'])).status_code!=200
    reopened=ChatRepository(Repository(app.state.repository.path));reopened.migrate()
    assert reopened.bookmarks(c['id'])['items']==visible
    with reopened.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM chat_bookmarks WHERE campaign_id=?',(c['id'],)).fetchone()[0]==2
        assert db.execute("SELECT COUNT(*) FROM schema_migrations WHERE name='chat_bookmarks_v3'").fetchone()[0]==1
    c=mark(client,c,messages[1]['id'],enabled=False)
    assert reopened.bookmarks(c['id'],original)['items'][0]['message_id']==messages[3]['id']


def test_summary_uses_selected_branch_bookmarks_and_never_replays_choices(env):
    client,app=env;c=create(client,memory=MEMORY)
    response='Лена закрыла дверь.\n\n### Варианты действий\n\n1. Украсть ключ.\n2. Уйти.\n3. Спросить.\n4. Ждать.'
    with patch('llm.chat_stream',side_effect=provider(response)): generate(client,c)
    c=state(client,c);message=client.get(url(c,'/messages')).json()['messages'][-1]
    c=mark(client,c,message['id'],note='Важно: ключ не украден.',priority=2)
    with patch('llm.chat_stream',side_effect=provider(MEMORY)) as io:
        generate(client,c,'summary','')
    context=io.call_args.kwargs['messages'];joined='\n'.join(x['content'] for x in context)
    assert joined.count(response)==1 # references, not duplicate quotes for uncovered messages
    assert 'Важно: ключ не украден.' in joined and 'не совершены' in context[0]['content']
    assert io.call_count==1
    c=state(client,c);c=mark(client,c,message['id'],priority=0)
    assert c['budgets']['summary']['bookmarks_included']==0
    assert c['budgets']['summary']['bookmarks_excluded']==1
    with patch('llm.chat_stream',side_effect=provider()) as io: generate(client,c)
    assert 'Важно: ключ не украден.' not in json.dumps(io.call_args.kwargs['messages'],ensure_ascii=False)


def test_long_history_jump_is_bounded_and_bidirectional(env):
    client,app=env;c=create(client)
    r=app.state.chat.repo
    with r.transaction() as db:
        b=r.branch(db,c['id']);ids=[r.add_message(db,c['id'],b,'assistant',f'Сообщение {i}') for i in range(1100)]
    c=state(client,c);c=mark(client,c,ids[500],note='Опорная дата')
    location=client.get(url(c,f'/messages/{ids[500]}/locate')).json()
    assert location['seq']==501
    page=client.get(url(c,f"/messages?before=522&chapter={location['chapter']}")).json()
    assert len(page['messages'])==40 and page['more'] and page['more_after']
    assert ids[500] in [m['id'] for m in page['messages']]
    following=client.get(url(c,f"/messages?after={page['messages'][-1]['seq']}")).json()
    assert len(following['messages'])==40 and following['messages'][0]['seq']==522


def test_character_views_source_fidelity_and_cas(env):
    client,app=env;c=create(client,memory=MEMORY.replace('\n','\r\n'))
    library=client.get(url(c,'/characters?q=ЛЕНА')).json();assert library['total']==1
    key=library['items'][0]['key'];card=client.get(url(c,f'/characters/{key}')).json()
    assert card['name']=='Лена' and any(f['label']=='Знает' and 'ключ' in f['value'] for f in card['fields'])
    assert 'Илья → Лена' not in card['text'] # directed relationships stay their own source
    edited=card['text'].replace('рыжие волосы','короткие рыжие волосы')
    request=body(c,branch=c['active_branch'],memory_id=c['memory']['id'],text=edited)
    result=client.post(url(c,f'/characters/{key}/draft'),json=request);assert result.status_code==200,result.text
    assert client.post(url(c,f'/characters/{key}/draft'),json=request).json()==result.json()
    c=state(client,c);d=client.get(url(c,'/drafts/'+result.json()['draft'])).json()
    assert d['text']==c['memory']['text'].replace('рыжие волосы','короткие рыжие волосы')
    assert c['memory']['text']==MEMORY.replace('\n','\r\n')
    confirmed=client.post(url(c,'/drafts/'+d['id']+'/confirm'),json=body(c,text=d['text'],next_chapter=False))
    assert confirmed.status_code==200,confirmed.text
    current=confirmed.json();stale=dict(request,token='different-token',revision=current['revision'])
    assert client.post(url(c,f'/characters/{key}/draft'),json=stale).status_code!=200
    assert state(client,c)['memory']['text']==d['text']
    assert client.get(url(c,'/characters')).json()['memory_id']==current['memory']['id']


def test_unknown_markdown_is_source_not_invented_cards():
    source='Лена упомянута в письме.\n\n```md\n## КЛЮЧЕВЫЕ NPC\n👤 Поддельный\n```\n\n> 👤 Цитата\n'
    assert characters(source)['cards']==[]
    assert characters(source)['sources'][0]['text']==source
    legacy='КЛЮЧЕВЫЕ NPC\n\n👤 Ёж 🦔\n· Внешность: иглы.\nЗнания\n· Не знает: дату.\n\nМИР\nЛес.'
    view=characters(legacy);assert len(view['cards'])==1
    assert view['cards'][0]['name']=='Ёж 🦔'
    assert patch_character(legacy,view['cards'][0]['key'],view['cards'][0]['text'])==legacy
    assert changes('Слух: дверь закрыта.','Дверь закрыта.')['groups']==[]
    diff=changes('одинаково\nодинаково\n','одинаково\n')
    assert sum(l['kind']=='removed' for h in diff['hunks'] for l in h['lines'])==1


def test_history_is_branch_lineage_and_persists_provenance(env):
    client,app=env;c=create(client,memory=MEMORY)
    with patch('llm.chat_stream',side_effect=provider()): generate(client,c)
    c=state(client,c);original=c['active_branch'];message=client.get(url(c,'/messages')).json()['messages'][0]
    c,job=checkpoint(client,c,MEMORY.replace('вернуть книгу','книга возвращена'))
    accepted=c['memory']['id']
    detail=client.get(url(c,'/history/'+accepted)).json()
    assert detail['previous']['text']==MEMORY and detail['provenance']['job_id']==job['id']
    assert detail['changes']['groups'][0]['title']=='КЛЮЧЕВЫЕ NPC'
    fork=client.post(url(c,'/edit'),json=body(c,branch=original,message=message['id'],text='Я ухожу.')).json()
    history=client.get(url(fork,'/history')).json()
    assert accepted not in [m['id'] for m in history['items']]
    assert client.get(url(fork,'/history/'+accepted)).status_code!=200
    assert client.get(url(fork,f'/history/{accepted}?branch={original}')).status_code==200
    reopened=ChatRepository(Repository(app.state.repository.path))
    assert reopened.history(fork['id'])==history


def test_archived_bookmark_budget_is_explicit_and_exclusion_is_user_controlled(env):
    client,app=env;c=create(client,memory=MEMORY)
    with patch('llm.chat_stream',side_effect=provider('Старый документ. '+('Подробности. '*1800))): generate(client,c)
    c=state(client,c);message=client.get(url(c,'/messages')).json()['messages'][-1]
    settings=copy.deepcopy(c['settings']);settings['summary']['context_length']=262144
    c=client.put(url(c,'/settings'),json=body(c,settings=settings)).json()
    c,_=checkpoint(client,c,MEMORY)
    settings=copy.deepcopy(c['settings']);settings['summary']['context_length']=32768
    c=client.put(url(c,'/settings'),json=body(c,settings=settings)).json()
    c=mark(client,c,message['id'],note='Архивное свидетельство',priority=2)
    assert not c['budgets']['summary']['fits']
    with patch('llm.chat_stream') as io:
        blocked=client.post(url(c,'/generate'),json=body(c,kind='summary',text=''))
        assert blocked.status_code!=200 and io.call_count==0
    assert client.get(url(c,'/bookmarks')).json()['items'][0]['priority']==2
    settings=copy.deepcopy(c['settings']);settings['summary']['context_length']=262144
    c=client.put(url(c,'/settings'),json=body(c,settings=settings)).json()
    with patch('llm.chat_stream',side_effect=provider(MEMORY)) as io: generate(client,c,'summary','')
    context=io.call_args.kwargs['messages'];serialized=json.dumps(context,ensure_ascii=False)
    assert 'Архивное свидетельство' in serialized and 'quoted_message' in serialized
    assert serialized.count('Старый документ.')==1
    c=state(client,c);c=mark(client,c,message['id'],priority=0)
    assert c['budgets']['summary']['bookmarks_excluded']==1


def test_bookmark_race_and_failed_write_are_atomic(env):
    client,app=env;c=create(client)
    with patch('llm.chat_stream',side_effect=provider()): generate(client,c)
    c=state(client,c);message=client.get(url(c,'/messages')).json()['messages'][-1]
    stale=body(c,branch=c['active_branch'],message=message['id'],note='Проигравшая запись',priority=1)
    c=mark(client,c,message['id'],note='Первая запись',priority=2)
    assert client.put(url(c,'/bookmarks'),json=stale).status_code!=200
    r=app.state.chat.repo;before=c['revision']
    request=body(c,branch=c['active_branch'],message=message['id'],note='Не должно сохраниться',priority=0,enabled=True)
    with patch.object(r,'record',side_effect=RuntimeError('simulated SQLite commit failure')):
        with pytest.raises(RuntimeError,match='commit failure'): r.bookmark(c['id'],request)
    assert state(client,c)['revision']==before
    assert r.bookmarks(c['id'])['items'][0]['note']=='Первая запись'
    # A fresh retry of the same request is safe after rollback.
    r.bookmark(c['id'],request)
    assert r.bookmarks(c['id'])['items'][0]['note']=='Не должно сохраниться'


def test_character_draft_write_rollback_preserves_memory_and_versions(env):
    client,app=env;c=create(client,memory=MEMORY);r=app.state.chat.repo
    card=client.get(url(c,'/characters?q=Лена')).json()['items'][0]
    value=r.character(c['id'],card['key'])
    with r.connect() as db: before=db.execute('SELECT COUNT(*) FROM chat_drafts').fetchone()[0]
    request=body(c,branch=c['active_branch'],memory_id=c['memory']['id'],text=value['text'].replace('рыжие','тёмные'))
    with patch.object(r,'record',side_effect=RuntimeError('write failure')):
        with pytest.raises(RuntimeError): r.edit_character(c['id'],card['key'],request)
    with r.connect() as db: assert db.execute('SELECT COUNT(*) FROM chat_drafts').fetchone()[0]==before
    assert state(client,c)['memory']['text']==MEMORY
    assert state(client,c)['revision']==c['revision']


def test_character_groups_keep_multiline_and_unknown_fields_without_inference():
    text=MEMORY.replace('- **Манера речи:** короткие фразы.', '- **Манера речи:** короткие фразы.\n  Иногда цитирует стихи.\n\nНеобычное авторское поле: текст без схемы.')
    card=next(c for c in characters(text)['cards'] if c['name']=='Лена')
    presented='\n'.join(b['text'] for b in card['blocks'])
    assert 'Иногда цитирует стихи.' in presented
    assert 'Необычное авторское поле: текст без схемы.' in presented
    assert 'кто стучал' in presented
    assert patch_character(text,card['key'],card['text'])==text
    # Same names remain distinct exact source spans, never merged by identity guessing.
    duplicate=text.replace('## ОТНОШЕНИЯ','### 👤 Лена\n\n- **Внешность:** другой человек.\n\n## ОТНОШЕНИЯ')
    cards=[c for c in characters(duplicate)['cards'] if c['name']=='Лена']
    assert len(cards)==2 and cards[0]['key']!=cards[1]['key']


def test_concurrent_bookmark_cas_has_one_winner(env):
    from concurrent.futures import ThreadPoolExecutor
    client,app=env;c=create(client)
    with patch('llm.chat_stream',side_effect=provider()): generate(client,c)
    c=state(client,c);r=app.state.chat.repo;message=client.get(url(c,'/messages')).json()['messages'][-1]
    def write(note):
        try:
            r.bookmark(c['id'],body(c,branch=c['active_branch'],message=message['id'],enabled=True,note=note,priority=1))
            return True
        except ValueError:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(write,['Первая вкладка','Вторая вкладка']))
    assert sorted(results)==[False,True]
    assert state(client,c)['revision']==c['revision']+1
    assert len(r.bookmarks(c['id'])['items'])==1


def test_legacy_schema_upgrade_and_regeneration_preserve_original_sources(env):
    client,app=env;c=create(client,memory=MEMORY);r=app.state.chat.repo
    with patch('llm.chat_stream',side_effect=provider()): generate(client,c)
    c=state(client,c);original=c['active_branch'];before=r.page(c['id'])
    # Explicitly reconstruct the pre-v3 schema in this disposable fixture DB.
    with r.transaction() as db:
        db.execute('DROP TABLE chat_bookmarks')
        db.execute("DELETE FROM schema_migrations WHERE name='chat_bookmarks_v3'")
    r.migrate();r.migrate()
    assert r.page(c['id'])==before
    for message in before['messages']: c=mark(client,c,message['id'],note=message['role'])
    with patch('llm.chat_stream',side_effect=provider('Другой ответ.')) as io:
        generate(client,c,'regenerate','',target=before['messages'][-1]['id'])
    c=state(client,c)
    assert io.call_count==1
    assert [b['role'] for b in r.bookmarks(c['id'])['items']]==['user']
    assert len(r.bookmarks(c['id'],original)['items'])==2
    assert r.page(c['id'])['messages'][-1]['bookmark'] is None
