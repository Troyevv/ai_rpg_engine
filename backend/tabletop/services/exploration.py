"""ExplorationService domain behavior."""

from ..rules import DifficultyResolver
from ..encounter import event


class ExplorationService:
    def __init__(self, runtime):
        self.runtime = runtime

    def execute(self, state, c, aid, events):
        a = state.actor(aid)
        e = state.encounter
        t = c.type
        if t == "look":
            location = next(
                (x for x in state.definition.locations if x.id == a.location)
            )
            event(events, location.description or location.name, kind="look")
            state.game_time += 6
        if t == "move":
            if e:
                self.runtime.move(state, aid, c.distance, events)
            else:
                loc = next(
                    (x for x in state.definition.locations if x.id == a.location)
                )
                if c.target not in loc.connections:
                    raise ValueError("Нет пути в эту локацию")
                source = a.location
                for i in state.party:
                    if state.actor(i).location == source:
                        state.actor(i).location = c.target
                        state.actor(i).position = 0
                if c.target not in state.known_locations:
                    state.known_locations.append(c.target)
                state.session_state.mode = "EXPLORATION"
                state.session_state.dialogue_actor = None
                minutes = loc.travel_minutes.get(c.target, 5)
                state.game_time += minutes * 60
                event(events, "Переход: " + state.locations[c.target], kind="travel")
        if t == "interact":
            self.runtime.interact(state, a, c.target, events)

    def interact(self, state, a, target, events, action=False):
        obj = next(
            (
                o
                for o in state.definition.objects
                if o.id == target and o.location_id == a.location
            ),
            None,
        )
        if obj and any(
            (
                e.loot_object == obj.id and e.id not in state.completed_encounters
                for e in state.definition.encounters
            )
        ):
            raise ValueError("Сначала заверши столкновение")
        if not obj or not state.objects[obj.id].revealed:
            raise ValueError("Объект недоступен")
        status = state.objects[obj.id]
        if obj.locked and (not status.unlocked):
            raise ValueError("Объект заперт. Нужна проверка взаимодействия")
        if action:
            self.runtime.spend(state.encounter)
        else:
            self.runtime.interaction(state)
        if obj.trap_damage and (not status.trap_triggered):
            self.runtime.pending(
                state,
                "save",
                a.id,
                ability="dexterity",
                modifier=self.runtime.rules.save_modifier(a, "dexterity"),
                dc=DifficultyResolver.resolve(state.ruleset, obj.difficulty, obj.dc),
                target=obj.id,
                outcome="trap",
            )
            event(events, "Сработала ловушка. Нужен спасбросок.", kind="trap")
            return
        status.opened = True
        self.runtime.reveal_object(state, obj, events)
        event(events, obj.description or "Открыто: " + obj.name, kind="interact")

    @staticmethod
    def reveal_object(state, obj, events):
        for secret in state.definition.secrets:
            if (
                secret.id in obj.secrets
                and secret.disclosure == "search"
                and (secret.id not in state.player_knowledge)
            ):
                state.player_knowledge[secret.id] = secret.description
                event(events, secret.description, kind="discovery")
