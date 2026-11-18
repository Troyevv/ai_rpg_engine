"""One explicit provider attempt per job. Existing transport, credentials and accounting."""
import json
import sqlite3
import threading
from contextlib import nullcontext

from backend.chat import capabilities
from backend.chat.creation import CreationStore, missing_sections

import llm
from backend.chat.context import assemble, require_fit, OPENING_PROMPT
from backend.chat.repository import dump, row, uid
from backend.services.coordinator import model_lease
from backend.services.usage import tracked_stream


class ChatService:
    def __init__(self, repository, credentials):
        self.repo = repository
        self.credentials = credentials
        self.creations = CreationStore(repository, credentials)
        self.workers = {}
        self.lock = threading.Lock()

    def reserve(self, cid, body, db=None, resolved=None):
        r = self.repo
        with r.transaction() if db is None else nullcontext(db) as db:
            fp, previous = r.operation(db, cid, body['token'], body)
            if previous: return previous['job'], False
            r.guard(db, cid, body['revision'])
            b, m, settings, tail, messages = r.inputs(db, cid)
            kind = body['kind']
            if resolved: settings = resolved
            if kind in ('retry', 'regenerate'):
                if kind == 'retry':
                    original = row(db, 'chat_jobs', body['target'], cid)
                else:
                    target = row(db, 'chat_messages', body['target'], cid)
                    if target['role'] != 'assistant' or not target['job_id']:
                        raise ValueError('Для этого сообщения нет записанного контекста генерации.')
                    original = row(db, 'chat_jobs', target['job_id'], cid)
                if original['status'] == 'running': raise ValueError('Запрос ещё выполняется.')
                if original['kind'] == 'summary':
                    raise ValueError('Обновите выжимку отдельной кнопкой из актуального состояния.')
                # Exact original context/settings, no later memory, prompt or suffix.
                b = r.fork(db, cid, original['branch_id'], original['head']-1,
                           memory=original['memory_id'], config=original['config_id'])
                context, config = json.loads(original['context_json']), json.loads(original['config_json'])
                m = row(db, 'chat_memories', b['memory_id'], cid)
            else:
                if any(message['status'] != 'complete' for message in messages):
                    raise ValueError('Есть незавершённый ответ. Повторите его или явно примите текст через редактирование.')
                if kind == 'start' and b['head']:
                    raise ValueError('Стартовая сцена уже запрошена. Используйте регенерацию или повтор существующего запроса.')
                if kind in ('reply','summary') and r.campaign(db,cid)['opening_required']:
                    first = r.messages(db,b['id'],through=1)
                    if not first or first[0]['role']!='assistant' or first[0]['status']!='complete':
                        raise ValueError('Сначала завершите стартовую сцену: повторите запрос или явно примите текст через редактирование.')
                if kind == 'reply':
                    if not body['text'].strip(): raise ValueError('Введите сообщение.')
                    messages.append({'role':'user','content':body['text']})
                bookmarks = r.summary_bookmarks(db,cid,b['id']) if kind=='summary' else ()
                context = assemble(settings, m['text'], tail, messages, summary=kind=='summary',bookmarks=bookmarks)
                if kind=='start': context[0]['content'] += '\n\n'+OPENING_PROMPT
                config = settings['summary' if kind=='summary' else 'reply']
            if not config['model'].strip(): raise ValueError('Выберите модель в настройках RP-чата.')
            require_fit(context, config)
            jid = 'chat_' + uid()
            if kind == 'reply': r.add_message(db, cid, b, 'user', body['text'])
            if kind == 'summary':
                output = uid()
                db.execute('''INSERT INTO chat_drafts(id,campaign_id,branch_id,source_revision,head,parent_id,config_id,cutoff,text,original,status,job_id,next_chapter)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''', (output,cid,b['id'],body['revision']+1,b['head'],m['id'],b['config_id'],b['head'],'','','running',jid,int(body.get('next_chapter',False))))
            else:
                output = r.add_message(db, cid, b, 'assistant', '', 'running', jid)
            db.execute('''INSERT INTO chat_jobs(id,campaign_id,branch_id,kind,source_revision,head,memory_id,config_id,context_json,config_json,output_id)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)''', (jid,cid,b['id'],kind,body['revision']+1,b['head'],m['id'],b['config_id'],dump(context),dump(config),output))
            r.record(db, cid, body['token'], fp, {'job':jid})
            return jid, True

    def launch(self, cid, jid, fresh):
        if fresh:
            event = threading.Event()
            with self.lock: self.workers[jid] = {'event':event,'stream':None}
            threading.Thread(target=self.run, args=(cid,jid,event), daemon=True).start()
        return self.job(cid, jid)

    def job(self, cid, jid):
        return self.creations.job(cid,jid) if cid.startswith('creation_') else self.repo.job(cid,jid)

    def start(self, cid, body):
        if cid.startswith('creation_'):
            jid,fresh = self.creations.reserve(cid,body)
        else:
            with self.repo.connect() as db:
                _,old = self.repo.operation(db,cid,body['token'],body)
                settings = self.repo.inputs(db,cid)[2]
            if old: return self.repo.job(cid,old['job'])
            resolved = capabilities.settings(settings,self.credentials) if body['kind'] not in ('retry','regenerate') else None
            jid,fresh = self.reserve(cid,body,resolved=resolved)
        return self.launch(cid,jid,fresh)

    def confirm_creation(self, cid, body):
        with self.repo.connect() as db:
            d = row(db,'chat_creations',cid)
            if d['campaign_id']: return self.repo.state(d['campaign_id'])
            value = json.loads(d['payload'])
        settings = capabilities.settings(value['settings'],self.credentials)
        with self.repo.transaction() as db:
            d = row(db,'chat_creations',cid)
            if d['campaign_id']:
                campaign = d['campaign_id']; jid = None; fresh = False
            else:
                d = self.creations.guard(db,cid,body['revision'])
                if not d['text'].strip(): raise ValueError('Выжимка пуста.')
                if d['job_id'] and (d['status']!='complete' or missing_sections(d['text'])) and not body['accept_partial']:
                    raise ValueError('Неполный ответ: исправьте текст и явно подтвердите проверку документа.')
                campaign = self.repo.create(dict(token=cid,name=value['name'],memory=d['text'],settings=settings,source=value.get('snapshot')),db=db)
                db.execute('UPDATE chat_campaigns SET opening_required=1 WHERE id=?',(campaign,))
                jid,fresh = self.reserve(campaign,dict(token=cid,revision=0,kind='start',text=''),db=db,resolved=settings)
                db.execute("UPDATE chat_creations SET campaign_id=?,status='confirmed',revision=revision+1 WHERE id=?",(campaign,cid))
        if jid: self.launch(campaign,jid,fresh)
        return self.repo.state(campaign)

    def stream_opened(self, jid, stream):
        with self.lock:
            worker = self.workers.get(jid)
            if worker and not worker['event'].is_set():
                worker['stream'] = stream
                return
        stream.close()

    def persist(self, cid, jid, text, status='running', error=''):
        if cid.startswith('creation_'): return self.creations.persist(cid,jid,text,status,error)
        with self.repo.transaction() as db:
            j = row(db, 'chat_jobs', jid, cid)
            c = self.repo.campaign(db, cid)
            if j['status'] != 'running': return False
            if c['revision'] != j['source_revision'] or c['active_branch'] != j['branch_id']:
                status, error = 'interrupted', 'Состояние изменилось; поздний ответ не принят.'
            db.execute('UPDATE chat_jobs SET response=?,status=?,error=? WHERE id=?', (text,status,error,jid))
            if j['kind'] == 'summary':
                db.execute('UPDATE chat_drafts SET text=?,original=?,status=? WHERE id=?', (text,text,status,j['output_id']))
            else:
                db.execute('UPDATE chat_messages SET content=?,status=? WHERE id=?', (text,status,j['output_id']))
            return status == 'running'

    def run(self, cid, jid, event):
        text = ''
        try:
            initial = cid.startswith('creation_')
            with self.repo.connect() as db: j = row(db, 'chat_creation_jobs' if initial else 'chat_jobs', jid, None if initial else cid)
            if j['status'] != 'running': return
            if initial and j['kind']=='continue': text = j['response']
            config = json.loads(j['config_json'])
            with model_lease(config['provider']):
                if event.is_set(): return
                # Recheck the serving limit under the shared model lease, including
                # recorded retries after a model was reloaded with a smaller window.
                known = capabilities.discover(config['provider'],config['model'],self.credentials)
                if known.get('context_length'):
                    require_fit(json.loads(j['context_json']),dict(config,context_length=min(config['context_length'],known['context_length'])))
                # Cancellation may precede worker registration, or arrive while
                # waiting for metadata/lease (including from another process).
                if event.is_set(): return
                with self.repo.connect() as db:
                    current = row(db,'chat_creation_jobs' if initial else 'chat_jobs',jid)
                if current['status'] != 'running': return
                key = self.credentials.resolve(config['provider'])
                for chunk in tracked_stream(self.repo.storage, llm.chat_stream, jid, 'chat_'+j['kind'], config,
                    json.loads(j['context_json']), model=config['model'], provider=config['provider'], api_key=key,
                    temperature=config['temperature'], max_tokens=config['max_tokens'], require_complete=True,
                    cancel_event=event, on_stream=lambda stream:self.stream_opened(jid,stream)):
                    if event.is_set(): break
                    text += chunk
                    if not self.persist(cid, jid, text): break
                if not event.is_set():
                    self.persist(cid, jid, text, 'complete' if text.strip() else 'empty',
                                 '' if text.strip() else 'Провайдер вернул пустой ответ. Повтор — только по вашей кнопке.')
        except Exception as exc:
            status = 'stopped' if event.is_set() else 'length' if isinstance(exc,llm.OutputLimitReached) else 'error'
            # Never echo provider exceptions: they may contain a URL/key or prompt.
            error = {'stopped':'Остановлено. Частичный текст сохранён.',
                     'length':'Достигнут лимит ответа. Текст неполный; исправьте его или повторите явно.',
                     'error':'Запрос прерван или не сохранён. Исход расхода может быть неизвестен; автоматического повтора нет.'}[status]
            try: self.persist(cid, jid, text, status, error)
            except sqlite3.Error:
                # A failed message/draft transaction must not look like a live stream.
                # Preserve an emergency journal independently if the DB still accepts writes.
                try:
                    with self.repo.connect() as db:
                        table = 'chat_creation_jobs' if cid.startswith('creation_') else 'chat_jobs'
                        db.execute(f"UPDATE {table} SET status='error',response=?,error=? WHERE id=? AND status='running'",
                                   (text,'Ошибка записи ответа. Доступный текст сохранён в журнале; примите его через редактор или повторите явно.',jid))
                except sqlite3.Error:
                    # A completely unwritable disk can preserve only the last durable prefix.
                    # Startup recovery handles this reservation after storage is restored.
                    pass
        finally:
            with self.lock: self.workers.pop(jid, None)

    def stop(self, cid, jid):
        j = self.job(cid, jid)
        with self.lock:
            worker = self.workers.get(jid)
            if worker: worker['event'].set()
            stream = worker['stream'] if worker else None
        # Read latest persisted prefix inside the same transaction as cancellation.
        with self.repo.transaction() as db:
            initial = cid.startswith('creation_')
            j = row(db, 'chat_creation_jobs' if initial else 'chat_jobs', jid, None if initial else cid)
            if initial and j['status']=='running':
                db.execute("UPDATE chat_creation_jobs SET status='stopped',error='Остановлено. Частичный текст сохранён.' WHERE id=?",(jid,))
                db.execute("UPDATE chat_creations SET status='stopped' WHERE id=? AND job_id=?",(cid,jid))
            elif j['status']=='running':
                db.execute("UPDATE chat_jobs SET status='stopped',error='Остановлено. Частичный текст сохранён.' WHERE id=?", (jid,))
                table = 'chat_drafts' if j['kind']=='summary' else 'chat_messages'
                db.execute(f"UPDATE {table} SET status='stopped' WHERE id=?", (j['output_id'],))
        if stream:
            try: stream.close()
            except Exception: pass
        return self.job(cid, jid)

    def recover(self):
        with self.repo.transaction() as db:
            for j in db.execute("SELECT * FROM chat_creation_jobs WHERE status='running'").fetchall():
                receipt = db.execute('SELECT response_text FROM llm_requests WHERE job_id=? ORDER BY rowid DESC LIMIT 1',(j['id'],)).fetchone()
                prefix = json.loads(j['context_json'])[-2]['content'] if j['kind']=='continue' else ''
                recovered = prefix+(receipt['response_text'] or '') if receipt else ''
                text = recovered if len(recovered)>len(j['response']) else j['response']
                db.execute("UPDATE chat_creation_jobs SET status='interrupted',response=?,error='Сервер перезапущен. Повтор только вручную.' WHERE id=?",(text,j['id']))
                db.execute("UPDATE chat_creations SET status='interrupted',text=? WHERE id=? AND job_id=?",(text,j['creation_id'],j['id']))
            for j in db.execute("SELECT * FROM chat_jobs WHERE status='running'").fetchall():
                # A DB failure can leave more text in the completed provider journal.
                receipt = db.execute('SELECT response_text FROM llm_requests WHERE job_id=? ORDER BY rowid DESC LIMIT 1', (j['id'],)).fetchone()
                text = receipt['response_text'] if receipt and receipt['response_text'] else j['response']
                db.execute("UPDATE chat_jobs SET status='interrupted',response=?,error='Сервер перезапущен. Исход запроса неизвестен; повтор только вручную.' WHERE id=?", (text,j['id']))
                if j['kind']=='summary':
                    db.execute("UPDATE chat_drafts SET status='interrupted',text=?,original=? WHERE id=?", (text,text,j['output_id']))
                else:
                    db.execute("UPDATE chat_messages SET status='interrupted',content=? WHERE id=?", (text,j['output_id']))

    def shutdown(self):
        with self.repo.connect() as db:
            active = list(db.execute("SELECT campaign_id,id FROM chat_jobs WHERE status='running'"))
            active += list(db.execute("SELECT creation_id AS campaign_id,id FROM chat_creation_jobs WHERE status='running'"))
        for j in active: self.stop(j['campaign_id'], j['id'])
