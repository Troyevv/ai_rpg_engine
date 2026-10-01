"""Validated commands are the only path to a new canonical snapshot."""

from uuid import uuid4
from .models import GameState, Command, PendingRoll
from .dice import DiceEngine
from .rules import RulesEngine
from .encounter import EncounterEngine
from .ai import GameAI


from .services.checks import CheckService
from .services.exploration import ExplorationService
from .services.inventory import InventoryService
from .services.encounters import EncounterService
from .services.dialogue import DialogueService
from .services.rest import RestService
from .services.characters import CharacterService
from .services.choices import ChoiceService
from .services.features import FeatureService
from .services.tactics import TacticalService


class TabletopRuntime:
    def __init__(self, dice=None):
        self.dice = dice or DiceEngine()
        self.rules = RulesEngine()
        self.combat = EncounterEngine(self.dice, self.rules)
        self.ai = GameAI()
        self.checks_service = CheckService(self)
        self.exploration_service = ExplorationService(self)
        self.inventory_service = InventoryService(self)
        self.encounters_service = EncounterService(self)
        self.dialogue_service = DialogueService(self)
        self.rest_service = RestService(self)
        self.characters_service = CharacterService(self)
        self.choices = ChoiceService(self)
        self.features_service = FeatureService(self)
        self.tactics_service = TacticalService(self)

    @staticmethod
    def validate(state):
        return GameState.model_validate(state.model_dump())

    @staticmethod
    def spend(e, slot="action"):
        if e:
            if not getattr(e, slot):
                raise ValueError("Это действие уже использовано")
            setattr(e, slot, False)

    def interaction(self, state):
        e = state.encounter
        if e:
            self.spend(
                e,
                (
                    "free_interaction"
                    if state.ruleset.version >= 3 and e.free_interaction
                    else "action"
                ),
            )

    @staticmethod
    def owned(state, actor_id, player_id="local"):
        if actor_id not in state.controllers:
            raise ValueError("Участник не найден")
        c = state.controllers[actor_id]
        if c.controller != "PLAYER" or c.player_id != player_id:
            raise ValueError("Этот персонаж не принадлежит твоему контроллеру")
        return state.actor(actor_id)

    def pending(self, state, purpose, actor, **kwargs):
        c = state.controllers[actor]
        state.session_state.pending = PendingRoll(
            id=uuid4().hex,
            purpose=purpose,
            actor=actor,
            controller=c.controller,
            player_id=c.player_id,
            resume=(
                "ENCOUNTER"
                if state.encounter
                else (
                    "DIALOGUE"
                    if state.session_state.mode == "DIALOGUE"
                    else "EXPLORATION"
                )
            ),
            **kwargs
        )
        state.session_state.mode = "AWAITING_ROLL"

    def execute(self, original, command, player_id="local"):
        state = original.model_copy(deep=True)
        events = []
        command = Command.model_validate(
            command.model_dump() if hasattr(command, "model_dump") else command
        )
        if command.type == "resolve_choice":
            command = self.choices.resolve(state, command, player_id)
        elif state.session_state.choice:
            raise ValueError("Сначала выбери вариант ожидающего действия")
        aid = command.actor_id or state.session_state.controlled_actor
        self.owned(state, aid, player_id)
        if state.session_state.pending:
            raise ValueError("Сначала выполни ожидающий бросок")
        if state.session_state.reaction:
            if command.type not in ("reaction_attack", "decline_reaction"):
                raise ValueError("Сначала реши, использовать ли реакцию")
            reaction = state.session_state.reaction
            if reaction["actor"] != aid:
                raise ValueError("Реакция принадлежит другому участнику")
            state.encounter.reaction[aid] = False
            if command.type == "decline_reaction":
                self.resume_reaction(state, events)
            else:
                self.attack(
                    state,
                    aid,
                    reaction["mover"],
                    reaction["weapon"],
                    events,
                    reaction=True,
                )
        else:
            self.apply(state, command, aid, events)
            if state.encounter and (not state.session_state.pending):
                self.drive(state, events)
        return (self.validate(state), events)

    def apply(self, state, c, aid, events):
        a = state.actor(aid)
        e = state.encounter
        t = c.type
        if t == "select_actor":
            return self.characters_service.execute(state, c, aid, events)
        if (
            a.hp <= 0
            and (not (t == "rest" and "stable" in a.conditions and (not e)))
            or set(a.conditions) & {"dead", "fled"}
        ):
            raise ValueError("Персонаж сейчас не может действовать")
        if self.rules.conditions.blocked(a, state.ruleset) and t not in (
            "end_turn",
            "rest",
        ):
            raise ValueError("Состояние персонажа запрещает действия")
        if e and t != "guard" and (e.order[e.index] != aid):
            raise ValueError("Сейчас ход другого участника")
        if t == "request_choice":
            return self.choices.request(state, c, aid, events)
        services = {
            "use_feature": self.features_service,
            **{
                name: self.tactics_service
                for name in (
                    "hide",
                    "search",
                    "stand",
                    "escape",
                    "grapple",
                    "shove",
                    "ready",
                    "surrender",
                    "seek_cover",
                    "use_object",
                )
            },
            "look": self.exploration_service,
            "move": self.exploration_service,
            "interact": self.exploration_service,
            "select_actor": self.characters_service,
            "check": self.checks_service,
            "save": self.checks_service,
            "take_item": self.inventory_service,
            "drop_item": self.inventory_service,
            "equip": self.inventory_service,
            "unequip": self.inventory_service,
            "use_item": self.inventory_service,
            "start_encounter": self.encounters_service,
            "attack": self.encounters_service,
            "end_turn": self.encounters_service,
            "dodge": self.encounters_service,
            "dash": self.encounters_service,
            "disengage": self.encounters_service,
            "help": self.encounters_service,
            "guard": self.encounters_service,
            "recover": self.encounters_service,
            "flee": self.encounters_service,
            "dialogue": self.dialogue_service,
            "rest": self.rest_service,
        }
        service = services.get(t)
        if not service:
            raise ValueError("Команда требует отдельного обработчика")
        service.execute(state, c, aid, events)

    def check(self, state, c, a, events):
        return self.checks_service.check(state, c, a, events)

    def resolve_roll(self, original, pending_id, player_id="local"):
        return self.checks_service.resolve_roll(original, pending_id, player_id)

    def interact(self, state, a, target, events):
        return self.exploration_service.interact(state, a, target, events)

    @staticmethod
    def reveal_object(state, obj, events):
        return ExplorationService.reveal_object(state, obj, events)

    @staticmethod
    def entry(actor, item_id):
        return InventoryService.entry(actor, item_id)

    @staticmethod
    def add(entries, item_id, quantity):
        return InventoryService.add(entries, item_id, quantity)

    @staticmethod
    def remove(entries, item_id, quantity):
        return InventoryService.remove(entries, item_id, quantity)

    def inventory(self, state, c, a, events):
        return self.inventory_service.inventory(state, c, a, events)

    def attack(self, state, aid, target, weapon, events, reaction=False):
        return self.encounters_service.attack(
            state, aid, target, weapon, events, reaction
        )

    def initiative(self, state, events):
        return self.encounters_service.initiative(state, events)

    def move(self, state, aid, distance, events):
        return self.encounters_service.move(state, aid, distance, events)

    def resume_reaction(self, state, events):
        return self.encounters_service.resume_reaction(state, events)

    def drive(self, state, events):
        return self.encounters_service.drive(state, events)
