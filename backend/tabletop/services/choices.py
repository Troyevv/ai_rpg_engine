"""Durable player choices contain bounded commands, never arbitrary state edits."""

from uuid import uuid4
from ..models import PendingChoice
from ..encounter import event
from ..projection import PublicProjection


class ChoiceService:
    def __init__(self, runtime):
        self.runtime = runtime

    def request(self, state, command, actor, events):
        self.runtime.owned(state, actor)
        if not state.session_state.mechanical_resolution_complete:
            raise ValueError("Сначала заверши ожидающее действие")
        ids = [option.id for option in command.options]
        if len(ids) != len(set(ids)):
            raise ValueError("Варианты выбора должны иметь разные ID")
        visible = PublicProjection.build(state)
        # Choices may only name visible entities. Hidden decisions stay in interpretation.
        allowed = (
            set(visible["npcs"])
            | set(visible["characters"])
            | {
                x["id"]
                for x in visible["objects"]
                + visible["locations"]
                + visible["encounters"]
            }
        )
        for option in command.options:
            c = option.command
            if c.actor_id and c.actor_id != actor:
                raise ValueError("Выбор не может передать управление другому участнику")
            target = getattr(c, "target", "")
            if target and target not in allowed:
                raise ValueError("Цель выбора недоступна игроку")
            if c.type in ("reaction_attack", "decline_reaction", "select_actor"):
                raise ValueError("Этот тип действия не является вариантом выбора DM")
        state.session_state.choice = PendingChoice(
            id=uuid4().hex,
            actor=actor,
            player_id=state.controllers[actor].player_id,
            kind=command.kind,
            prompt=command.prompt,
            options=command.options,
        )
        event(events, command.prompt, kind="choice")

    def resolve(self, state, command, player_id):
        choice = state.session_state.choice
        if not choice or choice.id != command.pending_id:
            raise ValueError("Выбор уже выполнен или устарел")
        actor = command.actor_id or choice.actor
        self.runtime.owned(state, actor, player_id)
        if actor != choice.actor or choice.player_id != player_id:
            raise ValueError("Выбор принадлежит другому участнику")
        option = next((o for o in choice.options if o.id == command.option_id), None)
        if not option:
            raise ValueError("Неизвестный вариант выбора")
        state.session_state.choice = None
        return option.command.model_copy(update={"actor_id": actor})
