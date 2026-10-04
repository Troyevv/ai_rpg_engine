"""Explicit authoring forms; compilation changes representation, never intent or IDs."""

from copy import deepcopy
from typing import Literal
from pydantic import ConfigDict, Field, create_model
from .contracts import Model, Named, Id
from .content import (
    ContentItem,
    WeaponComponent,
    ArmorComponent,
    AmmoComponent,
    MagazineComponent,
    EnergyComponent,
    ToolComponent,
    ConsumableComponent,
    IdentityComponent,
)
from .context_actions import ContextAction, ActionRequirements, ObjectCapability
from .definitions import WorldObject, ItemDefinition


class AuthorModel(Model):
    model_config = ConfigDict(extra="forbid", strict=True)


def form(name, model, exclude=(), additions=None):
    fields = {
        key: (value.annotation, deepcopy(value))
        for key, value in model.model_fields.items()
        if key not in exclude
    }
    fields.update(additions or {})
    return create_model(name, __base__=AuthorModel, **fields)


# Named component fields remove a discriminated union and make combinations explicit.
COMPONENT_FORMS = {
    key: form("Author" + model.__name__, model, ("type",))
    for key, model in {
        "weapon": WeaponComponent,
        "armor": ArmorComponent,
        "ammo": AmmoComponent,
        "magazine": MagazineComponent,
        "energy": EnergyComponent,
        "tool": ToolComponent,
        "consumable": ConsumableComponent,
        "medical": ConsumableComponent,
        "artifact": IdentityComponent,
        "key": IdentityComponent,
        "currency": IdentityComponent,
        "quest": IdentityComponent,
    }.items()
}
ItemAuthor = form(
    "ItemAuthor",
    ContentItem,
    ("components",),
    {
        **{key: (model | None, None) for key, model in COMPONENT_FORMS.items()},
        "container_capacity": (int | None, Field(default=None, ge=1, le=1000)),
    },
)

LegacyItemAuthor = form(
    "LegacyItemAuthor",
    ItemDefinition,
    ("components",),
    {
        **{key: (model | None, None) for key, model in COMPONENT_FORMS.items()},
        "container_capacity": (int | None, Field(default=None, ge=1, le=1000)),
    },
)
ObjectAuthor = form(
    "ObjectAuthor",
    WorldObject,
    ("components",),
    {
        "capabilities": (
            list[
                Literal[
                    "interactable",
                    "lockable",
                    "breakable",
                    "terminal",
                    "hazard",
                    "trap",
                    "cover",
                    "environment",
                ]
            ],
            [],
        ),
        "container_capacity": (int | None, Field(default=None, ge=1, le=1000)),
        "action_ids": (list[Id], []),
        "hit_points": (int, Field(default=1, ge=1, le=1000)),
        "defence": (int, Field(default=10, ge=1, le=30)),
        "damage_expression": (str, ""),
        "damage_type": (str, ""),
        "feature_id": (str, ""),
    },
)


class ContextActionAuthor(AuthorModel):
    id: Id
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    location_id: Id
    object_id: str = ""
    actor_id: str = ""
    requirements: ActionRequirements = Field(default_factory=ActionRequirements)
    operation: Literal["check", "feature", "interact"]
    reference_id: Id


