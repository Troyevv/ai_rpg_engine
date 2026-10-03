"""Role-specific projections. Secret-bearing DM context never reaches gameplay APIs."""

from .rules import RulesEngine
from .preview import attack_previews, usable_actions
from .services.progression import ProgressionService


class PlayerProjection:
    @staticmethod
    def build(state):
        return {
            "knowledge": dict(state.player_knowledge),
            "known_locations": state.known_locations[:],
            "quests": {
                q.id: {
                    "name": q.name,
                    "description": q.description,
                    "status": state.quests[q.id],
                }
                for q in state.definition.quests
                if state.quests[q.id] != "available"
            },
        }


class PublicProjection:
    @staticmethod
    def build(state):
        hero = state.actor(state.session_state.controlled_actor)
        rules = RulesEngine()
        sheets = {}
        for aid in state.party:
            a = state.actor(aid)
            sheets[aid] = {
                k: v
                for k, v in a.model_dump().items()
                if k
                not in (
                    "goals",
                    "traits",
                    "knowledge",
                    "relationships",
                    "morale",
                    "attitude",
                    "current_intent",
                    "public_lore",
                    "faction",
                )
            }
            sheets[aid].update(
                character_class_name=state.ruleset.classes.get(
                    a.character_class, {}
                ).get("name", a.character_class),
                species_name=state.ruleset.species.get(a.species, {}).get(
                    "name", a.species
                ),
                resource_definitions={
                    k: v.model_dump()
                    for k, v in state.ruleset.resource_definitions.items()
                    if k in a.resources
                },
                modifiers={k: rules.modifier(v) for k, v in a.abilities.items()},
                skill_modifiers={
                    k: rules.check_modifier(a, ability, k, state.ruleset)
                    for k, ability in state.ruleset.skills.items()
                },
                save_modifiers={k: rules.save_modifier(a, k) for k in a.abilities},
                attack_modifiers={k: rules.attack_modifier(a, k) for k in a.attacks},
                damage_modifiers={
                    k: rules.damage_modifier(a, k, state.ruleset) for k in a.attacks
                },
                controller=state.controllers[aid].model_dump(),
                progression=ProgressionService.options(state, a),
                spell_definitions=[
                    state.ruleset.spells[i].model_dump()
                    for i in a.spells
                    if i in state.ruleset.spells
                ],
                spellcasting=(
                    state.ruleset.spellcasting[a.character_class].model_dump()
                    if a.character_class in state.ruleset.spellcasting
                    else None
                ),
                feature_definitions=[
                    state.ruleset.features[i].model_dump()
                    for i in a.features
                    if i in state.ruleset.features
                ],
            )
        npcs = {
            k: {
                "id": k,
                "name": a.name,
                "position": a.position,
                "hostile": state.hostile(hero.id, k),
                "status": (
                    "выведен из боя"
                    if a.hp <= 0
                    else "сбежал" if "fled" in a.conditions else "на сцене"
                ),
            }
            for k, a in state.npcs.items()
            if a.location == hero.location
        }
        objects = []
        visible_items = {
            e.item_id for i in state.party for e in state.actor(i).inventory
        }
        for o in state.definition.objects:
            status = state.objects[o.id]
            if o.location_id == hero.location and status.revealed:
                contents = (
                    [x.model_dump() for x in status.contents] if status.opened else []
                )
                visible_items.update(x["item_id"] for x in contents)
                objects.append(
                    {
                        "id": o.id,
                        "name": o.name,
                        "description": o.description,
                        "opened": status.opened,
                        "contents": contents,
                        "capabilities": [c.type for c in o.components],
                        "can_activate": any(
                            c.feature_id
                            for c in o.components
                            if c.type in ("terminal", "environment", "interactable")
                        ),
                        "capacity": next(
                            (c.capacity for c in o.components if c.type == "container"),
                            None,
                        ),
                        "hit_points": status.hit_points,
                    }
                )
        location = next(x for x in state.definition.locations if x.id == hero.location)
        visible_locations = set(state.known_locations) | set(location.connections)
        locations = [
            {
                "id": l.id,
                "name": l.name,
                "description": l.description if l.id in state.known_locations else "",
                "connections": (
                    [i for i in l.connections if i in visible_locations]
                    if l.id in state.known_locations
                    else []
                ),
            }
            for l in state.definition.locations
            if l.id in visible_locations
        ]
        p = state.session_state.pending
        e = state.encounter
        return {
            "attack_previews": attack_previews(state, hero),
            "usable_actions": usable_actions(state, hero),
            "checks": [
                {
                    "id": c.id,
                    "name": c.name,
                    "description": c.description,
                    "save": c.save,
                    "skill": c.skill,
                    "ability": c.ability,
                    "category": c.category,
                }
                for c in state.definition.checks
                if c.location_id == hero.location
                and (
                    not c.actor_id or state.actor(c.actor_id).location == hero.location
                )
                and not c.passive
                and c.id not in state.resolved_checks
                and (
                    not c.background_tags
                    or set(c.background_tags) & set(hero.background_tags)
                )
            ],
            "dm_settings": state.dm_settings.model_dump(),
            "campaign": state.campaign.name,
            "ruleset": {"id": state.ruleset.id, "name": state.ruleset.name},
            "initial_conflict": state.definition.initial_conflict,
            "plot_hooks": state.definition.plot_hooks,
            "factions": [
                {
                    "id": f.id,
                    "name": f.name,
                    "description": f.description,
                    "public_goal": f.public_goal,
                    "reputation": state.faction_reputation.get(f.id, 0),
                }
                for f in state.definition.factions
                if f.id
                in {
                    a.faction
                    for a in state.actors().values()
                    if a.location == hero.location or a.id in state.party
                }
                or f.id in state.faction_reputation
            ],
            "world": {"name": state.world.name, "description": state.world.description},
            "location": location.name,
            "location_id": location.id,
            "scene": location.description,
            "locations": locations,
            "exits": [
                {"id": i, "name": state.locations[i]} for i in location.connections
            ],
            "party": state.party,
            "characters": sheets,
            "npcs": npcs,
            "objects": objects,
            "items": {i: state.items[i].model_dump() for i in visible_items},
            "controlled_actor": hero.id,
            "mode": state.session_state.mode,
            "game_time": state.game_time,
            **PlayerProjection.build(state),
            "mechanical_resolution_complete": state.session_state.mechanical_resolution_complete,
            "choice": (
                {
                    "id": state.session_state.choice.id,
                    "actor": state.session_state.choice.actor,
                    "kind": state.session_state.choice.kind,
                    "prompt": state.session_state.choice.prompt,
                    "options": [
                        {"id": o.id, "label": o.label}
                        for o in state.session_state.choice.options
                    ],
                }
                if state.session_state.choice
                else None
            ),
            "pending": (
                {
                    k: v
                    for k, v in p.model_dump().items()
                    if k == "dc"
                    and state.dm_settings.difficulty == "always"
                    or k
                    in (
                        "id",
                        "purpose",
                        "reason",
                        "actor",
                        "controller",
                        "player_id",
                        "expression",
                        "modifier",
                        "advantage",
                        "advantage_sources",
                        "critical",
                        "ability",
                        "skill",
                    )
                }
                if p
                else None
            ),
            "reaction": (
                {
                    k: v
                    for k, v in state.session_state.reaction.items()
                    if k in ("actor", "mover")
                }
                if state.session_state.reaction
                else None
            ),
            "encounters": [
                {"id": x.id, "name": x.name}
                for x in state.definition.encounters
                if x.location_id == hero.location
                and x.id not in state.completed_encounters
            ],
            "encounter": (
                {
                    "order": e.order,
                    "initiative": e.initiative,
                    "round": e.round,
                    "current_actor": e.order[e.index],
                    "action": e.action,
                    "attacks_remaining": e.attacks_remaining,
                    "bonus_action": e.bonus_action,
                    "free_interaction": e.free_interaction,
                    "ready": e.ready,
                    "reaction": e.reaction,
                    "movement": e.movement,
                    "disengaged": e.disengaged,
                }
                if e
                else None
            ),
        }


