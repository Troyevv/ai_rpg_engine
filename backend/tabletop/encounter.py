"""Initiative, action economy and automatic NPC turns."""
from .models import Encounter
from .ai import GameAI


def event(events, text, **details):
    events.append({'text': text, **details})


class EncounterEngine:
    def __init__(self, dice, rules):
        self.dice, self.rules, self.ai = dice, rules, GameAI()

    def roll(self, events, expression, **kwargs):
        roll = self.dice.roll(expression, **kwargs)
        event(events, f'Бросок: {roll.total}', roll=roll.as_dict())
        return roll

    def start(self, state, player_roll, events):
        hero = state.actor(state.session_state.controlled_actor)
        actors = [a for a in state.actors().values() if a.location == hero.location and a.hp > 0 and 'fled' not in a.conditions]
        totals = {hero.id: player_roll.total}
        for actor in actors:
            if actor.id != hero.id:
                totals[actor.id] = self.roll(events, '1d20', modifier=self.rules.modifier(actor.abilities['dexterity']), purpose='initiative', actor=actor.id).total
        order = sorted(totals, key=lambda i: (-totals[i], -state.actor(i).abilities['dexterity'], i))
        state.encounters['current'] = Encounter(order=order, initiative=totals, reaction={i: True for i in order})
        state.active_encounter = 'current'
        state.session_state.mode = 'ENCOUNTER'
        self.reset_turn(state)
        event(events, 'Бой начался. Определена инициатива.', kind='encounter')

    @staticmethod
    def reset_turn(state):
        e = state.encounter
        actor = state.actor(e.order[e.index])
        e.action, e.bonus_action, e.disengaged = True, True, False
        e.reaction[actor.id], e.movement = True, actor.speed
        actor.conditions = [c for c in actor.conditions if c != 'dodge']

    def advance(self, state):
        e = state.encounter
        e.index = (e.index + 1) % len(e.order)
        if e.index == 0:
            e.round += 1
            state.game_time += 6
        self.reset_turn(state)

    @staticmethod
    def ended(state, events):
        active = [a for a in state.actors().values() if a.id in state.encounter.order and a.hp > 0 and not set(a.conditions) & {'dead', 'fled'}]
        factions = {a.faction for a in active}
        if len(factions) > 1:
            return False
        won = factions == {'party'}
        state.active_encounter = None
        state.session_state.mode = 'EXPLORATION'
        if won:
            state.quests['watch'] = 'Обитатели заставы больше не угрожают партии.'
        event(events, 'Бой завершён: победа партии.' if won else 'Бой завершён: партия выведена из боя.', kind='encounter_end')
        return True

    def validate_attack(self, state, actor_id, target_id, weapon):
        actor, target = state.actor(actor_id), state.actor(target_id)
        self.rules.attack_modifier(actor, weapon)
        if target.hp == 0 or set(target.conditions) & {'dead', 'fled'} or target.faction == actor.faction or target.location != actor.location:
            raise ValueError('Цель атаки недоступна')
        if abs(actor.position - target.position) > actor.attacks[weapon].reach:
            raise ValueError('Цель вне досягаемости: сначала подойди')
        return actor, target

    def npc_attack(self, state, actor_id, target_id, weapon, events):
        actor, target = self.validate_attack(state, actor_id, target_id, weapon)
        roll = self.roll(events, '1d20', modifier=self.rules.attack_modifier(actor, weapon), advantage=-1 if 'dodge' in target.conditions else 0, purpose='attack', actor=actor_id)
        if self.rules.hit(roll, target.armor_class):
            attack = actor.attacks[weapon]
            damage = self.roll(events, f'1d{attack.die}', modifier=self.rules.modifier(actor.abilities[attack.ability]), critical=roll.selected == 20, critical_rule=state.ruleset.critical, purpose='damage', actor=actor_id)
            dealt = self.rules.damage(target, damage.total, critical=roll.selected == 20)
            event(events, f'{actor.name} атакует {target.name}: урон {dealt}.', kind='damage', actor=actor_id, target=target_id, amount=dealt)
        else:
            event(events, f'{actor.name} промахивается по {target.name}.', kind='miss')

    def move(self, state, actor_id, distance, events):
        e, actor = state.encounter, state.actor(actor_id)
        if abs(distance) > e.movement or not distance:
            raise ValueError('Недостаточно перемещения')
        new_position = actor.position + distance
        actor.position = new_position
        e.movement -= abs(distance)
        event(events, f'{actor.name}: перемещение на {distance} футов.', kind='move')

    def run_npcs(self, state, events):
        for _ in range(100):
            if not state.encounter or self.ended(state, events):
                return
            e = state.encounter
            actor = state.actor(e.order[e.index])
            if actor.id == state.session_state.controlled_actor and not set(actor.conditions) & {'dead', 'stable', 'fled'}:
                return
            if actor.hp > 0 and not set(actor.conditions) & {'dead', 'fled'}:
                command = self.ai.decide(state, actor.id)
                if command.type == 'move':
                    self.move(state, actor.id, command.distance, events)
                    if actor.hp / actor.max_hp < .3 and actor.morale < .6:
                        actor.conditions.append('fled')
                        event(events, f'{actor.name} бежит с поля боя.', kind='flee')
                    else:
                        command = self.ai.decide(state, actor.id)
                if command.type == 'attack':
                    self.npc_attack(state, actor.id, command.target, command.weapon, events)
                elif command.type == 'dodge':
                    actor.conditions.append('dodge')
            self.advance(state)
        raise ValueError('Не удалось завершить очередь NPC')
