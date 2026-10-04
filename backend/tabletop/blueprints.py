"""Small creative provider contracts. No references, counts or mechanical models."""

from typing import Annotated, Literal
from pydantic import Field
from .semantic import SemanticModel, Name, Text, Names


class Idea(SemanticModel):
    name: Name
    description: Text = ""


class EquipmentFamily(Idea):
    purpose: Literal["weapon", "protection", "recovery", "tool", "device"] = "tool"
    medium: Literal["contact", "projectile", "field"] = "contact"


class PowerTradition(Idea):
    practice: Literal["learned", "innate", "technical"] = "technical"


class ThreatFamily(Idea):
    nature: Literal["living", "construct", "phenomenon"] = "living"


class WorldBlueprint(SemanticModel):
    name: Name
    premise: Annotated[str, Field(min_length=1, max_length=2000)]
    genre: Text = ""
    tone: Text = ""
    themes: Names = []
    peoples: list[Idea] = Field(default_factory=list, max_length=4)
    cultures: list[Idea] = Field(default_factory=list, max_length=4)
    factions: list[Idea] = Field(default_factory=list, max_length=4)
    archetypes: list[Idea] = Field(default_factory=list, max_length=4)
    origins: list[Idea] = Field(default_factory=list, max_length=4)
    skill_domains: list[Idea] = Field(default_factory=list, max_length=4)
    equipment_families: list[EquipmentFamily] = Field(
        default_factory=list, max_length=6
    )
    power_traditions: list[PowerTradition] = Field(default_factory=list, max_length=3)
    threat_families: list[ThreatFamily] = Field(default_factory=list, max_length=4)
    locations: list[Idea] = Field(default_factory=list, max_length=4)
    world_rules: Names = []
    lore: list[Text] = Field(default_factory=list, max_length=6)


class LocalActorIdea(Idea):
    motivation: Text = ""
    knowledge: list[Text] = Field(default_factory=list, max_length=20)


class ActorIdea(LocalActorIdea):
    affiliation: Idea | None = None  # Inline creative concept, not a name reference.


class CampaignBlueprint(SemanticModel):
    name: Name
    premise: Annotated[str, Field(min_length=1, max_length=2000)]
    central_conflict: Text = ""
    starting_situation: Annotated[str, Field(min_length=1, max_length=2000)]
    tone: Text = ""
    actors: list[ActorIdea] = Field(default_factory=list, max_length=4)
    locations: list[Idea] = Field(default_factory=list, max_length=4)
    factions: list[Idea] = Field(default_factory=list, max_length=4)
    secret_ideas: list[Idea] = Field(default_factory=list, max_length=4)
    quest_hooks: list[Idea] = Field(default_factory=list, max_length=4)
    developments: list[Text] = Field(default_factory=list, max_length=6)
    player_hooks: Names = []
    player_affiliation: Idea | None = None


def world_context(setting):
    """Constant-bounded semantics, including for imported pre-blueprint worlds."""
    source = setting.semantic_source or {}
    if "premise" in source and "professions" not in source:
        return WorldBlueprint.model_validate(source).model_dump()

    def ideas(group):
        return [
            dict(name=v.name, description=v.description[:400])
            for v in list(getattr(setting.content, group).values())[:4]
        ]

    return dict(
        name=setting.name,
        premise=setting.description[:2000],
        genre=setting.genre,
        tone=setting.tone,
        themes=setting.themes[:8],
        lore=setting.custom_lore[:6],
        cultures=source.get("cultures", [])[:4],
        factions=source.get("factions", [])[:4],
        archetypes=ideas("archetypes"),
        peoples=ideas("species"),
        skill_domains=ideas("skills"),
        equipment_families=ideas("items"),
        threat_families=ideas("creatures"),
        locations=source.get("environments", [])[:4],
        technology=setting.technology_description[:1000],
        supernatural=setting.supernatural_description[:1000],
    )


class ExpansionBlueprint(SemanticModel):
    """A local creative addition; attachments and references are code-owned too."""

    locations: list[Idea] = Field(default_factory=list, max_length=2)
    actors: list[LocalActorIdea] = Field(default_factory=list, max_length=3)
    equipment_families: list[EquipmentFamily] = Field(
        default_factory=list, max_length=3
    )
    threat_families: list[ThreatFamily] = Field(default_factory=list, max_length=2)
    objects: list[Idea] = Field(default_factory=list, max_length=3)