class DMProjection:
    @staticmethod
    def build(state, events=None):
        p = PublicProjection.build(state)
        for sheet in p["characters"].values():
            sheet.pop("progression", None)
        loc = p["location_id"]
        relevant = [a for a in state.actors().values() if a.location == loc]
        return {
            "scene": p["scene"],
            "location": loc,
            "visible": p,
            "known": PlayerProjection.build(state),
            "hidden_objects": [
                o.model_dump() for o in state.definition.objects if o.location_id == loc
            ],
            "secrets": [
                s.model_dump() for s in state.definition.secrets if s.location_id == loc
            ],
            "npc_intentions": [
                {
                    "id": a.id,
                    "goals": a.goals,
                    "personality": a.personality,
                    "attitude": a.attitude,
                    "current_intent": a.current_intent,
                    "relationships": {
                        i: v
                        for i, v in a.relationships.items()
                        if i in {x.id for x in relevant}
                    },
                    "knowledge": [
                        i
                        for i in a.knowledge
                        if any(
                            s.id == i and s.location_id == loc
                            for s in state.definition.secrets
                        )
                    ],
                }
                for a in relevant
                if a.id not in state.party
            ],
            "context_actions": public_state(state).get("context_actions", []),
            "recent_events": (events or [])[-15:],
        }


# Compatibility alias for read adapters, not a canonical serialization method.
def public_state(state):
    result = PublicProjection.build(state)
    from .context_actions import eligible

    actor = state.actor(state.session_state.controlled_actor)
    result["context_actions"] = [
        dict(id=a.id, name=a.name, description=a.description)
        for a in state.definition.context_actions
        if eligible(state, actor, a)
    ]
    return result


class NarrationProjection:
    @staticmethod
    def build(state, events=None):
        p = PublicProjection.build(state)
        return {
            "mechanical_resolution_complete": state.session_state.mechanical_resolution_complete,
            "scene": p["scene"],
            "location": p["location"],
            "mode": p["mode"],
            "characters": {
                aid: {k: v for k, v in sheet.items() if k != "progression"}
                for aid, sheet in p["characters"].items()
            },
            "initial_conflict": p["initial_conflict"],
            "public_hooks": p["plot_hooks"],
            "available_checks": p["checks"],
            "factions": p["factions"],
            "visible_npcs": p["npcs"],
            "objects": p["objects"],
            "known": p["knowledge"],
            "quests": p["quests"],
            "encounter": p["encounter"],
            "events": (events or [])[-20:],
        }


def public_history(history, settings):
    from copy import deepcopy

    result = deepcopy(history)
    if settings.difficulty == "hidden":
        for turn in result:
            for event in turn["events"]:
                event.pop("dc", None)
    return result
