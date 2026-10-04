"""Build a connected, keyed campaign graph without provider-authored references."""

from .blueprints import CampaignBlueprint, Idea
from .semantic import (
    SemanticCampaignDTO,
    SemanticLocation,
    SemanticFaction,
    SemanticNPC,
    SemanticSecret,
    SemanticObject,
    SemanticQuest,
    SemanticCheck,
    SemanticEncounter,
    SemanticLoot,
)
from .generation_config import GeneratorContext
from .semantic_campaign import SemanticCampaignCompiler

LOCATION_ROLES = [
    "переход",
    "убежище",
    "место обмена",
    "наблюдательный пункт",
    "закрытая зона",
    "место работ",
    "граница",
    "путь снабжения",
    "покинутая площадка",
    "узел связи",
]
NPC_ROLES = [
    ("проводник", "skirmisher"),
    ("свидетель", "support"),
    ("посредник", "controller"),
    ("охранитель", "defender"),
    ("исследователь", "ranged"),
    ("спасатель", "support"),
    ("соперник", "brute"),
    ("мастер", "controller"),
    ("наблюдатель", "ranged"),
    ("посланник", "skirmisher"),
]
QUEST_ROLES = [
    "исследовать",
    "договориться",
    "доставить",
    "восстановить",
    "защитить",
    "сопоставить",
    "найти путь",
    "выбрать исход",
]
SECRET_ROLES = [
    "след события",
    "свидетельство",
    "причина",
    "последствие",
    "чужой интерес",
    "скрытая цена",
    "уязвимость",
    "альтернативный путь",
    "источник",
    "противоречие",
]


