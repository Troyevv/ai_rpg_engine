"""Deterministic cross-reference validation; never repairs or mutates definitions."""

from types import SimpleNamespace
from pydantic import BaseModel, ConfigDict, ValidationError, Field


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    code: str
    entity_type: str
    entity_id: str
    field: str
    reference: str = ""
    stage: str = "reference"
    source_id: str = ""
    target_id: str = ""
    context: dict = Field(default_factory=dict)
    message: str


class CampaignValidationError(ValueError):
    def __init__(self, issues, stage="reference", definition=None):
        self.issues = list(issues)
        self.stage = stage
        self.definition = definition
        super().__init__("\n".join(i.message for i in self.issues))

    def public_message(self):
        heading = {
            "reference": "Модель создала мир с некорректными связями.",
            "schema": "Ответ модели не соответствует структуре кампании.",
            "semantic": "Мир нарушает правила кампании.",
        }.get(self.stage, "Определение кампании некорректно.")
        # All issues remain available in diagnostics; bound the ordinary error text.
        lines = ["Не удалось создать кампанию.", heading]
        lines.extend("• " + i.message for i in self.issues[:12])
        if len(self.issues) > 12:
            lines.append(f"Ещё ошибок: {len(self.issues) - 12}. Открой диагностику.")
        lines.append("Исправь черновик или повтори генерацию.")
        return "\n".join(lines)


def schema_error(exc: ValidationError):
    issues = []
    for error in exc.errors(
        include_input=False, include_context=False, include_url=False
    ):
        field = ".".join(str(p) for p in error["loc"]) or "definition"
        reason = (
            "отсутствует обязательное поле"
            if error["type"] == "missing"
            else "недопустимое значение или формат поля"
        )
        issues.append(
            ValidationIssue(
                code=error["type"],
                stage="schema",
                entity_type="campaign",
                entity_id="",
                field=field,
                message=f"{field}: {reason}.",
            )
        )
    return CampaignValidationError(issues, stage="schema")


