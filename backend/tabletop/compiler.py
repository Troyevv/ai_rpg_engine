"""Validate all references before a campaign can become canonical state."""

from .definitions import CampaignDefinition, CampaignMutation
from .catalog import load_ruleset
from .models import GameState, Campaign, ActorControl, SessionState, ObjectState
from .rules import RulesEngine


def index(values):
    out = {v.id: v for v in values}
    if len(out) != len(values):
        raise ValueError("Повтор ID в определении кампании")
    return out


class CampaignCompiler:
    def validate(self, definition):
        d = CampaignDefinition.model_validate(
            definition.model_dump()
            if isinstance(definition, CampaignDefinition)
            else definition
        )
        rules = load_ruleset(d.ruleset_id)
        if d.ruleset_version != rules.version:
            raise ValueError("Несовместимая версия ruleset")
        regions = index(d.regions)
        locations = index(d.locations)
        factions = index(d.factions)
        actors = index(d.characters + d.creatures)
        items = index(rules.items + d.items)
        objects = index(d.objects)
        quests = index(d.quests)
        secrets = index(d.secrets)
        encounters = index(d.encounters)
        all_ids = [
            i
            for values in (
                regions,
                locations,
                factions,
                actors,
                items,
                objects,
                quests,
                secrets,
                encounters,
            )
            for i in values
        ]
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("ID должны быть уникальны между типами сущностей")

        def require(ok, message):
            if not ok:
                raise ValueError(message)

        require(d.starting_location in locations, "Неизвестная стартовая локация")
        require(
            len(set(d.starting_party)) == len(d.starting_party)
            and set(d.starting_party) <= set(actors),
            "Некорректная стартовая партия",
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
                all(e.item_id in items for e in entries),
                "Инвентарь ссылается на неизвестный предмет",
            )
            require(
                all(
                    not e.equipped or items[e.item_id].type in ("weapon", "armor")
                    for e in entries
                ),
                "Нельзя экипировать этот предмет",
            )

        for loc in locations.values():
            require(
                loc.region_id in regions and set(loc.connections) <= set(locations),
                "Некорректные ссылки локации",
            )
        visited = set()
        todo = [d.starting_location]
        while todo:
            loc = todo.pop()
            if loc not in visited:
                visited.add(loc)
                todo.extend(locations[loc].connections)
        require(
            visited == set(locations), "Все локации должны быть достижимы из стартовой"
        )
        pairs = set()
        for relation in d.faction_relations:
            pair = tuple(sorted((relation.first, relation.second)))
            require(
                relation.first in factions
                and relation.second in factions
                and relation.first != relation.second
                and pair not in pairs,
                "Некорректное отношение фракций",
            )
            pairs.add(pair)
        for a in actors.values():
            require(
                a.location_id in locations and a.faction_id in factions,
                "Неизвестная локация или фракция персонажа",
            )
            require(
                set(a.knowledge) <= set(secrets)
                and set(a.relationships) <= set(actors),
                "Неизвестные знания или отношения персонажа",
            )
            require(
                a.controller == "PLAYER" or a.player_id is None,
                "AI/DM не может владеть player_id",
            )
            RulesEngine().validate_build(a.build, rules)
            inventory(a.inventory)
        require(
            all(actors[i].location_id == d.starting_location for i in d.starting_party),
            "Партия должна начинать в одной локации",
        )
        for secret in secrets.values():
            require(secret.location_id in locations, "Неизвестная локация секрета")
        for obj in objects.values():
            require(
                obj.location_id in locations and set(obj.secrets) <= set(secrets),
                "Некорректные ссылки объекта",
            )
            require(
                all(secrets[i].location_id == obj.location_id for i in obj.secrets),
                "Секрет объекта должен принадлежать его локации",
            )
            require(
                not obj.check_skill
                or rules.skills.get(obj.check_skill) == obj.check_ability,
                "Неверный навык проверки объекта",
            )
            inventory(obj.contents)
        for q in quests.values():
            require(
                q.location_id in locations
                and (q.giver_id is None or q.giver_id in actors)
                and (q.required_item is None or q.required_item in items),
                "Некорректные ссылки задания",
            )
            inventory(q.reward)
        for e in encounters.values():
            require(
                e.location_id in locations
                and len(set(e.participants)) == len(e.participants)
                and set(e.participants) <= set(actors),
                "Некорректные участники столкновения",
            )
            require(
                all(actors[i].location_id == e.location_id for i in e.participants),
                "Участники столкновения должны находиться на его локации",
            )
            require(
                e.loot_object is None
                or e.loot_object in objects
                and objects[e.loot_object].location_id == e.location_id,
                "Некорректная добыча",
            )
            require(
                e.quest_id is None or e.quest_id in quests,
                "Неизвестное задание столкновения",
            )
        for item in items.values():
            require(
                not item.healing or item.type == "consumable",
                "Лечение разрешено только расходуемым предметам",
            )
        return d

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
