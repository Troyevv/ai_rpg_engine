"""Utility scores behind behavior guards; no provider calls."""
from .models import Command


class GameAI:
    def options(self, state, actor_id):
        actor = state.actor(actor_id)
        enemies = [x for x in state.actors().values() if x.faction != actor.faction and x.location == actor.location and x.hp > 0 and not set(x.conditions) & {'dead', 'fled'}]
        if not enemies:
            return [(1.0, Command(type='end_turn'))]
        danger = 1 - actor.hp / actor.max_hp
        options = [(.15 + danger * .2, Command(type='dodge'))]
        # Self-preservation utility is deliberately independent of the player's wishes.
        if actor.hp / actor.max_hp < .3:
            options.append((danger * (1 - actor.morale), Command(type='move', distance=-actor.speed)))
        weapon = next(iter(actor.attacks), None)
        if weapon is None:
            return options
        for target in enemies:
            distance = abs(target.position - actor.position)
            utility = .45 + .1 * (1 - target.hp / target.max_hp)
            if distance <= actor.attacks[weapon].reach:
                options.append((utility, Command(type='attack', target=target.id, weapon=weapon)))
            elif actor.speed:
                delta = target.position - actor.position
                options.append((utility - .05, Command(type='move', distance=(1 if delta > 0 else -1) * min(abs(delta), actor.speed))))
        return options

    def decide(self, state, actor_id):
        return max(self.options(state, actor_id), key=lambda option: option[0])[1]
