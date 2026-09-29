"""Command → validated copy → events. Persistence owns the atomic commit."""
from uuid import uuid4
from .models import GameState, NewGame, CharacterSheet, Attack, Campaign, Command, PendingRoll
from .dice import DiceEngine
from .rules import RulesEngine
from .encounter import EncounterEngine, event


def new_game(options: NewGame):
    hero = CharacterSheet(id='hero', name=options.character_name, biography=options.biography)
    chars = {'hero': hero}
    if options.companion:
        chars['theron'] = CharacterSheet(id='theron', name='Терон', hp=10, max_hp=10, position=5, morale=.8, traits=['осторожный'], goals=['защитить партию'])
    return GameState(campaign=Campaign(name=options.name, setting_id=options.setting.id), world=options.setting.model_copy(deep=True), ruleset=options.ruleset.model_copy(deep=True), characters=chars, party=list(chars),
                     npcs={'goblin': CharacterSheet(id='goblin', name='Гоблин-дозорный', hp=14, max_hp=14, armor_class=13, position=5, faction='hostile', morale=.3, attacks={'knife': Attack(name='Кинжал', die=4)}, inventory=['Кинжал'])},
                     dm_state={'objects': {'chest': {'name': 'Старый сундук', 'location': 'gate', 'dc': 12, 'knowledge_key': 'cache', 'secret': 'За сундуком спрятан ключ от караульной башни.'}}})


