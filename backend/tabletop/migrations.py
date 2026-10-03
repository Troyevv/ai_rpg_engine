"""Deterministic v1→v2 snapshots; current migration never reads history."""

from copy import deepcopy
from hashlib import sha256
from .models import (
    GameState,
    CharacterSheet,
    ActorControl,
    SessionState,
    Encounter,
    PendingRoll,
    ObjectState,
)
from .definitions import (
    CampaignDefinition,
    Setting,
    Region,
    Location,
    Faction,
    FactionRelation,
    CharacterDefinition,
    CharacterBuild,
    ItemDefinition,
    WorldObject,
    Secret,
    Quest,
    EncounterDefinition,
    InventoryEntry,
)
from .compiler import CampaignCompiler
from .catalog import load_ruleset


def migrate(payload):
    if payload.get("schema_version") == 2:
        return GameState.model_validate(payload)
    if payload.get("schema_version") != 1:
        raise ValueError("Неподдерживаемая версия tabletop сохранения")
    old = deepcopy(payload)
    actors = {**old["characters"], **old["npcs"]}
    party = old["party"]
    controlled = old["session_state"]["controlled_actor"]
    factions = list(dict.fromkeys(a["faction"] for a in actors.values()))
    items = {}
    definitions = []
    inventories = {}
    for aid, a in actors.items():
        inventory = []
        for name in a.get("inventory", []):
            iid = "legacy_item_" + sha256(name.encode()).hexdigest()[:12]
            if iid not in items:
                items[iid] = ItemDefinition(id=iid, name=name)
            inventory.append(InventoryEntry(item_id=iid))
        for weapon, w in a.get("attacks", {}).items():
            iid = "legacy_weapon_" + sha256((aid + weapon).encode()).hexdigest()[:12]
            items[iid] = ItemDefinition(
                id=iid,
                name=w["name"],
                type="weapon",
                weapon_die=w["die"],
                weapon_ability=w["ability"],
                reach=w["reach"],
            )
            inventory.append(InventoryEntry(item_id=iid, equipped=True))
        inventories[aid] = inventory
        definitions.append(
            CharacterDefinition(
                id=aid,
                name=a["name"],
                location_id=a["location"],
                faction_id=a["faction"],
                controller="PLAYER" if aid == controlled else "AI",
                player_id="local" if aid == controlled else None,
                build=CharacterBuild(name=a["name"]),
                morale=a.get("morale", 0.5),
                position=a.get("position", 0),
            )
        )
    objects = []
    secrets = []
    for oid, o in old.get("dm_state", {}).get("objects", {}).items():
        sid = o.get("knowledge_key", "legacy_secret_" + oid)
        secrets.append(
            Secret(
                id=sid,
                name="Сведения",
                description=o.get("secret", ""),
                location_id=o["location"],
            )
        )
        objects.append(
            WorldObject(
                id=oid,
                name=o["name"],
                location_id=o["location"],
                dc=o.get("dc", 12),
                secrets=[sid],
            )
        )
    locs = list(old["locations"])
    quests = [
        Quest(id=i, name=text, location_id=locs[0])
        for i, text in old.get("quests", {}).items()
    ]
    encounters = []
    for eid, e in old.get("encounters", {}).items():
        encounters.append(
            EncounterDefinition(
                id="legacy_enc_" + eid,
                name="Сохранённое столкновение",
                location_id=actors[e["order"][0]]["location"],
                participants=e["order"],
            )
        )
    if not encounters and old["npcs"]:
        encounters = [
            EncounterDefinition(
                id="legacy_encounter",
                name="Столкновение",
                location_id=actors[controlled]["location"],
                participants=[
                    i
                    for i in actors
                    if actors[i]["location"] == actors[controlled]["location"]
                ],
            )
        ]
    d = CampaignDefinition(
        id="legacy_campaign",
        name=old["campaign"]["name"],
        setting=Setting(**old["world"]),
        regions=[Region(id="legacy_region", name=old["world"]["name"])],
        locations=[
            Location(
                id=i,
                name=old["locations"][i],
                region_id="legacy_region",
                connections=[j for j in locs if j != i],
            )
            for i in locs
        ],
        factions=[Faction(id=i, name=i) for i in factions],
        faction_relations=[
            FactionRelation(first=a, second=b, relation="HOSTILE")
            for n, a in enumerate(factions)
            for b in factions[n + 1 :]
        ],
        characters=definitions,
        items=list(items.values()),
        objects=objects,
        secrets=secrets,
        quests=quests,
        encounters=encounters,
        starting_party=party,
        starting_location=actors[controlled]["location"],
        starting_scene=old["world"]["description"] or "Продолжение сохранённой игры.",
    )
    # Legacy actors may have split positions. Preserve their exact current state;
    # the definition records the initial roster independently.
    for a in d.characters:
        if a.id in party:
            a.location_id = d.starting_location
    state = CampaignCompiler().compile(d)
    for aid, a in actors.items():
        a["inventory"] = [e.model_dump() for e in inventories[aid]]
        a["proficiency_bonus"] = 2 + (a.get("level", 1) - 1) // 4
        state_actor = CharacterSheet.model_validate(a)
        # Old weapon IDs still name pending attack/damage rolls; keep them intact.
        (state.characters if aid in party else state.npcs)[aid] = state_actor
    state.player_knowledge = old.get("player_knowledge", {})
    state.game_time = old.get("game_time", 0)
    session = old["session_state"]
    pending = session.get("pending")
    if pending:
        pending.update(controller="PLAYER", player_id="local")
        if pending["purpose"] == "initiative":
            chosen = next(e for e in encounters if pending["actor"] in e.participants)
            session["initiative_waiting"] = [
                i for i in chosen.participants if i != pending["actor"]
            ]
            session["encounter_definition"] = chosen.id
        elif pending["purpose"] == "check" and pending.get("target") in {
            o.id for o in objects
        }:
            pending["outcome"] = "search"
    state.session_state = SessionState(**session)
    for oid in state.objects:
        if any(
            i in state.player_knowledge
            for i in next(o for o in d.objects if o.id == oid).secrets
        ):
            state.objects[oid].revealed = True
    for eid, e in old.get("encounters", {}).items():
        e["definition_id"] = "legacy_enc_" + eid
        if isinstance(e.get("reaction"), bool):
            e["reaction"] = {
                i: e["reaction"] if i == e["order"][e["index"]] else True
                for i in e["order"]
            }
        state.encounters[eid] = Encounter.model_validate(e)
    state.active_encounter = old.get("active_encounter")
    return GameState.model_validate(state.model_dump())
