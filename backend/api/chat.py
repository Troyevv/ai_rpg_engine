"""HTTP adapter for the local trusted-operator app (same origin policy as Narrative)."""
import asyncio
import json

from fastapi import Query
from fastapi.responses import StreamingResponse
from backend.chat import models, capabilities, tokenization
from backend.chat.context import RP_PROMPT, TEMPLATE
from backend.chat.repository import ChatRepository, row
from backend.chat.service import ChatService
from backend.chat.source import preview


def install(app, storage, credentials):
    repo = ChatRepository(storage)
    service = ChatService(repo, credentials)
    app.state.chat = service

    @app.get('/api/chat/defaults')
    def defaults():
        return dict(template=TEMPLATE, settings=models.Settings(prompt=RP_PROMPT).model_dump())

    @app.post('/api/chat/capabilities')
    def model_capabilities(body: models.ModelSettings):
        info = capabilities.discover(body.provider,body.model,credentials)
        info['approximate'] = True
        info['tokenizer'] = tokenization.method(body.model_dump())
        return info

    @app.post('/api/chat/tokenizer')
    def install_tokenizer(body: models.ModelSettings):
        if body.provider!='deepseek' or body.model not in capabilities.DEEPSEEK:
            raise ValueError('Этот tokenizer предназначен для известных моделей DeepSeek API.')
        return tokenization.install()

    @app.get('/api/chat/creations')
    def creations():
        with repo.connect() as db:
            ids = [r['id'] for r in db.execute("SELECT id FROM chat_creations WHERE campaign_id IS NULL ORDER BY rowid DESC")]
        return [service.creations.state(cid) for cid in ids]

    @app.post('/api/chat/creations')
    def creation(body: models.Creation):
        cid = service.creations.create(body.model_dump())
        return service.creations.state(cid)

    @app.get('/api/chat/creations/{cid}')
    def creation_state(cid: str):
        return service.creations.state(cid)

    @app.put('/api/chat/creations/{cid}')
    def creation_save(cid: str, body: models.CreationEdit):
        service.creations.save(cid,body.model_dump())
        return service.creations.state(cid)

    @app.post('/api/chat/creations/{cid}/generate')
    def creation_generate(cid: str,body: models.CreationGenerate):
        return service.start(cid,body.model_dump())

    @app.post('/api/chat/creations/{cid}/confirm')
    def creation_confirm(cid: str,body: models.CreationConfirm):
        return service.confirm_creation(cid,body.model_dump())

    @app.get('/api/chat/creations/{cid}/jobs/{jid}')
    def creation_job(cid: str,jid: str):
        return service.creations.job(cid,jid)

    @app.post('/api/chat/creations/{cid}/jobs/{jid}/stop')
    def creation_stop(cid: str,jid: str):
        return service.stop(cid,jid)

    @app.get('/api/chat/creations/{cid}/jobs/{jid}/events')
    async def creation_events(cid: str,jid: str):
        return await events(cid,jid)

    @app.post('/api/chat/source')
    def source(body: models.Source):
        return preview(storage, body)

    @app.get('/api/chat/campaigns')
    def campaigns():
        return repo.list()

    @app.post('/api/chat/campaigns')
    def create(body: models.Create):
        value = body.model_dump()
        value['settings'] = capabilities.settings(value['settings'],credentials)
        if not body.name.strip(): raise ValueError('Введите название кампании.')
        if body.source:
            if set(body.source) != {'id'}: raise ValueError('Некорректный источник.')
            with storage.connect() as db:
                captured = row(db, 'chat_sources', body.source['id'])
                value['source'] = dict(id=captured['id'],memory=captured['memory'],origin=json.loads(captured['origin_json']))
        return repo.state(repo.create(value))

    @app.get('/api/chat/campaigns/{cid}')
    def state(cid: str):
        return repo.state(cid)

    @app.get('/api/chat/campaigns/{cid}/messages')
    def messages(cid: str, branch: str | None = None, chapter: str | None = None,
                 before: int = Query(2147483647, ge=1), limit: int = Query(40,ge=1,le=100),
                 after: int | None = Query(None,ge=0)):
        return repo.page(cid,branch,chapter,before,limit,after=after)

    @app.post('/api/chat/campaigns/{cid}/budget')
    def budget(cid: str, body: models.Memory):
        with repo.connect() as db:
            repo.campaign(db,cid)
            return repo.budgets(db,cid,body.text)

    @app.get('/api/chat/campaigns/{cid}/bookmarks')
    def bookmarks(cid: str, branch: str | None = None, before: int = Query(2147483647,ge=1),
                  q: str = Query('',max_length=200)):
        return repo.bookmarks(cid,branch,before,q)

    @app.put('/api/chat/campaigns/{cid}/bookmarks')
    def bookmark(cid: str, body: models.Bookmark):
        repo.bookmark(cid,body.model_dump())
        return repo.state(cid)

    @app.get('/api/chat/campaigns/{cid}/messages/{message}/locate')
    def locate(cid: str,message: str,branch: str | None = None):
        return repo.locate(cid,message,branch)

    @app.put('/api/chat/campaigns/{cid}/settings')
    def configure(cid: str, body: models.Configure):
        value=body.model_dump()
        value['settings']=capabilities.settings(value['settings'],credentials)
        repo.configure(cid,value)
        return repo.state(cid)

    @app.post('/api/chat/campaigns/{cid}/select')
    def select(cid: str, body: models.Select):
        repo.select(cid,body.model_dump())
        return repo.state(cid)

    @app.post('/api/chat/campaigns/{cid}/edit')
    def edit(cid: str, body: models.Edit):
        repo.edit(cid,body.model_dump())
        return repo.state(cid)

    @app.post('/api/chat/campaigns/{cid}/generate')
    def generate(cid: str, body: models.Generate):
        return service.start(cid,body.model_dump())

    @app.get('/api/chat/campaigns/{cid}/jobs/{jid}')
    def job(cid: str,jid: str):
        return repo.job(cid,jid)

    @app.get('/api/chat/campaigns/{cid}/jobs/{jid}/requests')
    def requests(cid: str,jid: str):
        repo.job(cid,jid)
        return storage.request_log(job_id=jid)

    @app.post('/api/chat/campaigns/{cid}/jobs/{jid}/stop')
    def stop(cid: str,jid: str):
        return service.stop(cid,jid)

    @app.get('/api/chat/campaigns/{cid}/jobs/{jid}/events')
    async def events(cid: str,jid: str):
        service.job(cid,jid)  # Validate scope before headers are sent.
        async def stream():
            previous = None
            while True:
                value = await asyncio.to_thread(service.job,cid,jid)
                data = json.dumps(value,ensure_ascii=False)
                if data != previous:
                    yield 'event: snapshot\ndata: '+data+'\n\n'
                    previous = data
                if value['status'] != 'running': break
                await asyncio.sleep(.15)
        return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})

    @app.post('/api/chat/campaigns/{cid}/memory')
    def memory(cid: str,body: models.Memory):
        return repo.manual_memory(cid,body.model_dump())

    @app.get('/api/chat/campaigns/{cid}/versions')
    def versions(cid: str,before: int = Query(2147483647,ge=1)):
        return repo.versions(cid,before)

    @app.get('/api/chat/campaigns/{cid}/characters')
    def characters(cid: str,branch: str | None = None,memory: str | None = None,
                   q: str = Query('',max_length=200),offset: int = Query(0,ge=0)):
        return repo.library(cid,branch,memory,q,offset)

    @app.get('/api/chat/campaigns/{cid}/characters/{key}')
    def character(cid: str,key: str,branch: str | None = None,memory: str | None = None):
        return repo.character(cid,key,branch,memory)

    @app.post('/api/chat/campaigns/{cid}/characters/{key}/draft')
    def character_draft(cid: str,key: str,body: models.CharacterEdit):
        return repo.edit_character(cid,key,body.model_dump())

    @app.get('/api/chat/campaigns/{cid}/history')
    def history(cid: str,branch: str | None = None,before: int = Query(2147483647,ge=1)):
        return repo.history(cid,branch,before)

    @app.get('/api/chat/campaigns/{cid}/history/{mid}')
    def history_detail(cid: str,mid: str,branch: str | None = None):
        return repo.history_detail(cid,mid,branch)

    @app.get('/api/chat/campaigns/{cid}/drafts/{did}')
    def draft(cid: str,did: str):
        return repo.draft(cid,did)

    @app.put('/api/chat/campaigns/{cid}/drafts/{did}')
    def save_draft(cid: str,did: str,body: models.DraftEdit):
        repo.save_draft(cid,did,body.model_dump())
        return repo.draft(cid,did)

    @app.post('/api/chat/campaigns/{cid}/drafts/{did}/confirm')
    def confirm(cid: str,did: str,body: models.Confirm):
        repo.confirm(cid,did,body.model_dump())
        return repo.state(cid)

    @app.post('/api/chat/campaigns/{cid}/drafts/{did}/cancel')
    def cancel(cid: str,did: str,body: models.Revision):
        repo.cancel_draft(cid,did,body.revision)
        return repo.state(cid)

    return service
