"""D20 mechanics selected by ruleset capabilities/configuration."""

from .models import CharacterSheet


class RulesEngine:
    @staticmethod
    def modifier(score):
        return (score - 10) // 2

    @staticmethod
    def proficiency(actor):
        return actor.proficiency_bonus

    def check_modifier(self, actor, ability, skill, rules):
        if skill and (skill not in rules.skills or rules.skills[skill] != ability):
            raise ValueError("Навык не соответствует характеристике")
        return self.modifier(actor.abilities[ability]) + (
            self.proficiency(actor) if skill in actor.skill_proficiencies else 0
        )

    def save_modifier(self, actor, ability):
        return self.modifier(actor.abilities[ability]) + (
            self.proficiency(actor) if ability in actor.save_proficiencies else 0
        )

    def attack_modifier(self, actor, weapon):
        attack = actor.attacks.get(weapon)
        if not attack:
            raise ValueError("Оружие недоступно")
        return self.modifier(actor.abilities[attack.ability]) + (
            self.proficiency(actor) if attack.proficient else 0
        )

    @staticmethod
    def hit(roll, ac):
        return roll.selected == 20 or roll.selected != 1 and roll.total >= ac

    @staticmethod
    def damage(actor: CharacterSheet, amount, critical=False):
        amount = max(0, amount)
        before = actor.hp
        if "dead" in actor.conditions or amount == 0:
            return 0
        actor.hp = max(0, before - amount)
        if amount - before >= actor.max_hp:
            actor.conditions = ["dead"]
        elif actor.hp == 0:
            actor.conditions = [
                x for x in actor.conditions if x not in ("stable", "dodge")
            ]
            if "unconscious" not in actor.conditions:
                actor.conditions.append("unconscious")
            if before == 0:
                actor.death_failures = min(
                    3, actor.death_failures + (2 if critical else 1)
                )
                if actor.death_failures >= 3:
                    actor.conditions = ["dead"]
        return before - actor.hp

    @staticmethod
    def heal(actor, amount):
        if "dead" in actor.conditions:
            raise ValueError("Погибшего нельзя вылечить отдыхом")
        before = actor.hp
        actor.hp = min(actor.max_hp, actor.hp + max(0, amount))
        if actor.hp:
            actor.conditions = [
                x for x in actor.conditions if x not in ("unconscious", "stable")
            ]
            actor.death_successes = actor.death_failures = 0
        return actor.hp - before

    def death_save(self, actor, roll):
        if roll.selected == 20:
            self.heal(actor, 1)
        elif roll.total >= 10:
            actor.death_successes = min(3, actor.death_successes + 1)
            if actor.death_successes == 3:
                actor.conditions.append("stable")
        else:
            actor.death_failures = min(
                3, actor.death_failures + (2 if roll.selected == 1 else 1)
            )
            if actor.death_failures == 3:
                actor.conditions = ["dead"]

    def validate_build(self, build, rules):
        if (
            build.character_class not in rules.classes
            or build.species not in rules.species
            or build.background not in rules.backgrounds
        ):
            raise ValueError("Неизвестный класс, вид или происхождение")
        if set(build.abilities) != set(rules.abilities) or sorted(
            build.abilities.values()
        ) != sorted(rules.ability_array):
            raise ValueError(
                "Распредели стандартный набор характеристик без повторного использования значений"
            )
        cls = rules.classes[build.character_class]
        if (
            len(set(build.skills)) != cls["skill_count"]
            or len(build.skills) != len(set(build.skills))
            or not set(build.skills) <= set(cls["skills"])
        ):
            raise ValueError("Выбери допустимые навыки класса")
        if sorted(build.equipment) not in [
            sorted(e) for e in cls.get("equipment_choices", [cls["equipment"]])
        ]:
            raise ValueError(
                "Стартовое снаряжение должно соответствовать набору класса"
            )
        return build

    def build_character(self, definition, rules):
        from .models import CharacterSheet
        from .definitions import InventoryEntry

        b = self.validate_build(definition.build, rules)
        cls = rules.classes[b.character_class]
        hp = max(1, cls["hit_die"] + self.modifier(b.abilities["constitution"]))
        inventory = [
            InventoryEntry(
                item_id=i,
                equipped=next(x for x in rules.items if x.id == i).type
                in ("weapon", "armor"),
            )
            for i in b.equipment
        ]
        inventory.extend(e.model_copy(deep=True) for e in definition.inventory)
        actor = CharacterSheet(
            id=definition.id,
            name=b.name,
            character_class=b.character_class,
            species=b.species,
            proficiency_bonus=rules.progression["proficiency_base"],
            background=b.background,
            biography=b.biography,
            appearance=b.appearance,
            personality=b.personality or definition.personality,
            ideals=b.ideals,
            bonds=b.bonds,
            flaws=b.flaws,
            abilities=b.abilities.copy(),
            skill_proficiencies=b.skills[:],
            save_proficiencies=cls["saves"][:],
            hp=hp,
            max_hp=hp,
            armor_class=10,
            speed=rules.species[b.species]["speed"],
            position=definition.position,
            inventory=inventory,
            resources={"hit_dice": 1, "recovery": 1},
            faction=definition.faction_id,
            location=definition.location_id,
            goals=definition.goals[:],
            knowledge=definition.knowledge[:],
            public_lore=definition.public_lore[:],
            relationships=definition.relationships.copy(),
            morale=definition.morale,
            attitude=definition.attitude,
            current_intent=definition.current_intent,
        )
        return actor

    def equipment_stats(self, actor, items):
        from .models import Attack

        actor.attacks = {}
        actor.armor_class = 10 + self.modifier(actor.abilities["dexterity"])
        armors = []
        for e in actor.inventory:
            item = items[e.item_id]
            if e.equipped and item.type == "weapon":
                actor.attacks[item.id] = Attack(
                    name=item.name,
                    ability=item.weapon_ability,
                    die=item.weapon_die,
                    reach=item.reach,
                )
            if e.equipped and item.type == "armor":
                armors.append(item)
        if len(armors) > 1:
            raise ValueError("Можно надеть только одну броню")
        if armors:
            actor.armor_class = armors[0].armor_base + min(
                armors[0].dex_cap, self.modifier(actor.abilities["dexterity"])
            )
        # Unarmed attacks are a universal supported primitive, not a campaign item.
        if not actor.attacks:
            actor.attacks["unarmed"] = Attack(name="Без оружия", die=4)


class DifficultyResolver:
    @staticmethod
    def resolve(rules, category, authoritative=None):
        if authoritative is not None:
            return authoritative
        if category not in rules.difficulty:
            raise ValueError("Неизвестная сложность")
        return rules.difficulty[category]
