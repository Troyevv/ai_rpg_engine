"""RestService domain behavior."""

from ..encounter import event


class RestService:
    def __init__(self, runtime):
        self.runtime = runtime

    def execute(self, state, c, aid, events):
        a = state.actor(aid)
        e = state.encounter
        t = c.type
        if t == "rest":
            from ..resources import ResourceEngine

            if e:
                raise ValueError("Во время боя отдых невозможен")
            if c.rest == "short":
                if state.ruleset.version < 3 and a.resources.get("hit_dice", 0) <= 0:
                    raise ValueError("Кости здоровья закончились")
                self.runtime.features_service.recharge(a, state.ruleset, "short")
                ResourceEngine.recover(a, state.ruleset, "short")
                if a.resources.get("hit_dice", 0) > 0:
                    a.resources["hit_dice"] -= 1
                    self.runtime.rules.heal(
                        a,
                        max(
                            1,
                            5
                            + self.runtime.rules.modifier(a.abilities["constitution"]),
                        ),
                    )
            else:
                for i in state.party:
                    ally = state.actor(i)
                    if ally.location == a.location and "dead" not in ally.conditions:
                        self.runtime.rules.heal(ally, ally.max_hp)
                        ally.resources.update(hit_dice=ally.level, recovery=1)
                        ResourceEngine.recover(ally, state.ruleset, "long")
                        for slot in ally.spell_slots.values():
                            slot.remaining = slot.maximum
                        self.runtime.features_service.recharge(
                            ally, state.ruleset, "long"
                        )
            state.game_time += (
                state.ruleset.short_rest_minutes
                if c.rest == "short"
                else state.ruleset.long_rest_minutes
            ) * 60
            event(events, "Отдых завершён.", kind="rest")
