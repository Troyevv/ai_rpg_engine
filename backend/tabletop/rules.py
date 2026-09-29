"""D20 mechanics selected by ruleset capabilities/configuration."""
from .models import CharacterSheet


class RulesEngine:
    @staticmethod
    def modifier(score):
        return (score - 10) // 2

    @staticmethod
    def proficiency(actor):
        return 2 + (actor.level - 1) // 4

    def check_modifier(self, actor, ability, skill, rules):
        if skill and (skill not in rules.skills or rules.skills[skill] != ability):
            raise ValueError('Навык не соответствует характеристике')
        return self.modifier(actor.abilities[ability]) + (self.proficiency(actor) if skill in actor.skill_proficiencies else 0)

    def save_modifier(self, actor, ability):
        return self.modifier(actor.abilities[ability]) + (self.proficiency(actor) if ability in actor.save_proficiencies else 0)

    def attack_modifier(self, actor, weapon):
        attack = actor.attacks.get(weapon)
        if not attack:
            raise ValueError('Оружие недоступно')
        return self.modifier(actor.abilities[attack.ability]) + (self.proficiency(actor) if attack.proficient else 0)

    @staticmethod
    def hit(roll, ac):
        return roll.selected == 20 or roll.selected != 1 and roll.total >= ac

    @staticmethod
    def damage(actor: CharacterSheet, amount, critical=False):
        amount = max(0, amount)
        before = actor.hp
        if 'dead' in actor.conditions or amount == 0:
            return 0
        actor.hp = max(0, before - amount)
        if amount - before >= actor.max_hp:
            actor.conditions = ['dead']
        elif actor.hp == 0:
            actor.conditions = [x for x in actor.conditions if x not in ('stable', 'dodge')]
            if 'unconscious' not in actor.conditions:
                actor.conditions.append('unconscious')
            if before == 0:
                actor.death_failures = min(3, actor.death_failures + (2 if critical else 1))
                if actor.death_failures >= 3:
                    actor.conditions = ['dead']
        return before - actor.hp

    @staticmethod
    def heal(actor, amount):
        if 'dead' in actor.conditions:
            raise ValueError('Погибшего нельзя вылечить отдыхом')
        before = actor.hp
        actor.hp = min(actor.max_hp, actor.hp + max(0, amount))
        if actor.hp:
            actor.conditions = [x for x in actor.conditions if x not in ('unconscious', 'stable')]
            actor.death_successes = actor.death_failures = 0
        return actor.hp - before

    def death_save(self, actor, roll):
        if roll.selected == 20:
            self.heal(actor, 1)
        elif roll.total >= 10:
            actor.death_successes = min(3, actor.death_successes + 1)
            if actor.death_successes == 3:
                actor.conditions.append('stable')
        else:
            actor.death_failures = min(3, actor.death_failures + (2 if roll.selected == 1 else 1))
            if actor.death_failures == 3:
                actor.conditions = ['dead']