class TabletopRuntime:
    def __init__(self, dice=None):
        self.dice, self.rules = dice or DiceEngine(), RulesEngine()
        self.combat = EncounterEngine(self.dice, self.rules)

    def pending(self, state, purpose, **kwargs):
        resume = 'ENCOUNTER' if state.encounter else state.session_state.mode
        state.session_state.pending = PendingRoll(id=uuid4().hex, purpose=purpose, actor=state.session_state.controlled_actor, resume=resume, **kwargs)
        state.session_state.mode = 'AWAITING_ROLL'

    def execute(self, original, command: Command):
        state, events = original.model_copy(deep=True), []
        if state.session_state.pending:
            raise ValueError('Сначала выполни ожидающий бросок')
        actor = state.actor(state.session_state.controlled_actor)
        if actor.hp == 0 or 'dead' in actor.conditions:
            raise ValueError('Персонаж не может действовать. Откати ход или начни новую кампанию.')
        e = state.encounter
        if e and e.order[e.index] != actor.id:
            raise ValueError('Сейчас ход другого участника')
        t = command.type
        if t == 'start_encounter':
            if e or 'combat' not in state.ruleset.capabilities:
                raise ValueError('Бой недоступен')
            if not any(a.hp > 0 and a.faction != actor.faction and a.location == actor.location and 'fled' not in a.conditions for a in state.npcs.values()):
                raise ValueError('Нет противников')
            self.pending(state, 'initiative', modifier=self.rules.modifier(actor.abilities['dexterity']))
            event(events, 'Брось инициативу.', kind='pending')
        elif t in ('check', 'save'):
            if 'checks' not in state.ruleset.capabilities:
                raise ValueError('Проверки отключены')
            if e:
                self.spend_action(e)
            dc = command.dc
            if command.target:
                obj = state.dm_state.get('objects', {}).get(command.target)
                if not obj or obj['location'] != actor.location or command.ability != 'wisdom' or command.skill not in ('', 'perception'):
                    raise ValueError('Эту цель нельзя проверить выбранным способом')
                dc = obj['dc']  # DM cannot lower a scenario's authoritative DC.
            if t == 'save' and (command.target or command.skill):
                raise ValueError('Спасбросок не использует навык или объект')
            modifier = self.rules.save_modifier(actor, command.ability) if t == 'save' else self.rules.check_modifier(actor, command.ability, command.skill, state.ruleset)
            self.pending(state, t, modifier=modifier, ability=command.ability, skill=command.skill, dc=dc, target=command.target)
            event(events, 'Требуется проверка: ' + (command.skill or command.ability), kind='pending')
        elif t == 'attack':
            if not e:
                raise ValueError('Сначала начни бой и брось инициативу')
            _, target = self.combat.validate_attack(state, actor.id, command.target, command.weapon)
            self.spend_action(e)
            self.pending(state, 'attack', modifier=self.rules.attack_modifier(actor, command.weapon), target=target.id, dc=target.armor_class, weapon=command.weapon, advantage=-1 if 'dodge' in target.conditions else 0)
            event(events, f'{actor.name} атакует {target.name}. Брось d20.', kind='pending')
        elif t in ('dodge', 'dash', 'disengage', 'end_turn', 'move'):
            if not e:
                raise ValueError('Действие доступно только в бою')
            if t == 'move':
                self.combat.move(state, actor.id, command.distance, events)
            elif t == 'end_turn':
                self.combat.advance(state)
                self.combat.run_npcs(state, events)
                self.prepare_player(state, events)
            else:
                self.spend_action(e)
                if t == 'dodge':
                    actor.conditions.append('dodge')
                elif t == 'dash':
                    e.movement += actor.speed
                else:
                    e.disengaged = True
                event(events, {'dodge': 'Уклонение до следующего хода.', 'dash': 'Рывок: добавлено перемещение.', 'disengage': 'Отход. Реакции атак в этом ruleset ещё не включены.'}[t])
        elif t == 'rest':
            if e or 'rests' not in state.ruleset.capabilities:
                raise ValueError('Отдых сейчас недоступен')
            if command.rest == 'short':
                if actor.resources.get('hit_dice', 0) <= 0:
                    raise ValueError('Кости здоровья закончились')
                actor.resources['hit_dice'] -= 1
                # All player rolls, including healing, are explicit (future UI contract).
                # Basic rest uses a fixed recovery, not a hidden player dice roll.
                amount = max(1, 5 + self.rules.modifier(actor.abilities['constitution']))
                self.rules.heal(actor, amount)
            else:
                self.rules.heal(actor, actor.max_hp)
                actor.resources['hit_dice'] = actor.level
            state.game_time += (state.ruleset.short_rest_minutes if command.rest == 'short' else state.ruleset.long_rest_minutes) * 60
            event(events, f'Отдых завершён. HP: {actor.hp}/{actor.max_hp}.', kind='rest')
        elif t in ('look', 'dialogue'):
            if t == 'dialogue' and (command.target not in state.actors() or state.actor(command.target).location != actor.location or state.actor(command.target).hp <= 0):
                raise ValueError('Собеседник недоступен')
            if not e:
                state.session_state.mode = 'DIALOGUE' if t == 'dialogue' else 'EXPLORATION'
            event(events, 'Ты осматриваешь двор заставы.' if t == 'look' else 'Собеседник выслушивает тебя. Убеждение не управляет его волей.', kind=t)
        return self.validate(state), events

    @staticmethod
    def spend_action(e):
        if not e.action:
            raise ValueError('Основное действие уже использовано')
        e.action = False

    @staticmethod
    def validate(state):
        return GameState.model_validate(state.model_dump())

    def prepare_player(self, state, events):
        if not state.encounter:
            return
        actor = state.actor(state.session_state.controlled_actor)
        if actor.hp == 0:
            if set(actor.conditions) & {'dead', 'stable'}:
                event(events, 'Персонаж выведен из боя. Доступен откат.', kind='incapacitated')
            else:
                self.pending(state, 'death', dc=10)
                event(events, 'Брось спасбросок от смерти.', kind='pending')

    def resolve_roll(self, original, pending_id):
        state, events = original.model_copy(deep=True), []
        p = state.session_state.pending
        if not p or p.id != pending_id:
            raise ValueError('Этот бросок уже выполнен или устарел')
        actor = state.actor(p.actor)
        roll = self.combat.roll(events, p.expression, modifier=p.modifier, advantage=p.advantage, purpose=p.purpose, actor=p.actor, critical=p.critical, critical_rule=state.ruleset.critical)
        state.session_state.pending = None
        state.session_state.mode = p.resume
        if p.purpose in ('check', 'save'):
            success = roll.total >= p.dc  # 1/20 are not automatic check successes/failures.
            event(events, 'Проверка успешна.' if success else 'Проверка не пройдена.', kind='check', success=success)
            if success and p.target:
                obj = state.dm_state['objects'][p.target]
                state.player_knowledge[obj['knowledge_key']] = obj['secret']
                event(events, obj['secret'], kind='discovery')
            state.game_time += 60
        elif p.purpose == 'initiative':
            self.combat.start(state, roll, events)
            self.combat.run_npcs(state, events)
            self.prepare_player(state, events)
        elif p.purpose == 'attack':
            if self.rules.hit(roll, state.actor(p.target).armor_class):
                attack = actor.attacks[p.weapon]
                self.pending(state, 'damage', expression=f'1d{attack.die}', modifier=self.rules.modifier(actor.abilities[attack.ability]), target=p.target, weapon=p.weapon, critical=roll.selected == 20)
                event(events, 'Критическое попадание! Брось урон.' if roll.selected == 20 else 'Попадание! Брось урон.', kind='hit')
            else:
                event(events, 'Промах.', kind='miss')
        elif p.purpose == 'damage':
            dealt = self.rules.damage(state.actor(p.target), roll.total, critical=p.critical)
            event(events, f'Нанесён урон: {dealt}.', kind='damage', actor=p.actor, target=p.target, amount=dealt)
            self.combat.ended(state, events)
        elif p.purpose == 'death':
            self.rules.death_save(actor, roll)
            event(events, f'Спасброски от смерти: {actor.death_successes} успехов, {actor.death_failures} провалов.', kind='death')
            if actor.hp == 0 and state.encounter:
                self.combat.advance(state)
                self.combat.run_npcs(state, events)
                self.prepare_player(state, events)
        return self.validate(state), events
