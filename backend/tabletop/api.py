"""Thin FastAPI adapter. Tabletop state never enters narrative repositories."""
import hashlib
import json
from uuid import uuid4
from fastapi import APIRouter
from pydantic import Field, model_validator
from backend.api.schemas import Credential, ModelConfig
from .models import Command, NewGame
from .repository import TabletopRepository
from .runtime import TabletopRuntime, new_game
from .projection import public_state
from .dm import DMAgent


class Request(Credential):
    revision: int = Field(ge=0)
    request_id: str = Field(min_length=8, max_length=100)
    config: ModelConfig | None = None


class ActionRequest(Request):
    command: Command | None = None
    text: str = Field(default='', max_length=4000)

    @model_validator(mode='after')
    def one_action(self):
        if (self.command is None) == (not self.text.strip()):
            raise ValueError('Укажи команду или текст')
        return self


class RollRequest(Request):
    pending_id: str = Field(min_length=1, max_length=100)


def install(app, shared_repo, credentials):
    repo = TabletopRepository(shared_repo.path)
    runtime = TabletopRuntime()
    app.state.tabletop_repository = repo
    app.state.tabletop_runtime = runtime
    router = APIRouter(prefix='/api/tabletop', tags=['tabletop'])

    def snapshot(gid):
        revision, state = repo.load(gid)
        return {'id': gid, 'revision': revision, 'state': public_state(state), 'history': repo.history(gid), 'usage': repo.usage(gid)}

    def agent(body):
        config = body.config.model_dump() if body.config else None
        return DMAgent(repo, config, credentials.resolve(body.config.provider, body.key()) if body.config else None)

    def prepare(gid, body, kind):
        fingerprint = hashlib.sha256(json.dumps({'kind': kind, **body.model_dump(exclude={'api_key', 'config', 'request_id'})}, sort_keys=True).encode()).hexdigest()
        if repo.duplicate(gid, body.request_id, fingerprint):
            return None, fingerprint
        revision, state = repo.load(gid)
        if revision != body.revision:
            raise ValueError('Кампания изменилась. Обнови экран.')
        return state, fingerprint

    def finish(gid, body, fp, state, events, dm, text):
        if repo.commit(gid, body.revision, body.request_id, fp, state, events, text):
            try:
                narrative = dm.narrate(gid, state, events, text)
            except Exception:
                # A provider failure after commit cannot undo or replay a dice roll.
                narrative = '\n\n'.join(e['text'] for e in events if 'roll' not in e) + '\n\nОписание DM недоступно. Игровой результат сохранён.'
            repo.annotate(gid, body.revision + 1, narrative)
        return snapshot(gid)

    @router.get('/games')
    def games():
        return repo.list_games()

    @router.post('/games')
    def create(body: NewGame):
        state = new_game(body)
        gid = repo.create(state)
        after, events = runtime.execute(state, Command(type='look'))
        repo.commit(gid, 0, uuid4().hex, 'opening', after, events, '')
        repo.annotate(gid, 1, state.world.description)
        return snapshot(gid)

    @router.get('/games/{gid}')
    def get(gid: str):
        return snapshot(gid)

    @router.post('/games/{gid}/actions')
    def action(gid: str, body: ActionRequest):
        state, fp = prepare(gid, body, 'action')
        if state is None:
            return snapshot(gid)
        if state.session_state.pending:
            raise ValueError('Сначала выполни ожидающий бросок')
        dm = agent(body)
        try:
            command = body.command or dm.interpret(gid, state, body.text)
        except ValueError:
            raise
        except Exception:
            raise ValueError('DM недоступен. Состояние не изменено; можно использовать игровые кнопки.') from None
        after, events = runtime.execute(state, command)
        labels = {'look': 'Осмотреться', 'dialogue': 'Поговорить', 'check': 'Выполнить проверку',
                  'save': 'Выполнить спасбросок', 'attack': 'Атаковать', 'start_encounter': 'Начать бой',
                  'end_turn': 'Закончить ход', 'dodge': 'Уклонение', 'dash': 'Рывок',
                  'disengage': 'Отход', 'move': 'Переместиться', 'rest': 'Отдохнуть'}
        return finish(gid, body, fp, after, events, dm, body.text or labels[command.type])

    @router.post('/games/{gid}/roll')
    def roll(gid: str, body: RollRequest):
        state, fp = prepare(gid, body, 'roll')
        if state is None:
            return snapshot(gid)
        dm = agent(body)
        after, events = runtime.resolve_roll(state, body.pending_id)
        return finish(gid, body, fp, after, events, dm, 'Бросить кубик')

    @router.post('/games/{gid}/rollback')
    def rollback(gid: str, body: Request):
        state, fp = prepare(gid, body, 'rollback')
        if state is None:
            return snapshot(gid)
        previous = repo.before_last(gid, body.revision)
        repo.commit(gid, body.revision, body.request_id, fp, previous, [{'text': 'Восстановлено состояние до предыдущего действия.'}], 'Откат')
        return snapshot(gid)

    @router.get('/games/{gid}/replay/{revision}')
    def replay(gid: str, revision: int):
        return {'revision': revision, 'state': public_state(repo.replay(gid, revision))}

    app.include_router(router)
