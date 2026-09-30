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
            if e:
                raise ValueError("Во время боя отдых невозможен")
            if c.rest == "short":
                if a.resources.get("hit_dice", 0) <= 0:
                    raise ValueError("Кости здоровья закончились")
                a.resources["hit_dice"] -= 1
                self.runtime.rules.heal(
                    a,
                    max(
                        1, 5 + self.runtime.rules.modifier(a.abilities["constitution"])
                    ),
                )
            else:
                for i in state.party:
                    ally = state.actor(i)
                    if ally.location == a.location and "dead" not in ally.conditions:
                        self.runtime.rules.heal(ally, ally.max_hp)
                        ally.resources.update(hit_dice=ally.level, recovery=1)
            state.game_time += (
                state.ruleset.short_rest_minutes
                if c.rest == "short"
                else state.ruleset.long_rest_minutes
            ) * 60
            event(events, "Отдых завершён.", kind="rest")
