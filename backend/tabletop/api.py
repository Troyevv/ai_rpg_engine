"""HTTP adapts requests; generated data crosses compiler before persistence."""

import hashlib
import json
from uuid import uuid4
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from .validation import CampaignValidationError
from pydantic import Field, model_validator
from backend.api.schemas import Credential, ModelConfig
from .models import Command, NewGame
from .definitions import CampaignDefinition, GenerationOptions, CharacterBuild
from .repository import TabletopRepository
from .runtime import TabletopRuntime
from .projection import public_state
from .compiler import CampaignCompiler
from .catalog import load_ruleset
from .dm import DMAgent, DMContextBuilder
from .generation import CampaignGenerator, ContentGenerator


class Request(Credential):
    revision: int = Field(ge=0)
    request_id: str = Field(min_length=8, max_length=100)
    config: ModelConfig | None = None


class ActionRequest(Request):
    command: Command | None = None
    text: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def one_action(self):
        if (self.command is None) == (not self.text.strip()):
            raise ValueError("Укажи команду или текст")
        return self


class RollRequest(Request):
    pending_id: str = Field(min_length=1, max_length=100)


class GenerateRequest(Credential):
    config: ModelConfig
    options: GenerationOptions


class DraftRequest(Credential):
    definition: CampaignDefinition
    revision: int = 0


class BuildRequest(Credential):
    build: CharacterBuild
    ruleset_id: str = "d20-basic-v2"