class CampaignReferenceValidator:
    def validate(self, definition, ruleset) -> list[ValidationIssue]:
        d = definition
        targets = {
            "region": {x.id for x in d.regions},
            "location": {x.id for x in d.locations},
            "faction": {x.id for x in d.factions},
            "actor": {x.id for x in d.characters + d.creatures + d.creature_instances},
            "secret": {x.id for x in d.secrets},
            "item": {x.id for x in ruleset.items + d.items},
            "object": {x.id for x in d.objects},
            "quest": {x.id for x in d.quests},
        }
        labels = {
            "region": "регион",
            "location": "место",
            "faction": "фракция",
            "actor": "персонаж",
            "secret": "секрет",
            "item": "предмет",
            "object": "объект",
            "quest": "задание",
        }
        issues = []

        def check(kind, entity, field, reference, target):
            if reference is not None and reference not in targets[target]:
                issues.append(
                    ValidationIssue(
                        code="unknown_reference",
                        entity_type=kind,
                        entity_id=entity.id,
                        field=field,
                        reference=reference,
                        source_id=entity.id,
                        target_id=reference,
                        message=f"{entity.name} ({entity.id}): {field} → отсутствует {labels[target]} «{reference}».",
                    )
                )

        def many(kind, entity, field, refs, target):
            for ref in refs:
                check(kind, entity, field, ref, target)

        for l in d.locations:
            check("location", l, "region_id", l.region_id, "region")
            many("location", l, "connections", l.connections, "location")
            many("location", l, "travel_minutes", sorted(l.travel_minutes), "location")
        for kind, actors in [("character", d.characters), ("creature", d.creatures)]:
            for a in actors:
                check(kind, a, "location_id", a.location_id, "location")
                check(kind, a, "faction_id", a.faction_id, "faction")
                many(kind, a, "knowledge", a.knowledge, "secret")
                many(kind, a, "relationships", sorted(a.relationships), "actor")
                many(
                    kind,
                    a,
                    "inventory.item_id",
                    [e.item_id for e in a.inventory],
                    "item",
                )
                many(kind, a, "build.equipment", a.build.equipment, "item")
        for actor in d.creature_instances:
            check("creature", actor, "location_id", actor.location_id, "location")
            check("creature", actor, "faction_id", actor.faction_id, "faction")
            many("creature", actor, "knowledge", actor.knowledge, "secret")
            many("creature", actor, "relationships", actor.relationships, "actor")
            many("creature", actor, "inventory", actor.inventory, "item")
            template = (
                d.setting_definition.content.creatures.get(actor.template_id)
                if d.setting_definition
                else None
            )
            if not template:
                issues.append(
                    ValidationIssue(
                        code="missing_content_reference",
                        entity_type="creature",
                        entity_id=actor.id,
                        field="template_id",
                        target_id=actor.template_id,
                        reference=actor.template_id,
                        message="Шаблон существа отсутствует в Setting",
                    )
                )
            else:
                if actor.current_hp is not None and actor.current_hp > template.base_hp:
                    issues.append(
                        ValidationIssue(
                            code="creature_hp_bounds",
                            entity_type="creature",
                            entity_id=actor.id,
                            field="current_hp",
                            message="HP экземпляра превышает максимум шаблона",
                        )
                    )
                for rid, amount in actor.resources.items():
                    definition = d.setting_definition.content.resources.get(rid)
                    if (
                        rid not in template.resources
                        or not definition
                        or not 0 <= amount <= definition.maximum
                    ):
                        issues.append(
                            ValidationIssue(
                                code="invalid_resource",
                                entity_type="creature",
                                entity_id=actor.id,
                                field="resources",
                                reference=rid,
                                message="Недопустимый ресурс экземпляра",
                            )
                        )
        for action in d.context_actions:
            check(
                "context_action", action, "location_id", action.location_id, "location"
            )
            if action.object_id:
                check("context_action", action, "object_id", action.object_id, "object")
            if action.actor_id:
                check("context_action", action, "actor_id", action.actor_id, "actor")
            for field, ref, available in [
                ("check_id", action.check_id, {c.id for c in d.checks}),
                ("feature_id", action.feature_id, set(ruleset.features)),
            ]:
                if ref and ref not in available:
                    issues.append(
                        ValidationIssue(
                            code="unknown_reference",
                            entity_type="context_action",
                            entity_id=action.id,
                            field=field,
                            reference=ref,
                            message="Контекстное действие ссылается на отсутствующий контент",
                        )
                    )
            for field, available in [
                ("skills", ruleset.skills),
                ("backgrounds", ruleset.backgrounds),
                ("archetypes", ruleset.classes),
                ("features", ruleset.features),
                ("items", targets["item"]),
                ("equipment", targets["item"]),
                ("knowledge", targets["secret"]),
                ("conditions", ruleset.condition_definitions),
                ("without_conditions", ruleset.condition_definitions),
            ]:
                for ref in getattr(action.requirements, field):
                    if ref not in available:
                        issues.append(
                            ValidationIssue(
                                code="missing_content_reference",
                                entity_type="context_action",
                                entity_id=action.id,
                                field="requirements." + field,
                                reference=ref,
                                message="Требование действия ссылается на отсутствующий контент",
                            )
                        )
        for s in d.secrets:
            check("secret", s, "location_id", s.location_id, "location")
        for o in d.objects:
            check("object", o, "location_id", o.location_id, "location")
            many("object", o, "secrets", o.secrets, "secret")
            many(
                "object", o, "contents.item_id", [e.item_id for e in o.contents], "item"
            )
        for q in d.quests:
            check("quest", q, "location_id", q.location_id, "location")
            check("quest", q, "giver_id", q.giver_id, "actor")
            check("quest", q, "required_item", q.required_item, "item")
            many("quest", q, "reward.item_id", [e.item_id for e in q.reward], "item")
        for e in d.encounters:
            check("encounter", e, "location_id", e.location_id, "location")
            many("encounter", e, "participants", e.participants, "actor")
            check("encounter", e, "loot_object", e.loot_object, "object")
            check("encounter", e, "quest_id", e.quest_id, "quest")
        for schedule in d.schedules:
            check("schedule", schedule, "actor_id", schedule.actor_id, "actor")
            check(
                "schedule",
                schedule,
                "destination_id",
                schedule.destination_id,
                "location",
            )
            check("schedule", schedule, "after_quest", schedule.after_quest, "quest")
        for n, r in enumerate(d.faction_relations):
            # Relations have no standalone entity ID: identify their stable array slot.
            relation = SimpleNamespace(
                id=f"faction_relations[{n}]", name="Отношение фракций"
            )
            check("faction_relation", relation, "first", r.first, "faction")
            check("faction_relation", relation, "second", r.second, "faction")
        check("campaign", d, "starting_location", d.starting_location, "location")
        many("campaign", d, "starting_party", d.starting_party, "actor")
        for c in d.checks:
            check("check", c, "location_id", c.location_id, "location")
            check("check", c, "actor_id", c.actor_id, "actor")
            for effect in (
                c.success
                + c.failure
                + (c.critical_success or [])
                + (c.critical_failure or [])
                + c.partial
            ):
                target = {
                    "reveal_secret": "secret",
                    "reveal_object": "object",
                    "attitude": "actor",
                    "alert": "actor",
                    "move": "location",
                }.get(effect.type)
                if target:
                    check("check", c, "effects.target", effect.target, target)
        return issues