class ProceduralCampaignGenerator:
    def semantics(self, blueprint, setting, options):
        b = blueprint
        cfg = options.generation
        targets = cfg.targets
        rng = GeneratorContext(cfg.seed)

        def select(group, label):
            return rng.rng(group, label)

        def name(base, role):
            return f"{base[:80]}: {role}"[:120]

        bases = b.locations or [
            Idea(name=setting.name[:85] + ": начало", description=b.starting_situation)
        ]
        locations = [
            SemanticLocation(
                key=f"place/{i}", name=v.name, description=v.description, mood=b.tone
            )
            for i, v in enumerate(bases)
        ]
        while len(locations) < targets["locations"]:
            i = len(locations)
            parent = bases[i % len(bases)]
            role = LOCATION_ROLES[i - len(bases)]
            locations.append(
                SemanticLocation(
                    key=f"place/{i}",
                    name=name(parent.name, role),
                    description=f"Назначение: {role}. {parent.description} {b.central_conflict}"[
                        :2000
                    ],
                    environment=[role],
                    danger=("low", "medium", "high")[i % 3],
                    mood=b.tone,
                )
            )
        # Spanning tree plus a seeded extra route; every edge is reciprocal.
        for i in range(1, len(locations)):
            parent = select("topology", str(i)).randrange(i)
            locations[i].connections.append(locations[parent].key)
            locations[parent].connections.append(locations[i].key)
        if len(locations) > 2 and locations[-1].key not in locations[0].connections:
            locations[0].connections.append(locations[-1].key)
            locations[-1].connections.append(locations[0].key)
        factions = []
        affiliation_keys = {}

        def affiliation(idea):
            if idea is None:
                return None
            identity = (idea.name.strip().casefold(), idea.description.strip())
            if identity not in affiliation_keys:
                key = f"affiliation/{len(factions)}"
                affiliation_keys[identity] = key
                factions.append(
                    SemanticFaction(
                        key=key, name=idea.name, description=idea.description
                    )
                )
            return affiliation_keys[identity]

        for idea in b.factions:
            affiliation(idea)
        player_faction = affiliation(b.player_affiliation)
        secrets = []
        secret_ideas = b.secret_ideas or [
            Idea(name=b.name, description=b.central_conflict or b.premise)
        ]
        for i in range(max(targets["secrets"], len(secret_ideas))):
            base = secret_ideas[i % len(secret_ideas)]
            role = SECRET_ROLES[i]
            loc = locations[select("secret_place", str(i)).randrange(len(locations))]
            secrets.append(
                SemanticSecret(
                    key=f"secret/{i}",
                    name=base.name if i < len(secret_ideas) else name(base.name, role),
                    description=base.description
                    if i < len(secret_ideas)
                    else f"{role.capitalize()}: {base.description} Здесь: {loc.name}."[
                        :2000
                    ],
                    location=loc.key,
                )
            )
        npcs = []
        classes = rng.order(list(setting.content.archetypes), "classes")
        species = rng.order(list(setting.content.species), "species")
        backgrounds = rng.order(list(setting.content.backgrounds), "backgrounds")
        for i in range(max(targets["npcs"], len(b.actors), options.party_size - 1)):
            role, combat_role = NPC_ROLES[i]
            base = b.actors[i] if i < len(b.actors) else None
            loc = locations[i % len(locations)]
            companion = i < options.party_size - 1
            npcs.append(
                SemanticNPC(
                    key=f"actor/{i}",
                    name=base.name if base else name(loc.name, role),
                    description=base.description
                    if base
                    else f"{role.capitalize()} в {loc.name}. {b.central_conflict}"[
                        :2000
                    ],
                    location=locations[0].key if companion else loc.key,
                    faction=affiliation(base.affiliation) if base else None,
                    profession=classes[i % len(classes)],
                    species=species[i % len(species)],
                    background=backgrounds[i % len(backgrounds)],
                    role=combat_role,
                    motivation=base.motivation if base else b.central_conflict,
                    knowledge=base.knowledge
                    if base
                    else [loc.description or b.premise],
                    known_secrets=[secrets[i % len(secrets)].key],
                    companion=companion,
                )
            )
        for i, npc in enumerate(npcs[1:], 1):
            npc.relationships[npcs[i - 1].key] = select("relations", str(i)).choice(
                ["neutral", "friendly", "hostile"]
            )
        skills = rng.order(list(setting.content.skills), "checks")
        objects, checks = [], []
        for i in range(max(targets["objects"], len(secrets))):
            secret = secrets[i % len(secrets)]
            kind = ["свидетельство", "запас", "преграда", "укрытие"][i % 4]
            caps = [
                ["openable"],
                ["container"],
                ["lockable", "destructible"],
                ["cover"],
            ][i % 4]
            objects.append(
                SemanticObject(
                    key=f"object/{i}",
                    name=name(secret.name, kind),
                    description=f"{kind.capitalize()}, связанное с событиями: {b.premise}"[
                        :2000
                    ],
                    location=secret.location,
                    secrets=[secret.key],
                    capabilities=caps,
                    expertise=skills[i % len(skills)],
                    loot=[SemanticLoot(category="medical")] if kind == "запас" else [],
                )
            )
        for i, secret in enumerate(secrets):
            checks.append(
                SemanticCheck(
                    key=f"check/{i}",
                    name=name(secret.name, "изучить"),
                    location=secret.location,
                    expertise=skills[i % len(skills)],
                    reveals=secret.key,
                    difficulty=("low", "medium", "high")[i % 3],
                )
            )
        quests = []
        hooks = b.quest_hooks or [
            Idea(name=b.name, description=b.central_conflict or b.premise)
        ]
        for i in range(max(targets["quests"], len(hooks))):
            hook = hooks[i % len(hooks)]
            role = QUEST_ROLES[i]
            quests.append(
                SemanticQuest(
                    key=f"quest/{i}",
                    name=hook.name if i < len(hooks) else name(hook.name, role),
                    description=hook.description,
                    location=locations[i % len(locations)].key,
                    giver=npcs[i % len(npcs)].key,
                    goals=[
                        f"{role.capitalize()}: {hook.description or hook.name}"[:120]
                    ],
                    clues=[objects[i % len(objects)].name],
                    dependencies=[quests[(i - 1) // 2].key] if i else [],
                    possible_outcomes=[v[:120] for v in b.developments[:3]]
                    or [
                        "Договориться об изменении ситуации",
                        "Сохранить положение дел",
                    ],
                    consequences=[v[:120] for v in b.developments[:3]],
                    reward=[SemanticLoot(category="medical")],
                )
            )
        encounters = []
        creatures = rng.order(list(setting.content.creatures), "encounters")
        for i in range(targets["encounters"] if creatures else 0):
            loc = locations[(i + 1) % len(locations)]
            key = creatures[i % len(creatures)]
            encounters.append(
                SemanticEncounter(
                    key=f"encounter/{i}",
                    name=name(loc.name, setting.content.creatures[key].name[:35]),
                    description=b.central_conflict,
                    location=loc.key,
                    creatures=[key],
                    difficulty="low" if i == 0 else "medium",
                )
            )
        # Non-creature phenomena remain environment hazards, never humanoid monsters.
        source = setting.semantic_source or {}
        for i, threat in enumerate(source.get("threat_families", [])):
            if threat.get("nature") == "phenomenon":
                objects.append(
                    SemanticObject(
                        key=f"hazard/{i}",
                        name=threat["name"],
                        description=threat.get("description", ""),
                        location=locations[-1].key,
                        capabilities=["flammable"],
                        expertise=skills[0],
                    )
                )
        return SemanticCampaignDTO(
            name=b.name,
            premise=b.central_conflict or b.premise,
            starting_situation=options.starting_situation or b.starting_situation,
            starting_location=locations[0].key,
            player_hooks=b.player_hooks or [v.name for v in b.quest_hooks],
            player_faction=player_faction,
            locations=locations,
            factions=factions,
            npcs=npcs,
            secrets=secrets,
            objects=objects,
            quests=quests,
            checks=checks,
            encounters=encounters,
            developments=b.developments,
        )

    def generate(self, id, blueprint, setting, options):
        dto = self.semantics(blueprint, setting, options)
        result = SemanticCampaignCompiler().compile(id, dto, setting, options)
        result.semantic_source = blueprint.model_dump(mode="json")
        return result