def install(app, shared_repo, credentials):
    repo = TabletopRepository(shared_repo.path)
    runtime = TabletopRuntime()
    compiler = CampaignCompiler()
    app.state.tabletop_repository = repo
    app.state.tabletop_runtime = runtime
    router = APIRouter(prefix="/api/tabletop", tags=["tabletop"])

    def snapshot(gid):
        revision, state = repo.load(gid)
        return {
            "id": gid,
            "revision": revision,
            "state": public_state(state),
            "history": repo.history(gid),
            "usage": repo.usage(gid)
            + (
                repo.usage(state.campaign.source_draft)
                if state.campaign.source_draft
                else []
            ),
        }

    def agent(body):
        config = body.config.model_dump() if body.config else None
        return DMAgent(
            repo,
            config,
            (
                credentials.resolve(body.config.provider, body.key())
                if body.config
                else None
            ),
        )

    def prepare(gid, body, kind):
        fp = hashlib.sha256(
            json.dumps(
                {
                    "kind": kind,
                    **body.model_dump(exclude={"api_key", "config", "request_id"}),
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        if repo.duplicate(gid, body.request_id, fp):
            return None, fp
        revision, state = repo.load(gid)
        if revision != body.revision:
            raise ValueError("Кампания изменилась. Обнови экран.")
        return state, fp

    def finish(gid, body, fp, state, events, dm, text):
        if repo.commit(gid, body.revision, body.request_id, fp, state, events, text):
            try:
                narrative = dm.narrate(gid, state, events, text)
            except Exception:
                narrative = (
                    "\n\n".join(e["text"] for e in events if "roll" not in e)
                    + "\n\nОписание DM недоступно. Игровой результат сохранён."
                )
            repo.annotate(gid, body.revision + 1, narrative)
        return snapshot(gid)

    def validation_response(exc, draft_id=None):
        return JSONResponse(
            status_code=409,
            content={
                "detail": exc.public_message(),
                "stage": exc.stage,
                "validation_issues": [i.model_dump() for i in exc.issues],
                "draft_id": draft_id,
            },
        )

    @router.get("/catalog")
    def catalog():
        return {
            **load_ruleset().model_dump(),
            "default_build": CharacterBuild().model_dump(),
        }

    @router.post("/build/validate")
    def build(body: BuildRequest):
        from .rules import RulesEngine

        RulesEngine().validate_build(body.build, load_ruleset(body.ruleset_id))
        return {"valid": True}

    @router.get("/drafts")
    def drafts():
        return repo.list_drafts()

    @router.get("/drafts/{did}")
    def draft(did: str):
        return repo.draft(did)  # explicit authoring surface; never gameplay projection

    @router.post("/drafts")
    def import_draft(body: DraftRequest):
        try:
            return repo.save_draft(body.definition)
        except CampaignValidationError as exc:
            return validation_response(exc)

    @router.put("/drafts/{did}")
    def edit(did: str, body: DraftRequest):
        try:
            return repo.save_draft(
                body.definition, draft_id=did, revision=body.revision
            )
        except CampaignValidationError as exc:
            return validation_response(exc, did)

    @router.post("/generate")
    def generate(body: GenerateRequest):
        did = uuid4().hex
        try:
            definition = CampaignGenerator(agent(body)).generate(did, body.options)
        except CampaignValidationError as exc:
            invalid_id = None
            if exc.definition is not None:
                invalid_id = repo.save_invalid_draft(
                    exc.definition, exc.issues, exc.stage, did
                )
            return validation_response(exc, invalid_id)
        except ValueError:
            raise
        except Exception:
            raise ValueError(
                "Генерация недоступна. Проверь модель и соединение."
            ) from None
        result = repo.save_draft(definition, source="generated")
        with repo.connect() as db:
            db.execute(
                "UPDATE tabletop_requests SET game_id=? WHERE game_id=?",
                (result["id"], did),
            )
        return repo.draft(result["id"])

    @router.get("/games")
    def games():
        return repo.list_games()

    @router.post("/games")
    def create(body: NewGame):
        draft = repo.draft(body.draft_id)
        if draft["revision"] != body.draft_revision:
            raise ValueError("Черновик изменился")
        if draft["generation_status"] != "VALID":
            raise ValueError(
                "Черновик содержит ошибки. Исправь и проверь его перед запуском."
            )
        state = compiler.compile(draft["definition"], body.character)
        state.campaign.source_draft = body.draft_id
        gid = repo.create(state)
        events = [{"text": state.definition.starting_scene, "kind": "opening"}]
        repo.commit(gid, 0, uuid4().hex, "opening", state, events, "")
        repo.annotate(gid, 1, state.definition.starting_scene)
        return snapshot(gid)

    @router.get("/games/{gid}")
    def get(gid: str):
        return snapshot(gid)

    @router.get("/games/{gid}/context")
    def context(gid: str):
        _, state = repo.load(gid)
        return {
            "public_context": DMContextBuilder.build(state),
            "dm_hidden_context": "Скрытая часть используется сервером и не выдаётся игроку.",
        }

    @router.post("/games/{gid}/actions")
    def action(gid: str, body: ActionRequest):
        state, fp = prepare(gid, body, "action")
        if state is None:
            return snapshot(gid)
        if state.session_state.pending:
            raise ValueError("Сначала выполни ожидающий бросок")
        dm = agent(body)
        try:
            command = body.command or dm.interpret(gid, state, body.text)
        except ValueError:
            raise
        except Exception:
            raise ValueError("DM недоступен. Состояние не изменено.") from None
        if command.type == "expand":
            if state.encounter or state.session_state.reaction:
                raise ValueError("Новый контент создаётся вне боя")
            runtime.owned(
                state, command.actor_id or state.session_state.controlled_actor
            )
            if not command.topic.strip():
                raise ValueError("Опиши новый контент")
            try:
                after, mutation = ContentGenerator(dm).generate(
                    gid, state, command.topic
                )
            except ValueError:
                raise
            except Exception:
                raise ValueError(
                    "Расширение мира недоступно. Состояние не изменено."
                ) from None
            events = [
                {
                    "text": "Добавлен новый контент. Доступные переходы обновлены.",
                    "kind": "content",
                    "operations": [op.type for op in mutation.operations],
                }
            ]
        else:
            after, events = runtime.execute(state, command)
        labels = {
            "look": "Осмотреться",
            "dialogue": "Поговорить",
            "check": "Выполнить проверку",
            "save": "Спасбросок",
            "attack": "Атаковать",
            "start_encounter": "Начать бой",
            "end_turn": "Закончить ход",
            "dodge": "Уклонение",
            "dash": "Рывок",
            "disengage": "Отход",
            "move": "Переместиться",
            "rest": "Отдохнуть",
            "help": "Помочь",
            "use_item": "Использовать предмет",
            "equip": "Экипировать",
            "unequip": "Снять",
            "take_item": "Взять предмет",
            "drop_item": "Оставить предмет",
            "interact": "Взаимодействовать",
            "flee": "Покинуть бой",
            "guard": "Защититься",
            "recover": "Восстановиться",
            "expand": "Исследовать новое место",
            "reaction_attack": "Атаковать реакцией",
            "decline_reaction": "Пропустить реакцию",
            "select_actor": "Выбрать персонажа",
        }
        return finish(
            gid, body, fp, after, events, dm, body.text or labels[command.type]
        )

    @router.post("/games/{gid}/roll")
    def roll(gid: str, body: RollRequest):
        state, fp = prepare(gid, body, "roll")
        if state is None:
            return snapshot(gid)
        dm = agent(body)
        after, events = runtime.resolve_roll(state, body.pending_id)
        return finish(gid, body, fp, after, events, dm, "Бросить кубик")

    @router.post("/games/{gid}/rollback")
    def rollback(gid: str, body: Request):
        state, fp = prepare(gid, body, "rollback")
        if state is None:
            return snapshot(gid)
        previous = repo.before_last(gid, body.revision)
        repo.commit(
            gid,
            body.revision,
            body.request_id,
            fp,
            previous,
            [{"text": "Восстановлено состояние до предыдущего действия."}],
            "Откат",
        )
        return snapshot(gid)

    @router.get("/games/{gid}/replay/{revision}")
    def replay(gid: str, revision: int):
        return {"revision": revision, "state": public_state(repo.replay(gid, revision))}

    app.include_router(router)
