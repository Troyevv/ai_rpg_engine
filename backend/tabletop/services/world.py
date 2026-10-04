"""Authored NPC schedules and reputation advance from canonical time/outcomes."""

from ..encounter import event


class WorldService:
    @staticmethod
    def advance(state, events):
        if state.encounter or not state.session_state.mechanical_resolution_complete:
            return
        hero = state.actor(state.session_state.controlled_actor)
        for schedule in state.definition.schedules:
            if (
                schedule.id in state.completed_schedules
                or state.game_time
                < state.schedule_due.get(schedule.id, schedule.delay_minutes * 60)
            ):
                continue
            if (
                schedule.after_quest
                and state.quests[schedule.after_quest] != "completed"
            ):
                continue
            actor = state.actor(schedule.actor_id)
            if any(
                actor.id in e.participants and e.id not in state.completed_encounters
                for e in state.definition.encounters
            ):
                continue
            if (
                state.controllers[actor.id].controller != "AI"
                or actor.id in state.party
            ):
                raise ValueError("Расписание не может управлять игроком или партией")
            state.completed_schedules.append(schedule.id)
            if actor.hp <= 0 or "dead" in actor.conditions:
                continue
            source = actor.location
            actor.location = schedule.destination_id
            actor.position = 0
            if (
                state.session_state.dialogue_actor == actor.id
                and actor.location != hero.location
            ):
                state.session_state.dialogue_actor = None
                state.session_state.mode = "EXPLORATION"
            state.world_events.append(
                {
                    "schedule": schedule.id,
                    "actor": actor.id,
                    "from": source,
                    "to": actor.location,
                    "time": state.game_time,
                }
            )
            state.world_events = state.world_events[-100:]
            if hero.location in (source, actor.location):
                text = actor.name + (
                    " появляется в этой локации."
                    if hero.location == actor.location
                    else " покидает локацию."
                )
                event(events, text, kind="world_movement", actor=actor.id)
        for quest in state.definition.quests:
            if (
                state.quests[quest.id] != "completed"
                or quest.id in state.reputation_rewards
                or not quest.giver_id
            ):
                continue
            state.reputation_rewards.append(quest.id)
            faction = state.actor(quest.giver_id).faction
            if faction is None:
                continue
            state.faction_reputation[faction] = min(
                10, state.faction_reputation.get(faction, 0) + 1
            )
            name = next(f.name for f in state.definition.factions if f.id == faction)
            event(
                events,
                "Репутация выросла: " + name,
                kind="reputation",
                faction=faction,
                value=state.faction_reputation[faction],
            )
