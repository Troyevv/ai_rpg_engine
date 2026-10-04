"""Validate all references before a campaign can become canonical state."""

from .definitions import CampaignDefinition, CampaignMutation
from .content_registry import campaign_rules
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
            rules = campaign_rules(d)
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
        issues = []

        def require(ok, code, kind, entity, field, message, target="", **context):
            if not ok:
                issues.append(
                    ValidationIssue(
                        code=code,
                        stage="semantic",
                        entity_type=kind,
                        entity_id=entity,
                        field=field,
                        source_id=entity,
                        target_id=target,
                        reference=target,
                        message=message,
                        context=context,
                    )
                )

        require(
            d.ruleset_version == rules.version,
            "ruleset_version",
            "campaign",
            d.id,
            "ruleset_version",
            "Несовместимая версия ruleset",
        )
        groups = [
            ("region", d.regions),
            ("location", d.locations),
            ("faction", d.factions),
            ("actor", d.characters + d.creatures + d.creature_instances),
            ("item", rules.items + d.items),
            ("object", d.objects),
            ("quest", d.quests),
            ("secret", d.secrets),
            ("encounter", d.encounters),
            ("schedule", d.schedules),
            ("check", d.checks),
        ]
        seen = set()
        for kind, entries in groups:
            for entry in entries:
                require(
                    entry.id not in seen,
                    "duplicate_id",
                    kind,
                    entry.id,
                    "id",
                    "ID должны быть уникальны между типами сущностей",
                )
                seen.add(entry.id)
        locations = {v.id: v for v in d.locations}
        actors = {v.id: v for v in d.characters + d.creatures + d.creature_instances}
        items = {v.id: v for v in rules.items + d.items}
        objects = {v.id: v for v in d.objects}
        secrets = {v.id: v for v in d.secrets}
        for check in d.checks:

            def check_issue(ok, code, field, message, target=""):
                require(ok, code, "check", check.id, field, message, target)

            check_issue(
                RulesEngine.valid_skill(rules, check.skill, check.ability),
                "invalid_skill_ability",
                "skill",
                "Навык проверки не соответствует характеристике",
            )
            check_issue(
                not (check.save and check.skill),
                "save_skill_conflict",
                "skill",
                "Спасбросок не использует навык",
            )
            effects = (
                check.success
                + check.failure
                + (check.critical_success or [])
                + (check.critical_failure or [])
                + check.partial
            )
            check_issue(
                not check.passive
                or (
                    (
                        bool(
                            set(rules.skill_definitions[check.skill].tags)
                            & {"PASSIVE_PERCEPTION", "PASSIVE_INSIGHT"}
                        )
                        if check.skill in rules.skill_definitions
                        else check.skill in ("perception", "insight")
                    )
                    and not check.failure
                    and not check.critical_failure
                    and all(
                        e.type in ("reveal_secret", "reveal_object") for e in effects
                    )
                ),
                "invalid_passive_check",
                "passive",
                "Пассивная проверка только обнаруживает сведения",
            )
            check_issue(
                bool(effects),
                "no_meaningful_consequences",
                "success",
                "Проверка требует значимых последствий",
            )
            for outcome in (
                "success",
                "failure",
                "critical_success",
                "critical_failure",
                "partial",
            ):
                for n, effect in enumerate(getattr(check, outcome) or []):
                    field = f"{outcome}.{n}.target"
                    if effect.type == "reveal_secret":
                        check_issue(
                            secrets[effect.target].location_id == check.location_id,
                            "secret_wrong_location",
                            field,
                            "Проверка раскрывает сведения только текущей сцены",
                            effect.target,
                        )
                        check_issue(
                            secrets[effect.target].disclosure != "never",
                            "forbidden_disclosure",
                            field,
                            "Проверка не может раскрывать запретный секрет",
                            effect.target,
                        )
                    if effect.type == "reveal_object":
                        check_issue(
                            objects[effect.target].location_id == check.location_id,
                            "object_wrong_location",
                            field,
                            "Проверка обнаруживает объекты только текущей сцены",
                            effect.target,
                        )
                    if effect.type in ("attitude", "alert"):
                        check_issue(
                            effect.target not in d.starting_party
                            and actors[effect.target].controller != "PLAYER",
                            "player_agency",
                            field,
                            "Проверка не управляет чувствами игрока",
                            effect.target,
                        )
                    if effect.type == "move":
                        check_issue(
                            effect.target in locations[check.location_id].connections,
                            "non_adjacent_move",
                            field,
                            "Проверка перемещения требует соседнюю локацию",
                            effect.target,
                        )
        require(
            len(set(d.starting_party)) == len(d.starting_party),
            "duplicate_party_member",
            "campaign",
            d.id,
            "starting_party",
            "Повтор участника в стартовой партии",
        )
        require(
            d.player_slot is not None
            or any(
                actors[i].controller == "PLAYER"
                and (actors[i].player_id or "local") == "local"
                for i in d.starting_party
            ),
            "missing_local_player",
            "campaign",
            d.id,
            "starting_party",
            "В партии нужен локальный игрок",
        )

        if d.player_slot:
            slot = d.player_slot
            require(
                slot.id not in seen,
                "duplicate_id",
                "player_slot",
                slot.id,
                "id",
                "Слот игрока конфликтует с сущностью",
            )
            require(
                not any(a.controller == "PLAYER" for a in actors.values()),
                "player_agency",
                "campaign",
                d.id,
                "player_slot",
                "Слот и готовый игрок взаимоисключающие",
            )
            require(
                slot.starting_location == d.starting_location,
                "starting_party_mismatch",
                "player_slot",
                slot.id,
                "starting_location",
                "Слот должен начинать в стартовой локации",
            )
            require(
                slot.faction_id is None
                or slot.faction_id in {f.id for f in d.factions},
                "unknown_reference",
                "player_slot",
                slot.id,
                "faction_id",
                "Неизвестная фракция игрока",
            )

        def inventory(entries, kind, entity, field):
            for n, e in enumerate(entries):
                require(
                    not e.equipped or items[e.item_id].type in ("weapon", "armor"),
                    "invalid_equipped_item",
                    kind,
                    entity,
                    f"{field}.{n}",
                    "Нельзя экипировать этот предмет",
                    e.item_id,
                )

        visited, todo = set(), [d.starting_location]
        while todo:
            loc = todo.pop()
            if loc not in visited:
                visited.add(loc)
                todo.extend(locations[loc].connections)
        for loc in sorted(set(locations) - visited):
            require(
                False,
                "unreachable_location",
                "location",
                loc,
                "connections",
                "Все локации должны быть достижимы из стартовой",
                d.starting_location,
            )
        pairs = set()
        for r in d.faction_relations:
            pair = tuple(sorted((r.first, r.second)))
            require(
                r.first != r.second and pair not in pairs,
                "invalid_faction_relation",
                "faction",
                r.first,
                "relations",
                "Некорректное отношение фракций",
                r.second,
            )
            pairs.add(pair)
        for a in actors.values():
            require(
                a.controller == "PLAYER" or a.player_id is None,
                "invalid_player_owner",
                "actor",
                a.id,
                "player_id",
                f"Персонаж '{a.id}': AI/DM не может владеть player_id",
            )
            try:
                if hasattr(a, "build"):
                    RulesEngine().validate_build(a.build, rules)
            except ValueError as exc:
                require(
                    False, "invalid_character_build", "actor", a.id, "build", str(exc)
                )
            if hasattr(a, "build"):
                inventory(a.inventory, "actor", a.id, "inventory")
        for aid in d.starting_party:
            require(
                actors[aid].location_id == d.starting_location,
                "starting_party_mismatch",
                "actor",
                aid,
                "location_id",
                "Партия должна начинать в одной локации",
                d.starting_location,
            )
        for o in objects.values():
            for sid in o.secrets:
                require(
                    secrets[sid].location_id == o.location_id,
                    "secret_wrong_location",
                    "object",
                    o.id,
                    "secrets",
                    f"Объект '{o.id}': секрет должен принадлежать его локации",
                    sid,
                )
            require(
                RulesEngine.valid_skill(rules, o.check_skill, o.check_ability),
                "invalid_skill_ability",
                "object",
                o.id,
                "check_skill",
                f"Объект '{o.id}': неверный навык проверки",
            )
            inventory(o.contents, "object", o.id, "contents")
        for q in d.quests:
            inventory(q.reward, "quest", q.id, "reward")
        for e in d.encounters:
            require(
                len(set(e.participants)) == len(e.participants),
                "duplicate_encounter_participant",
                "encounter",
                e.id,
                "participants",
                f"Столкновение '{e.id}': повтор участника",
            )
            for aid in e.participants:
                require(
                    actors[aid].location_id == e.location_id,
                    "invalid_encounter_participant",
                    "encounter",
                    e.id,
                    "participants",
                    f"Столкновение '{e.id}': участники должны находиться на его локации",
                    aid,
                )
            require(
                e.loot_object is None
                or objects[e.loot_object].location_id == e.location_id,
                "loot_wrong_location",
                "encounter",
                e.id,
                "loot_object",
                f"Столкновение '{e.id}': добыча должна находиться на его локации",
                e.loot_object or "",
            )
        for location in d.locations:
            require(
                set(location.travel_minutes) <= set(location.connections),
                "invalid_travel_time",
                "location",
                location.id,
                "travel_minutes",
                "Время пути задаётся только для связанного места",
            )
        for schedule in d.schedules:
            require(
                actors[schedule.actor_id].controller == "AI"
                and schedule.actor_id not in d.starting_party,
                "invalid_schedule",
                "schedule",
                schedule.id,
                "actor_id",
                "Расписание не может управлять партией или персонажем игрока",
                schedule.actor_id,
            )
        for item in items.values():
            require(
                not item.healing or item.type == "consumable",
                "invalid_item_healing",
                "item",
                item.id,
                "healing",
                f"Предмет '{item.id}': лечение разрешено только расходуемым предметам",
            )
        if issues:
            raise CampaignValidationError(issues, stage="semantic", definition=d)

    def compile(self, definition, character=None):
        d = self.validate(definition).model_copy(deep=True)
        if d.player_slot:
            if character is None:
                raise ValueError("Создай персонажа перед началом игры")
            from .definitions import CharacterDefinition

            placeholder = d.player_slot
            RulesEngine().validate_build(character, campaign_rules(d))
            d.characters.append(
                CharacterDefinition(
                    id=placeholder.id,
                    name=character.name,
                    location_id=placeholder.starting_location,
                    faction_id=placeholder.faction_id,
                    controller="PLAYER",
                    player_id="local",
                    build=character,
                )
            )
            d.starting_party.insert(0, placeholder.id)
            d.player_slot = None
            d = self.validate(d)
        elif character:
            slot = next(
                a
                for a in d.characters + d.creatures + d.creature_instances
                if a.id in d.starting_party
                and a.controller == "PLAYER"
                and (a.player_id or "local") == "local"
            )
            slot.build = RulesEngine().validate_build(character, campaign_rules(d))
            slot.name = character.name
        rules = campaign_rules(d)
        items = index(rules.items + d.items)
        actors = {
            a.id: RulesEngine().build_character(a, rules)
            for a in d.characters + d.creatures
        }
        for a in actors.values():
            RulesEngine().equipment_stats(a, items, rules)
        from .creatures import build_creature

        for instance in d.creature_instances:
            actors[instance.id] = build_creature(instance, d.setting_definition)
        controllers = {
            a.id: ActorControl(
                actor_id=a.id,
                controller=a.controller,
                player_id=(
                    (a.player_id or "local") if a.controller == "PLAYER" else None
                ),
            )
            for a in d.characters + d.creatures + d.creature_instances
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
            faction_reputation={
                f.id: max(
                    -100,
                    min(100, actors[controlled].background_reputation.get(f.id, 0)),
                )
                for f in d.factions
                if f.id in actors[controlled].background_reputation
            },
            player_knowledge={
                "background_" + str(i): text
                for i, text in enumerate(actors[controlled].background_knowledge)
            },
            known_locations=[d.starting_location],
            schedule_due={s.id: s.delay_minutes * 60 for s in d.schedules},
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
            "CreateRegion": "regions",
            "CreateSecret": "secrets",
            "CreateSchedule": "schedules",
            "CreateCheck": "checks",
        }
        created_secret_ids = {
            op.value.id for op in mutation.operations if op.type == "CreateSecret"
        }
        created_actor_ids = {
            op.value.id for op in mutation.operations if op.type == "CreateNPC"
        }
        existing_factions = {f.id for f in d.factions}
        new_schedules = []
        reveals = []
        new_actors = []
        new_objects = []
        new_items = []
        new_quests = []
        existing_secrets = {s.id for s in d.secrets}
        for op in mutation.operations:
            if op.type in collections:
                if op.type == "CreateCheck":
                    effects = (
                        op.value.success
                        + op.value.failure
                        + (op.value.critical_success or [])
                        + (op.value.critical_failure or [])
                        + op.value.partial
                    )
                    if any(
                        e.type == "reveal_secret" and e.target in existing_secrets
                        for e in effects
                    ):
                        raise ValueError(
                            "Нельзя раскрывать старые секреты новыми проверками"
                        )
                if op.type == "CreateSchedule":
                    if op.value.actor_id not in created_actor_ids:
                        raise ValueError(
                            "Расширение задаёт расписания только новым NPC"
                        )
                    new_schedules.append(op.value)
                if op.type == "CreateNPC":
                    if (
                        op.value.controller != "AI"
                        or not set(op.value.knowledge) <= created_secret_ids
                    ):
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
            elif op.type == "DefineFactionRelation":
                relation = op.value
                if (
                    relation.first in existing_factions
                    and relation.second in existing_factions
                ):
                    raise ValueError(
                        "Нельзя менять отношения существующих фракций расширением мира"
                    )
                if any(
                    {r.first, r.second} == {relation.first, relation.second}
                    for r in d.faction_relations
                ):
                    raise ValueError("Отношение фракций уже определено")
                d.faction_relations.append(relation)
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
        for schedule in new_schedules:
            state.schedule_due[schedule.id] = (
                state.game_time + schedule.delay_minutes * 60
            )
        state.locations = {x.id: x.name for x in d.locations}
        state.items.update(index(new_items))
        for a in new_actors:
            actor = RulesEngine().build_character(a, state.ruleset)
            RulesEngine().equipment_stats(actor, state.items, state.ruleset)
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
