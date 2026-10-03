"""Progress is earned from confirmed campaign outcomes; level-up only selects options."""

from ..encounter import event
from ..features import FeatureEngine
from ..spells import SpellSlotState


class ProgressionService:
    def __init__(self, runtime):
        self.runtime = runtime

    @staticmethod
    def reconcile(state, events):
        if not state.ruleset.levels:
            return
        sources = [("encounter", i) for i in state.completed_encounters] + [
            ("quest", i) for i, status in state.quests.items() if status == "completed"
        ]
        for kind, source in sources:
            key = kind + ":" + source
            if key in state.rewarded_progression:
                continue
            state.rewarded_progression.append(key)
            for aid in state.party:
                a = state.actor(aid)
                xp = state.ruleset.progression[kind + "_xp"]
                milestone = state.ruleset.progression["milestone_" + kind]
                a.xp += xp
                a.milestones += milestone
                event(
                    events,
                    f"{a.name}: +{xp} опыта.",
                    kind="progression",
                    actor=aid,
                    xp=xp,
                    milestones=milestone,
                    source=key,
                )

    @staticmethod
    def options(state, a):
        rule = state.ruleset.levels.get(str(a.level + 1))
        eligible = bool(
            rule
            and (
                a.xp >= rule.xp
                if state.campaign.progression_mode == "xp"
                else a.milestones >= a.level
            )
        )
        if not rule:
            return {"available": False, "maximum": True}
        cls = state.ruleset.classes[a.character_class]
        spell_slots = rule.spell_slots.get(a.character_class, {})
        highest = max(map(int, spell_slots), default=0)
        return {
            "available": eligible,
            "maximum": False,
            "level": a.level + 1,
            "required_xp": rule.xp,
            "mode": state.campaign.progression_mode,
            "proficiency": rule.proficiency,
            "hp_base": cls["hit_die"] // 2 + 1,
            "asi": rule.asi,
            "features": [
                state.ruleset.features[i].model_dump()
                for i in rule.features.get(a.character_class, [])
            ],
            "subclasses": (
                [
                    v.model_dump()
                    for v in state.ruleset.subclasses.get(
                        a.character_class, {}
                    ).values()
                ]
                if rule.subclass and not a.subclass
                else []
            ),
            "feats": (
                [
                    state.ruleset.features[i].model_dump()
                    for i in state.ruleset.feats
                    if i not in a.feats
                ]
                if rule.asi
                else []
            ),
            "spell_slots": spell_slots,
            "learn_spells": (
                rule.learn_spells
                if a.character_class in state.ruleset.spellcasting
                else 0
            ),
            "spells": (
                [
                    s.model_dump()
                    for s in state.ruleset.spells.values()
                    if a.character_class in s.classes
                    and s.level <= highest
                    and s.id not in a.spells
                ]
                if spell_slots
                else []
            ),
        }

    def execute(self, state, c, aid, events):
        a = state.actor(aid)
        if state.encounter:
            raise ValueError("Повышение уровня доступно вне боя")
        options = self.options(state, a)
        if not options["available"]:
            raise ValueError("Новый уровень ещё недоступен")
        rule = state.ruleset.levels[str(a.level + 1)]
        new_features = rule.features.get(a.character_class, [])[:]
        if options["subclasses"]:
            subclass = state.ruleset.subclasses[a.character_class].get(c.subclass)
            if not subclass:
                raise ValueError("Выбери допустимый подкласс")
            a.subclass = c.subclass
            new_features += subclass.features
        elif c.subclass:
            raise ValueError("На этом уровне подкласс не выбирается")
        previous_con = self.runtime.rules.modifier(a.abilities["constitution"])
        if rule.asi:
            if c.feat_id:
                if (
                    c.ability_increases
                    or c.feat_id not in state.ruleset.feats
                    or c.feat_id in a.feats
                ):
                    raise ValueError("Выбери новую черту вместо характеристик")
                a.feats.append(c.feat_id)
                new_features.append(c.feat_id)
            else:
                if len(c.ability_increases) != 2:
                    raise ValueError(
                        "Распредели два очка характеристик или выбери черту"
                    )
                for ability in c.ability_increases:
                    if a.abilities[ability] >= 20:
                        raise ValueError("Характеристика не может превышать 20")
                    a.abilities[ability] += 1
        elif c.feat_id or c.ability_increases:
            raise ValueError("На этом уровне нет улучшения характеристик")
        allowed = {s["id"] for s in options["spells"]}
        if (
            len(c.learn_spells) > options["learn_spells"]
            or len(c.learn_spells) != len(set(c.learn_spells))
            or not set(c.learn_spells) <= allowed
        ):
            raise ValueError("Выбери доступные заклинания нового уровня")
        new_con = self.runtime.rules.modifier(a.abilities["constitution"])
        hp_gain = (
            max(1, options["hp_base"] + new_con) + (new_con - previous_con) * a.level
        )
        a.level += 1
        a.proficiency_bonus = rule.proficiency
        a.max_hp += hp_gain
        a.hp += hp_gain
        a.resources["hit_dice"] = a.resources.get("hit_dice", 0) + 1
        new_features = [fid for fid in new_features if fid not in a.features]
        FeatureEngine.apply_passives(
            a, [state.ruleset.features[i] for i in new_features]
        )
        a.features.extend(new_features)
        a.spells.extend(c.learn_spells)
        for tier, maximum in options["spell_slots"].items():
            previous = a.spell_slots.get(tier, SpellSlotState(maximum=0, remaining=0))
            a.spell_slots[tier] = SpellSlotState(
                maximum=maximum,
                remaining=previous.remaining + max(0, maximum - previous.maximum),
            )
        self.runtime.rules.equipment_stats(a, state.items)
        event(
            events,
            f"{a.name} достигает уровня {a.level}.",
            kind="level_up",
            actor=aid,
            level=a.level,
            hp_gain=hp_gain,
            features=new_features,
            spells=c.learn_spells,
        )