class AuthoringCompiler:
    @staticmethod
    def item(value):
        data = value.model_dump(exclude=set(COMPONENT_FORMS) | {"container_capacity"})
        data["components"] = [
            dict(type=key, **getattr(value, key).model_dump())
            for key in COMPONENT_FORMS
            if getattr(value, key) is not None
        ]
        if value.container_capacity is not None:
            data["components"].append(
                dict(type="container", capacity=value.container_capacity)
            )
        return ContentItem.model_validate(data)

    @staticmethod
    def object(value):
        extras = {
            "capabilities",
            "container_capacity",
            "action_ids",
            "hit_points",
            "defence",
            "damage_expression",
            "damage_type",
            "feature_id",
        }
        data = value.model_dump(exclude=extras)
        from .validation import CampaignValidationError, ValidationIssue

        kinds = set(value.capabilities)
        problems = []
        for field, used in (
            ("capabilities", len(kinds) == len(value.capabilities)),
            (
                "feature_id",
                not value.feature_id
                or bool(kinds & {"interactable", "terminal", "environment"}),
            ),
            (
                "damage_expression",
                not value.damage_expression or bool(kinds & {"hazard", "trap"}),
            ),
            ("damage_type", not value.damage_type or bool(kinds & {"hazard", "trap"})),
            (
                "action_ids",
                not value.action_ids
                or bool(kinds)
                or value.container_capacity is not None,
            ),
        ):
            if not used:
                problems.append(
                    ValidationIssue(
                        code="incompatible_capability_field",
                        entity_type="object",
                        entity_id=value.id,
                        field=field,
                        message="Поле не соответствует объявленным возможностям объекта",
                    )
                )
        if problems:
            raise CampaignValidationError(problems)
        data["components"] = []
        for kind in value.capabilities:
            fields = {"type": kind, "action_ids": value.action_ids}
            if kind == "breakable":
                fields.update(hit_points=value.hit_points, defence=value.defence)
            if kind in ("hazard", "trap"):
                fields.update(
                    damage_expression=value.damage_expression,
                    damage_type=value.damage_type,
                )
            if kind in ("interactable", "terminal", "environment"):
                fields["feature_id"] = value.feature_id
            data["components"].append(ObjectCapability(**fields))
        if value.container_capacity is not None:
            data["components"].append(
                ObjectCapability(
                    type="container",
                    capacity=value.container_capacity,
                    action_ids=value.action_ids,
                )
            )
        return WorldObject.model_validate(data)

    @staticmethod
    def action(value):
        data = value.model_dump(exclude={"operation", "reference_id"})
        if value.operation == "interact":
            if value.object_id and value.object_id != value.reference_id:
                from .validation import CampaignValidationError, ValidationIssue

                raise CampaignValidationError(
                    [
                        ValidationIssue(
                            code="conflicting_reference",
                            entity_type="context_action",
                            entity_id=value.id,
                            field="reference_id",
                            target_id=value.reference_id,
                            message="Цель взаимодействия не совпадает с object_id",
                        )
                    ]
                )
            data.update(object_id=value.reference_id, interaction=True)
        else:
            data[value.operation + "_id"] = value.reference_id
        return ContextAction.model_validate(data)

    @classmethod
    def stage(cls, value):
        data = value.model_dump()
        if hasattr(value, "items") and isinstance(value.items, dict):
            data["items"] = {
                k: cls.item(v).model_dump() for k, v in value.items.items()
            }
        if hasattr(value, "items") and isinstance(value.items, list):
            data["items"] = []
            for item in value.items:
                entry = item.model_dump(
                    exclude=set(COMPONENT_FORMS) | {"container_capacity"}
                )
                entry["components"] = [
                    dict(type=key, **getattr(item, key).model_dump())
                    for key in COMPONENT_FORMS
                    if getattr(item, key) is not None
                ]
                if item.container_capacity is not None:
                    entry["components"].append(
                        dict(type="container", capacity=item.container_capacity)
                    )
                data["items"].append(ItemDefinition.model_validate(entry).model_dump())
        if hasattr(value, "objects"):
            data["objects"] = [cls.object(v).model_dump() for v in value.objects]
        if hasattr(value, "context_actions"):
            data["context_actions"] = [
                cls.action(v).model_dump() for v in value.context_actions
            ]
        return data


def stage_schema(name, root, fields):
    overrides = {
        "objects": list[ObjectAuthor],
        "context_actions": list[ContextActionAuthor],
    }
    overrides["items"] = (
        dict[Id, ItemAuthor]
        if root.__name__ == "ContentRegistry"
        else list[LegacyItemAuthor]
    )
    return create_model(
        name,
        __base__=AuthorModel,
        **{
            key: (
                overrides.get(key, root.model_fields[key].annotation),
                deepcopy(root.model_fields[key]),
            )
            for key in fields
        }
    )


def authoring_payload(data):
    """Encode deterministic fixture definitions in the published authoring representation."""
    data = deepcopy(data)
    if data.get("setting_definition", "absent") is None:
        data.pop("setting_definition")
    if "items" in data:
        items = (
            data["items"].values() if isinstance(data["items"], dict) else data["items"]
        )
        for item in items:
            for component in item.pop("components", []):
                kind = component.pop("type")
                if kind == "container":
                    item["container_capacity"] = component["capacity"]
                else:
                    item[kind] = component
    for obj in data.get("objects", []):
        components = obj.pop("components", [])
        obj["capabilities"] = []
        for component in components:
            if component["type"] == "container":
                obj["container_capacity"] = component["capacity"]
            else:
                obj["capabilities"].append(component["type"])
            for key in (
                "action_ids",
                "hit_points",
                "defence",
                "damage_expression",
                "damage_type",
                "feature_id",
            ):
                if key in component:
                    obj[key] = component[key]
    for action in data.get("context_actions", []):
        check = action.pop("check_id", "")
        feature = action.pop("feature_id", "")
        interact = action.pop("interaction", False)
        action["operation"] = "check" if check else "feature" if feature else "interact"
        action["reference_id"] = check or feature or action["object_id"]
    return data


def authoring_issues(error, raw, generation_id, stage):
    import json
    from .validation import ValidationIssue

    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        payload = {}
    issues = []
    for entry in error.errors(include_input=False):
        entity = generation_id
        node = payload
        for part in entry["loc"]:
            if isinstance(node, dict) and isinstance(node.get("id"), str):
                entity = node["id"]
            try:
                node = node[part]
            except (KeyError, IndexError, TypeError):
                break
        issues.append(
            ValidationIssue(
                code=entry["type"],
                stage=stage,
                entity_type=str(entry["loc"][0]) if entry["loc"] else "authoring",
                entity_id=entity,
                source_id=entity,
                field=".".join(map(str, entry["loc"])),
                message=entry["msg"],
            )
        )
    return issues
