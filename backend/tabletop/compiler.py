"""Validate all references before a campaign can become canonical state."""

from .definitions import CampaignDefinition, CampaignMutation
from .catalog import load_ruleset
from .models import GameState, Campaign, ActorControl, SessionState, ObjectState
from .rules import RulesEngine
from pydantic import ValidationError
from .validation import (
    CampaignReferenceValidator,
    CampaignValidationError,
    ValidationIssue,
    schema_error,
)


def index(values):
    out = {v.id: v for v in values}
    if len(out) != len(values):
        raise ValueError("Повтор ID в определении кампании")
    return out


class CampaignCompiler:
    def validate(self, definition):
        try:
            d = CampaignDefinition.model_validate(
                definition.model_dump()
                if isinstance(definition, CampaignDefinition)
                else definition
            )
        except ValidationError as exc:
            raise schema_error(exc) from None
        try:
            rules = load_ruleset(d.ruleset_id)
            issues = CampaignReferenceValidator().validate(d, rules)
            if issues:
                raise CampaignValidationError(issues, definition=d)
            self.validate_semantics(d, rules)
        except CampaignValidationError:
            raise
        except ValueError as exc:
            raise CampaignValidationError(
                [
                    ValidationIssue(
                        code="semantic_validation",
                        entity_type="campaign",
                        entity_id=d.id,
                        field="definition",
                        message=str(exc),
                    )
                ],
                stage="semantic",
                definition=d,
            ) from None
        return d

    def validate_semantics(self, d, rules):
        # Cross references are already complete. These checks enforce their meaning.
        if d.ruleset_version != rules.version:
            raise ValueError("Несовместимая версия ruleset")
        groups = [
            index(values)
            for values in (
                d.regions,
                d.locations,
                d.factions,
                d.characters + d.creatures,
                rules.items + d.items,
                d.objects,
                d.quests,
                d.secrets,
                d.encounters,
            )
        ]
        all_ids = [i for group in groups for i in group]
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("ID должны быть уникальны между типами сущностей")
        _, locations, _, actors, items, objects, _, secrets, encounters = groups

        def require(ok, message):
            if not ok:
                raise ValueError(message)

        require(
            len(set(d.starting_party)) == len(d.starting_party),
            "Повтор участника в стартовой партии",
        )
        require(
            any(
                actors[i].controller == "PLAYER"
                and (actors[i].player_id or "local") == "local"
                for i in d.starting_party
            ),
            "В партии нужен локальный игрок",
        )

        def inventory(entries):
            require(
                all(
                    not e.equipped or items[e.item_id].type in ("weapon", "armor")
                    for e in entries
                ),
                "Нельзя экипировать этот предмет",
            )

        visited, todo = set(), [d.starting_location]
        while todo:
            loc = todo.pop()
            if loc not in visited:
                visited.add(loc)
                todo.extend(locations[loc].connections)
        require(
            visited == set(locations), "Все локации должны быть достижимы из стартовой"
        )
        pairs = set()
        for r in d.faction_relations:
            pair = tuple(sorted((r.first, r.second)))
            require(
                r.first != r.second and pair not in pairs,
                "Некорректное отношение фракций",
            )
            pairs.add(pair)
        for a in actors.values():
            require(
                a.controller == "PLAYER" or a.player_id is None,
                f"Персонаж '{a.id}': AI/DM не может владеть player_id",
            )
            RulesEngine().validate_build(a.build, rules)
            inventory(a.inventory)
        require(
            all(actors[i].location_id == d.starting_location for i in d.starting_party),
            "Партия должна начинать в одной локации",
        )
        for o in objects.values():
            require(
                all(secrets[i].location_id == o.location_id for i in o.secrets),
                f"Объект '{o.id}': секрет должен принадлежать его локации",
            )
            require(
                not o.check_skill or rules.skills.get(o.check_skill) == o.check_ability,
                f"Объект '{o.id}': неверный навык проверки",
            )
            inventory(o.contents)
        for q in d.quests:
            inventory(q.reward)
        for e in encounters.values():
            require(
                len(set(e.participants)) == len(e.participants),
                f"Столкновение '{e.id}': повтор участника",
            )
            require(
                all(actors[i].location_id == e.location_id for i in e.participants),
                f"Столкновение '{e.id}': участники должны находиться на его локации",
            )
            require(
                e.loot_object is None
                or objects[e.loot_object].location_id == e.location_id,
                f"Столкновение '{e.id}': добыча должна находиться на его локации",
            )
        for item in items.values():
            require(
                not item.healing or item.type == "consumable",
                f"Предмет '{item.id}': лечение разрешено только расходуемым предметам",
            )

    def compile(self, definition, character=None):
        d = self.validate(definition).model_copy(deep=True)
        if character:
            slot = next(
                a
                for a in d.characters + d.creatures
                if a.id in d.starting_party
                and a.controller == "PLAYER"
                and (a.player_id or "local") == "local"
            )
            slot.build = RulesEngine().validate_build(
                character, load_ruleset(d.ruleset_id)
            )
            slot.name = character.name
        rules = load_ruleset(d.ruleset_id)
        items = index(rules.items + d.items)
        actors = {
            a.id: RulesEngine().build_character(a, rules)
            for a in d.characters + d.creatures
        }
        for a in actors.values():
            RulesEngine().equipment_stats(a, items)
        controllers = {
            a.id: ActorControl(
                actor_id=a.id,
                controller=a.controller,
                player_id=(
                    (a.player_id or "local") if a.controller == "PLAYER" else None
                ),
            )
            for a in d.characters + d.creatures
        }
        controlled = next(
            i
            for i in d.starting_party
            if controllers[i].controller == "PLAYER"
            and controllers[i].player_id == "local"
        )
        return GameState(
            definition=d,
            campaign=Campaign(
                name=d.name,
                setting_id=d.setting.id,
                starting_location=d.starting_location,
            ),
            world=d.setting,
            ruleset=rules,
            party=d.starting_party[:],
            characters={i: actors[i] for i in d.starting_party},
            npcs={i: a for i, a in actors.items() if i not in d.starting_party},
            controllers=controllers,
            locations={x.id: x.name for x in d.locations},
            items=items,
            objects={
                o.id: ObjectState(
                    revealed=not o.hidden
                    and not any(e.loot_object == o.id for e in d.encounters),
                    contents=o.contents,
                )
                for o in d.objects
            },
            quests={
                q.id: "active" if not q.giver_id else "available" for q in d.quests
            },
            known_locations=[d.starting_location],
            session_state=SessionState(controlled_actor=controlled),
        )

    def extend(self, original, mutation: CampaignMutation):
        state = original.model_copy(deep=True)
        d = state.definition
        collections = {
            "CreateLocation": "locations",
            "CreateNPC": "characters",
            "CreateItem": "items",
            "CreateQuest": "quests",
            "CreateEncounter": "encounters",
            "CreateObject": "objects",
            "CreateFaction": "factions",
        }
        reveals = []
        new_actors = []
        new_objects = []
        new_items = []
        new_quests = []
        existing_secrets = {s.id for s in d.secrets}
        for op in mutation.operations:
            if op.type in collections:
                if op.type == "CreateNPC":
                    if op.value.controller != "AI" or op.value.knowledge:
                        raise ValueError(
                            "Динамический NPC не получает управление игрока или старые секреты"
                        )
                    new_actors.append(op.value)
                if op.type == "CreateObject":
                    if set(op.value.secrets) & existing_secrets:
                        raise ValueError(
                            "Нельзя перепривязать существующие секреты к новому объекту"
                        )
                    new_objects.append(op.value)
                if op.type == "CreateItem":
                    new_items.append(op.value)
                if op.type == "CreateQuest":
                    new_quests.append(op.value)
                getattr(d, collections[op.type]).append(op.value)
            elif op.type == "ConnectLocations":
                locs = index(d.locations)
                if op.first not in locs or op.second not in locs:
                    raise ValueError("Неизвестные локации соединения")
                for a, b in ((op.first, op.second), (op.second, op.first)):
                    if b not in locs[a].connections:
                        locs[a].connections.append(b)
            else:
                reveals.append(op)
        self.validate(d)
        state.locations = {x.id: x.name for x in d.locations}
        state.items.update(index(new_items))
        for a in new_actors:
            actor = RulesEngine().build_character(a, state.ruleset)
            RulesEngine().equipment_stats(actor, state.items)
            state.npcs[a.id] = actor
            state.controllers[a.id] = ActorControl(actor_id=a.id, controller="AI")
        for o in new_objects:
            state.objects[o.id] = ObjectState(
                revealed=not o.hidden
                and not any(e.loot_object == o.id for e in d.encounters),
                contents=o.contents,
            )
        for q in new_quests:
            state.quests[q.id] = "available" if q.giver_id else "active"
        for op in reveals:
            obj = next((o for o in d.objects if o.id == op.source_id), None)
            if (
                not obj
                or op.secret_id not in obj.secrets
                or not state.objects[obj.id].opened
                or obj.location_id
                != state.actor(state.session_state.controlled_actor).location
            ):
                raise ValueError("Нет подтверждённого основания раскрыть знание")
            secret = next(s for s in d.secrets if s.id == op.secret_id)
            if secret.disclosure == "never":
                raise ValueError("Секрет не подлежит раскрытию")
            state.player_knowledge[secret.id] = secret.description
        return GameState.model_validate(state.model_dump())
