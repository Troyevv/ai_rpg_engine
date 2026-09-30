"""DialogueService domain behavior."""

from uuid import uuid4
from ..encounter import event


class DialogueService:
    def __init__(self, runtime):
        self.runtime = runtime

    def execute(self, state, c, aid, events):
        a = state.actor(aid)
        e = state.encounter
        t = c.type
        if t == "dialogue":
            npc = state.actor(c.target)
            if npc.id == a.id or npc.location != a.location or npc.hp <= 0:
                raise ValueError("Собеседник недоступен")
            if e and state.hostile(a.id, npc.id):
                raise ValueError("Противник сейчас ведёт бой")
            state.session_state.dialogue_actor = npc.id
            if not e:
                state.session_state.mode = "DIALOGUE"
            event(
                events,
                f"{a.name} обращается к {npc.name}.",
                kind="dialogue",
                speaker=npc.id,
            )
            for lore in npc.public_lore:
                if lore not in state.player_knowledge.values():
                    state.player_knowledge["lore_" + uuid4().hex] = lore
                    event(events, lore, kind="discovery")
            for q in state.definition.quests:
                if q.giver_id == npc.id:
                    if state.quests[q.id] == "available":
                        state.quests[q.id] = "active"
                        event(events, "Получено задание: " + q.name, kind="quest")
                    elif (
                        state.quests[q.id] == "active"
                        and q.required_item
                        and self.runtime.entry(a, q.required_item)
                    ):
                        self.runtime.remove(a.inventory, q.required_item, 1)
                        state.quests[q.id] = "completed"
                        for reward in q.reward:
                            self.runtime.add(
                                a.inventory, reward.item_id, reward.quantity
                            )
                        event(
                            events,
                            "Задание выполнено: " + q.name,
                            kind="quest_complete",
                        )
            state.game_time += 60
