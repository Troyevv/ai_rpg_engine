"""CharacterService domain behavior."""

from ..encounter import event


class CharacterService:
    def __init__(self, runtime):
        self.runtime = runtime

    def execute(self, state, c, aid, events):
        a = state.actor(aid)
        e = state.encounter
        t = c.type
        if t == "select_actor":
            self.runtime.owned(state, c.target)
            state.session_state.controlled_actor = c.target
            event(events, "Выбран персонаж: " + state.actor(c.target).name)
            return
