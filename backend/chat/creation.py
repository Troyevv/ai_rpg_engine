"""Durable author drafts before a playable campaign exists."""
import hashlib
import json
import re

from backend.chat.context import INITIAL_PROMPT, TEMPLATE, require_fit
from backend.chat.repository import dump, row, uid
from backend.chat import capabilities
from backend.chat.source import preview
from backend.chat.models import Source


class CreationStore:
    def __init__(self, repo, credentials):
        self.repo, self.credentials = repo, credentials

    def operation(self, db, cid, body):
        fp = hashlib.sha256(dump(body).encode()).hexdigest()
        old = db.execute('SELECT * FROM chat_creation_operations WHERE creation_id=? AND token=?', (cid,body['token'])).fetchone()
        if old and old['fingerprint'] != fp: raise ValueError('Ключ повтора уже использован для другого действия.')
        return fp, json.loads(old['result']) if old else None

    def record(self, db, cid, body, fp, result):
        db.execute('INSERT INTO chat_creation_operations VALUES(?,?,?,?)', (cid,body['token'],fp,dump(result)))

    def guard(self, db, cid, revision):
        d = row(db,'chat_creations',cid)
        if d['revision'] != revision: raise ValueError('Черновик изменён в другой вкладке. Загрузите сохранённую версию.')
        if d['campaign_id']: raise ValueError('Выжимка уже утверждена. Откройте кампанию.')
        if d['job_id'] and d['status']=='running':
            j = row(db,'chat_creation_jobs',d['job_id'])
            if j['status']!='running': d.update(status=j['status'],text=j['response'])
        if d['status']=='running': raise ValueError('Сначала остановите или дождитесь генерации.')
        return d

    def create(self, body):
        if not body['name'].strip(): raise ValueError('Введите название кампании.')
        fp = hashlib.sha256(dump(body).encode()).hexdigest()
        with self.repo.connect() as db:
            old = db.execute('SELECT * FROM chat_creations WHERE token=?',(body['token'],)).fetchone()
        if old:
            if old['fingerprint'] != fp: raise ValueError('Ключ создания уже использован.')
            return old['id']
        value = dict(body)
        if body.get('source'):
            snap = preview(self.repo.storage, Source(**body['source']))
            value['snapshot'] = snap
            value['text'] = snap['memory']
        with self.repo.transaction() as db:
            old = db.execute('SELECT * FROM chat_creations WHERE token=?',(body['token'],)).fetchone()
            if old:
                if old['fingerprint'] != fp: raise ValueError('Ключ создания уже использован.')
                return old['id']
            cid = 'creation_' + uid()
            db.execute('INSERT INTO chat_creations(id,token,fingerprint,payload,text) VALUES(?,?,?,?,?)',(cid,body['token'],fp,dump(value),value['text']))
            return cid

    def state(self, cid):
        with self.repo.connect() as db:
            d = row(db,'chat_creations',cid)
            value = json.loads(d.pop('payload'))
            d.pop('token'); d.pop('fingerprint')
            d.update(name=value['name'],idea=value['idea'],settings=value['settings'],source=value.get('source'))
            if d['job_id'] and d['status']=='running':
                journal = row(db,'chat_creation_jobs',d['job_id'])
                if journal['status']!='running': d.update(status=journal['status'],text=journal['response'])
            d['jobs'] = [self.job(cid,j['id'],db) for j in db.execute('SELECT id FROM chat_creation_jobs WHERE creation_id=? ORDER BY rowid',(cid,)).fetchall()]
            return d

    def save(self, cid, body):
        if not body['name'].strip(): raise ValueError('Введите название кампании.')
        with self.repo.transaction() as db:
            fp, old = self.operation(db,cid,body)
            if old: return
            d = self.guard(db,cid,body['revision'])
            value = json.loads(d['payload'])
            # Source provenance belongs to the original captured snapshot, not the browser.
            value.update({k:body[k] for k in ('name','idea','settings','text')})
            db.execute('UPDATE chat_creations SET payload=?,text=?,revision=revision+1 WHERE id=?',(dump(value),body['text'],cid))
            self.record(db,cid,body,fp,{'saved':True})

    def reserve(self, cid, body):
        with self.repo.connect() as db:
            d = row(db,'chat_creations',cid)
            _, previous = self.operation(db,cid,body)
            if previous: return previous['job'],False
        settings = json.loads(d['payload'])['settings']
        config = capabilities.resolve(settings['summary'],self.credentials,'initial')
        with self.repo.transaction() as db:
            fp, old = self.operation(db,cid,body)
            if old: return old['job'],False
            d = self.guard(db,cid,body['revision'])
            value = json.loads(d['payload'])
            if not value['idea'].strip(): raise ValueError('Опишите идею игры.')
            context = [dict(role='system',content=INITIAL_PROMPT+'\nЯзык: '+settings['language']+'\nАвторские правила:\n'+settings['prompt']+'\nПолный шаблон:\n'+TEMPLATE),dict(role='user',content=value['idea'])]
            prefix = ''
            if body['kind']=='continue':
                if not d['text'].strip(): raise ValueError('Нет текста для продолжения.')
                prefix = d['text']
                context.extend([dict(role='assistant',content=prefix),dict(role='user',content='Продолжи этот неполный документ с места остановки. Не повторяй написанное. Заверши все оставшиеся разделы и поля полного шаблона.')])
            if config['max_tokens'] < 8192 and body['kind']=='initial':
                raise ValueError('Для полного шаблона требуется лимит ответа не менее 8192. Выберите большее окно/лимит в дополнительных настройках.')
            if not config['model'].strip(): raise ValueError('Выберите модель.')
            require_fit(context,config)
            jid = 'chat_initial_' + uid()
            # Continuations retain the approved editable prefix as part of the recorded context.
            db.execute('INSERT INTO chat_creation_jobs(id,creation_id,kind,source_revision,context_json,config_json,response) VALUES(?,?,?,?,?,?,?)',(jid,cid,body['kind'],d['revision']+1,dump(context),dump(config),prefix))
            db.execute("UPDATE chat_creations SET revision=revision+1,status='running',job_id=?,text=? WHERE id=?",(jid,prefix,cid))
            self.record(db,cid,body,fp,{'job':jid})
            return jid,True

    def job(self, cid, jid, db=None):
        if db is None:
            with self.repo.connect() as db: return self.job(cid,jid,db)
        j = row(db,'chat_creation_jobs',jid)
        if j['creation_id'] != cid: raise ValueError('Запрос не принадлежит черновику.')
        j.pop('context_json');j.pop('config_json')
        j['usage'] = [dict(x) for x in db.execute('SELECT stage,provider,model,status,input_tokens,output_tokens,cost_usd,finish_reason FROM llm_requests WHERE job_id=?',(jid,))]
        return j

    def persist(self, cid, jid, text, status, error):
        with self.repo.transaction() as db:
            j = row(db,'chat_creation_jobs',jid)
            d = row(db,'chat_creations',cid)
            if j['creation_id']!=cid or j['status']!='running': return False
            if d['revision']!=j['source_revision'] or d['job_id']!=jid:
                status,error='interrupted','Черновик изменился; поздний ответ не принят.'
            if status=='complete' and missing_sections(text):
                status,error='incomplete','Отсутствуют разделы шаблона: '+', '.join(missing_sections(text))+'. Исправьте документ или явно запросите продолжение.'
            db.execute('UPDATE chat_creation_jobs SET response=?,status=?,error=? WHERE id=?',(text,status,error,jid))
            if d['job_id']==jid:
                db.execute('UPDATE chat_creations SET text=?,status=? WHERE id=?',(text,status,cid))
            return status=='running'


SECTIONS = ['ГЛАВНОЕ СЕЙЧАС','ЖАНР И ТОН','ГЛАВНЫЙ ГЕРОЙ','КЛЮЧЕВЫЕ NPC','ОТНОШЕНИЯ','ЧТО ЗНАЮТ / ЧТО ТАЙНА','МИР','ЛОКАЦИИ','АКТИВНЫЕ СОБЫТИЯ И ОБЯЗАТЕЛЬСТВА','НЕЗАКРЫТЫЕ ЛИНИИ','ХРОНОЛОГИЯ','ПРАВИЛА И НЕИЗМЕННЫЕ ФАКТЫ']


def missing_sections(text):
    # Structural completeness only; never adjudicates the literary content.
    labels = list(dict.fromkeys(re.findall(r'^· ([^:\n\[]+):', TEMPLATE, re.M)))
    plain = text.upper().replace('**','').replace('__','')
    return [section for section in SECTIONS if section not in plain] + [label+':' for label in labels if label.upper()+':' not in plain]
