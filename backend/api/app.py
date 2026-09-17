"""HTTP adapter. Authoritative state lives in repositories, never in a connection."""
import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import secrets
import sqlite3
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import engine
import llm
from character_links import linked_markdown
from backend.api.schemas import (World, Named, Generation, Turn, Retry, Revision, Scene,
                                 Models, Load, Preferences, Markdown, Credential, VariantSelection, Actor, DocumentChange, Camera, Motivation)
from backend.repositories.preparation import Repository
from backend.services.preparation import Preparation
from backend.services.scene import scene_metadata
from backend.services.coordinator import LOCAL_MODEL_LOCK
from backend.services.credentials import Credentials

ROOT = Path(__file__).resolve().parents[2]
ACTIVE = ('generating', 'extracting', 'validating')


def create_app(db_path=None, recover=True):
    repo = Repository(db_path)
    preparation = Preparation(repo)
    credentials = Credentials(repo)

    @asynccontextmanager
    async def lifespan(app):
        if recover:
            with repo.connect() as db:
                stale = [r['id'] for r in db.execute("SELECT id FROM preparation_jobs WHERE status='generating'")]
                db.execute("UPDATE game_jobs SET status='stopped',error='Сервер перезапущен. Можно повторить запрос.' WHERE status IN ('generating','extracting','validating')")
                db.execute("UPDATE llm_requests SET status='interrupted' WHERE status='running'")
            for jid in stale:
                preparation.stop(jid)
        yield
        with repo.connect() as db:
            games = [r['id'] for r in db.execute("SELECT id FROM game_jobs WHERE status IN ('generating','extracting','validating')")]
            drafts = [r['id'] for r in db.execute("SELECT id FROM preparation_jobs WHERE status='generating'")]
        for jid in games:
            engine.stop(repo, jid)
        for jid in drafts:
            preparation.stop(jid)

    app = FastAPI(title='AI RPG Engine', version='2.0.0', lifespan=lifespan)
    app.state.repository = repo
    app.state.preparation = preparation

    @app.middleware('http')
    async def same_origin(request, call_next):
        origin = request.headers.get('origin')
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and origin and urlsplit(origin).netloc != request.headers.get('host'):
            return JSONResponse({'detail': 'Запрос с другого origin отклонён.'}, status_code=403)
        return await call_next(request)

    @app.exception_handler(ValueError)
    async def value_error(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=409)

    @app.exception_handler(sqlite3.Error)
    async def database_error(request, exc):
        return JSONResponse({'detail': 'Не удалось записать данные. Повтори запрос после завершения текущей операции.'}, status_code=409)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Pydantic's default response echoes input, which may include API keys.
        return JSONResponse({'detail': 'Некорректный запрос', 'fields': [list(e['loc']) for e in exc.errors()]}, status_code=422)

    @app.get('/api/health')
    def health():
        return {'service': 'ai-rpg-engine', 'version': '2.0.0', 'status': 'ready'}

    @app.post('/api/_shutdown')
    def shutdown(request: Request):
        expected = os.getenv('RPG_CONTROL_TOKEN')
        if not expected or not secrets.compare_digest(request.headers.get('x-control-token', ''), expected):
            raise HTTPException(403, 'Недоступно')
        with repo.connect() as db:
            games = [r['id'] for r in db.execute("SELECT id FROM game_jobs WHERE status IN ('generating','extracting','validating')")]
            drafts = [r['id'] for r in db.execute("SELECT id FROM preparation_jobs WHERE status='generating'")]
        for jid in games:
            engine.stop(repo, jid)
        for jid in drafts:
            preparation.stop(jid)
        if hasattr(app.state, 'shutdown'):
            app.state.shutdown()
        return {'ok': True}

    @app.get('/api/worlds')
    def worlds(deleted: bool = False):
        if not deleted:
            return repo.list_worlds()
        with repo.connect() as db:
            return [dict(r) for r in db.execute('SELECT id,name,version,created_at FROM worlds WHERE deleted=1 ORDER BY id DESC')]

    @app.post('/api/worlds')
    def create_world(body: World):
        return repo.get_world(repo.save_world(body.name, body.markdown.lstrip('\ufeff')))

    @app.get('/api/worlds/{wid}')
    def world(wid: int):
        w = repo.get_world(wid)
        w['scene_meta'] = scene_metadata(w['state'])
        return w

    @app.get('/api/worlds/{wid}/saves')
    def saves(wid: int):
        repo.get_world(wid)
        return repo.list_saves(wid)

    @app.post('/api/worlds/{wid}/saves')
    def create_save(wid: int, body: Named):
        return repo.get_save(repo.create_save(wid, body.name))

    def job(jid):
        if jid.startswith('prep_'):
            value = repo.preparation_job(jid)
            value['live'] = preparation.live(jid)
        else:
            value = repo.get_job(jid)
            value['live'] = engine.live(jid)
        value['warnings'] = json.loads(value.get('warnings_json','[]'))
        return repo.public_job(value)

    @app.get('/api/saves/{sid}')
    def save(sid: int):
        value = repo.get_save(sid)
        value['scene_meta'] = scene_metadata(value['state'])
        value['turns'] = [{**t, 'choices': json.loads(t['choices_json']), 'changes': json.loads(t['changes_json'])} for t in repo.list_turns(sid)]
        for t in value['turns']:
            t['variants'] = repo.variants(t['node_id'])
        latest = repo.latest_job(sid)
        value['job'] = job(latest['id']) if latest else None
        return value

    @app.patch('/api/saves/{sid}/scene')
    def scene(sid: int, body: Scene):
        repo.update_scene_meta(sid, body.model_dump(exclude={'revision'}), body.revision)
        return save(sid)

    @app.patch('/api/saves/{sid}/characters/{actor_id}/motivation')
    def motivation(sid: int, actor_id: str, body: Motivation):
        repo.update_motivation(sid, actor_id, body.revision, body.short_goal, body.intentions)
        return save(sid)

    @app.post('/api/saves/{sid}/turns')
    def turn(sid: int, body: Turn):
        settings = body.config.model_dump()
        settings['expected_revision'] = body.revision
        settings['target_turn_id'] = body.target_turn_id
        settings['rollback_following'] = body.rollback_following
        jid = engine.submit(repo, sid, body.text, body.kind, settings, api_key=credentials.resolve(body.config.provider, body.key()))
        return job(jid)

    @app.post('/api/saves/{sid}/rollback')
    def rollback(sid: int, body: Revision):
        repo.rollback_last(sid, body.revision)
        return save(sid)

    @app.get('/api/jobs/{jid}')
    def get_job(jid: str):
        return job(jid)

    @app.post('/api/jobs/{jid}/stop')
    def stop(jid: str):
        if jid.startswith('prep_'):
            preparation.stop(jid)
        else:
            repo.get_job(jid)
            engine.stop(repo, jid)
        return job(jid)

    @app.post('/api/jobs/{jid}/retry')
    def retry(jid: str, body: Retry):
        engine.retry(repo, jid, body.config.model_dump(), api_key=credentials.resolve(body.config.provider, body.key()))
        return job(jid)

    @app.get('/api/jobs/{jid}/events')
    async def events(jid: str, request: Request):
        await asyncio.to_thread(job, jid)
        async def stream():
            previous, tick = None, 0
            while not await request.is_disconnected():
                current = await asyncio.to_thread(job, jid)
                payload = json.dumps(current, ensure_ascii=False)
                if payload != previous:
                    yield f'event: snapshot\ndata: {payload}\n\n'
                    previous = payload
                if current['status'] not in ACTIVE:
                    return
                tick += 1
                if tick % 50 == 0:
                    yield ': heartbeat\n\n'
                await asyncio.sleep(0.2)
        return StreamingResponse(stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    @app.get('/api/workspaces')
    def workspaces(deleted: bool = False):
        return repo.list_workspaces(deleted)

    @app.post('/api/workspaces')
    def create_workspace(body: Named):
        return repo.create_workspace(body.name)

    @app.get('/api/workspaces/{wid}')
    def workspace(wid: str):
        return repo.workspace(wid)

    @app.post('/api/workspaces/{wid}/generate')
    def generate(wid: str, body: Generation):
        if body.kind == 'idea' and not body.text.strip():
            raise ValueError('Опиши идею или изменения.')
        jid = preparation.submit(wid, body.kind, body.text, body.config.model_dump(), body.revision, credentials.resolve(body.config.provider, body.key()))
        return job(jid)

    @app.post('/api/workspaces/{wid}/reset')
    def reset(wid: str, body: Revision):
        repo.reset_workspace(wid, body.revision)
        return repo.workspace(wid)

    @app.post('/api/workspaces/{wid}/world')
    def save_preparation(wid: str, body: Named):
        w = repo.workspace(wid)
        if w['deleted'] or (w['job'] and w['job']['status'] == 'generating') or not w['summary_complete']:
            raise ValueError('Заверши генерацию выжимки перед сохранением мира.')
        return repo.get_world(repo.save_world(body.name, w['summary']))

    @app.get('/api/prompts')
    def prompts():
        return repo.prompt_snapshot()

    @app.get('/api/documents/{kind}/{owner}')
    def document(kind: str,owner: str):
        return repo.document_history(kind,owner)

    @app.post('/api/documents/{kind}/{owner}')
    def change_document(kind: str,owner: str,body: DocumentChange):
        return repo.change_document(kind,owner,body.content,body.expected_head,body.source_id)

    @app.delete('/api/workspaces/{wid}')
    def remove_workspace(wid: str,body: Revision):
        repo.remove_workspace(wid,body.revision)
        return {'ok':True}

    @app.post('/api/workspaces/{wid}/restore')
    def restore_workspace(wid: str,body: Revision):
        repo.remove_workspace(wid,body.revision,False)
        return repo.workspace(wid)

    @app.delete('/api/worlds/{wid}')
    def remove_world(wid: int):
        repo.remove_world(wid)
        return {'ok':True}

    @app.post('/api/worlds/{wid}/restore')
    def restore_world(wid: int):
        repo.remove_world(wid,False)
        return repo.get_world(wid)

    @app.post('/api/saves/{sid}/actor')
    def actor(sid: int,body: Actor):
        settings={**body.config.model_dump(),'expected_revision':body.revision,'actor_id':body.actor_id,'source_turn_id':body.source_turn_id}
        jid=engine.submit(repo,sid,'','pov',settings,api_key=credentials.resolve(body.config.provider,body.key()))
        return job(jid)

    @app.post('/api/saves/{sid}/camera')
    def camera(sid: int, body: Camera):
        if body.actor_id is not None and body.scene_id is not None:
            raise ValueError('Выбери персонажа или сцену камеры, не оба сразу.')
        settings={**body.config.model_dump(),'expected_revision':body.revision,
                  'camera_actor_id':body.actor_id,'camera_scene_id':body.scene_id,'camera_direct':True}
        jid=engine.submit(repo,sid,'','background',settings,api_key=credentials.resolve(body.config.provider,body.key()))
        return job(jid)

    @app.get('/api/saves/{sid}/timeline')
    def world_timeline(sid: int, visibility: str='player'):
        if visibility not in ('player','actor'):
            raise ValueError('Неизвестный фильтр журнала.')
        from backend.services.world import timeline
        return timeline(repo.get_save(sid)['state'],visibility)

    @app.get('/api/saves/{sid}/scene-records/{record_id}')
    def scene_record(sid: int, record_id: str):
        value=repo.get_save(sid)['state']['world']['scene_records'].get(record_id)
        if value is None:
            raise ValueError('Запись сцены не найдена в текущей истории.')
        return {'mode':'playback','sequence':value['source_sequence'],'narrative':value['narrative'],
                'user_text':'','scene':value['scene_meta'],'pov_actor_id':value['pov_actor_id']}

    @app.get('/api/saves/{sid}/playback/{tid}')
    def playback(sid: int, tid: int):
        # Read-only historical camera: no job, clock, revision or canonical state mutation.
        repo.get_save(sid)
        with repo.connect() as db:
            row=db.execute('SELECT * FROM turns WHERE id=? AND save_id=?',(tid,sid)).fetchone()
            if row is None:
                raise ValueError('Записанная сцена не найдена в текущей истории.')
            from backend.services.world import normalize
            state=normalize(json.loads(row['after_json']))
            return {'mode':'playback','turn_id':tid,'sequence':row['sequence'],
                    'narrative':row['assistant_text'],'user_text':row['user_text'],
                    'scene':scene_metadata(state),'pov_actor_id':row['pov_actor_id'],
                    'camera':state.get('camera'), 'world_clock':state.get('world_clock')}

    @app.get('/api/credentials')
    def credential_status():
        return credentials.status()

    @app.put('/api/credentials/deepseek')
    def store_key(body: Credential):
        if not body.key() or not body.key().strip():
            raise ValueError('Введи непустой API-ключ.')
        credentials.put('deepseek',body.key())
        return credentials.status()

    @app.delete('/api/credentials/deepseek')
    def delete_key():
        credentials.delete('deepseek')
        return credentials.status()

    @app.get('/api/capabilities')
    def capabilities():
        return {key: {'thinking_models':spec.thinking_models} for key,spec in llm.PROVIDERS.items()}

    @app.get('/api/saves/{sid}/accounting')
    def accounting(sid: int):
        return repo.accounting(sid)

    @app.post('/api/saves/{sid}/sessions')
    def new_session(sid: int):
        return {'id':repo.start_session(sid)}

    @app.get('/api/workspaces/{wid}/requests')
    def workspace_requests(wid: str):
        repo.workspace(wid)
        return repo.request_log(workspace_id=wid)

    @app.post('/api/saves/{sid}/turns/{tid}/variant')
    def select_variant(sid: int, tid: int, body: VariantSelection):
        repo.select_variant(sid,tid,body.variant_id,body.revision,body.rollback_following)
        return save(sid)

    @app.get('/api/saves/{sid}/archive')
    def archive(sid: int):
        repo.get_save(sid)
        with repo.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM archived_turns WHERE save_id=? ORDER BY id', (sid,))]

    @app.get('/api/settings/{profile}')
    def settings(profile: str):
        return repo.get_settings(profile)

    @app.put('/api/settings/{profile}')
    def set_settings(profile: str, body: Preferences):
        repo.save_settings(profile, body.model_dump())
        return body

    @app.post('/api/models/list')
    def models(body: Models):
        try:
            if body.provider == 'deepseek':
                return {'models': llm.get_deepseek_models(credentials.resolve('deepseek',body.key())), 'loaded': []}
            return {'models': llm.get_available_models(), 'loaded': llm.get_loaded_models()}
        except Exception:
            raise HTTPException(502, 'Не удалось получить модели. Проверь провайдера, подключение и API-ключ.') from None

    @app.post('/api/models/load')
    def load(body: Load):
        if not LOCAL_MODEL_LOCK.acquire(blocking=False):
            raise HTTPException(409, 'Локальная модель занята генерацией.')
        try:
            llm.unload_all_models()
            llm.load_model(**body.model_dump())
            return {'loaded': llm.get_loaded_models()}
        except Exception:
            raise HTTPException(502, 'Не удалось загрузить модель в LM Studio.') from None
        finally:
            LOCAL_MODEL_LOCK.release()

    @app.post('/api/models/unload')
    def unload():
        if not LOCAL_MODEL_LOCK.acquire(blocking=False):
            raise HTTPException(409, 'Локальная модель занята генерацией.')
        try:
            return {'unloaded': llm.unload_all_models()}
        except Exception:
            raise HTTPException(502, 'Не удалось выгрузить модель.') from None
        finally:
            LOCAL_MODEL_LOCK.release()

    @app.post('/api/markdown')
    def markdown(body: Markdown):
        state = repo.get_save(body.save_id)['state'] if body.save_id else repo.get_world(body.world_id)['state'] if body.world_id else {}
        return {'html': linked_markdown(body.text, state.get('characters', []) if body.link_names else [])}

    dist = ROOT / 'frontend' / 'dist'
    if (dist / 'assets').is_dir():
        app.mount('/assets', StaticFiles(directory=dist / 'assets'), name='assets')

    @app.get('/sw.js', include_in_schema=False)
    def service_worker():
        if not (dist/'sw.js').is_file():raise HTTPException(404)
        return FileResponse(dist/'sw.js',media_type='text/javascript',headers={'Cache-Control':'no-cache','Service-Worker-Allowed':'/'})

    @app.get('/manifest.webmanifest', include_in_schema=False)
    def manifest():
        return FileResponse(dist/'manifest.webmanifest',media_type='application/manifest+json',headers={'Cache-Control':'no-cache'})

    @app.get('/offline.html', include_in_schema=False)
    def offline():
        return FileResponse(dist/'offline.html',headers={'Cache-Control':'no-cache'})

    if (dist/'icons').is_dir():
        app.mount('/icons',StaticFiles(directory=dist/'icons'),name='icons')

    @app.get('/api/local-ca', include_in_schema=False)
    def local_ca():
        cert=ROOT/'.runtime'/'tls'/'rootCA.cer'
        if not (ROOT/'.runtime'/'https.json').is_file() or not cert.is_file():raise HTTPException(404)
        return FileResponse(cert,media_type='application/x-x509-ca-cert',filename='AI-RPG-Local-CA.cer',headers={'Cache-Control':'no-store'})

    @app.get('/{path:path}', include_in_schema=False)
    def frontend(path: str):
        if path.startswith('api/'):
            raise HTTPException(404, 'Маршрут не найден')
        if not (dist / 'index.html').is_file():
            raise HTTPException(503, 'Собери frontend: npm ci && npm run build в frontend/')
        return FileResponse(dist / 'index.html', headers={'Cache-Control': 'no-cache'})

    return app
