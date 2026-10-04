"""Build internal semantic content from a fixed-size creative blueprint."""

from .blueprints import WorldBlueprint, Idea
from .semantic import (
    SemanticSettingDTO,
    SemanticSpecies,
    SemanticProfession,
    SemanticBackground,
    SemanticSkill,
    SemanticItem,
    SemanticCreature,
    SemanticFeature,
    Concept,
)
from .generation_coverage import world_coverage, PROFESSIONS, SKILLS
from .procedural_content import ProceduralContentCompiler


class ProceduralWorldGenerator:
    def semantics(self, blueprint, config):
        b = WorldBlueprint.model_validate(
            blueprint.model_dump()
            if isinstance(blueprint, WorldBlueprint)
            else blueprint
        )
        species = b.peoples or [Idea(name="Обитатели " + b.name[:90])]
        roles = b.archetypes or [Idea(name=b.name[:80] + ": исследователь")]
        origins = b.origins or b.cultures or [Idea(name=b.name[:80] + ": местный опыт")]
        domains = b.skill_domains or [Idea(name=b.name[:80] + ": среда")]

        def common(v, kind, i):
            return dict(key=f"{kind}/{i}", name=v.name, description=v.description)

        professions = []
        for i, v in enumerate(roles):
            tradition = (
                b.power_traditions[i % len(b.power_traditions)]
                if b.power_traditions
                else None
            )
            role = PROFESSIONS[i % len(PROFESSIONS)]
            abilities = [SemanticFeature(name=v.name[:90] + ": приём", intent=role[2])]
            casting = "none"
            if tradition:
                abilities = [
                    SemanticFeature(
                        name=tradition.name[:90] + ": воздействие", intent="damage"
                    ),
                    SemanticFeature(
                        name=tradition.name[:90] + ": восстановление", intent="healing"
                    ),
                ]
                if tradition.practice == "learned":
                    casting = "prepared_slots"
            professions.append(
                SemanticProfession(
                    **common(v, "profession", i),
                    role=role[1],
                    abilities=abilities,
                    casting=casting,
                    power_source=tradition.description if tradition else "",
                )
            )
        dto = SemanticSettingDTO(
            name=b.name,
            description=b.premise,
            genre=b.genre,
            tone=b.tone,
            themes=b.themes,
            cultures=[Concept(**v.model_dump()) for v in b.cultures],
            factions=[Concept(**v.model_dump()) for v in b.factions],
            lore=b.world_rules + b.lore,
            technology="; ".join(
                v.description for v in b.power_traditions if v.practice == "technical"
            )[:2000],
            supernatural="; ".join(
                v.description for v in b.power_traditions if v.practice != "technical"
            )[:2000],
            species=[
                SemanticSpecies(**common(v, "species", i))
                for i, v in enumerate(species)
            ],
            professions=professions,
            backgrounds=[
                SemanticBackground(
                    **common(v, "origin", i), knowledge=b.world_rules[:2]
                )
                for i, v in enumerate(origins)
            ],
            skills=[
                SemanticSkill(
                    **common(v, "skill", i), affinity=SKILLS[i % len(SKILLS)][1]
                )
                for i, v in enumerate(domains)
            ],
            items=[
                SemanticItem(
                    **common(v, "equipment", i),
                    category={"protection": "armor", "recovery": "medical"}.get(
                        v.purpose, v.purpose
                    ),
                    style="melee" if v.medium == "contact" else "ranged",
                    supply="ammunition"
                    if v.medium == "projectile" and v.purpose == "weapon"
                    else "none",
                )
                for i, v in enumerate(b.equipment_families)
            ],
            creatures=[
                SemanticCreature(
                    **common(v, "threat", i),
                    role="minion",
                    behavior=v.description,
                    tags=[v.nature],
                )
                for i, v in enumerate(b.threat_families)
                if v.nature != "phenomenon"
            ],
        )
        return world_coverage(dto, config)

    def generate(self, id, blueprint, config, revision=0):
        dto = self.semantics(blueprint, config)
        world = ProceduralContentCompiler().compile(id, dto, revision, config)
        world.semantic_source = blueprint.model_dump(mode="json")
        world.world_rules = blueprint.world_rules[:]
        for field in ("peoples", "archetypes", "origins", "skill_domains"):
            if not getattr(blueprint, field):
                world.diagnostics.append(
                    dict(
                        code="default_concept",
                        entity=field,
                        message="Не задано творческое семейство; использован нейтральный базовый вариант.",
                    )
                )
        return world
