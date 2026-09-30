"""Expansion crosses typed authoring validation before runtime persistence."""

from ..generation import ContentGenerator


class ContentService:
    def __init__(self, runtime):
        self.runtime = runtime

    def execute(self, gid, state, command, dm):
        if state.encounter or not state.session_state.mechanical_resolution_complete:
            raise ValueError(
                "Новый контент создаётся вне боя после завершения ожидающих действий"
            )
        self.runtime.owned(
            state, command.actor_id or state.session_state.controlled_actor
        )
        try:
            after, mutation = ContentGenerator(dm).generate(gid, state, command.topic)
        except ValueError:
            raise
        except Exception:
            raise ValueError(
                "Расширение мира недоступно. Состояние не изменено."
            ) from None
        return after, [
            {
                "text": "Добавлен новый контент. Доступные переходы обновлены.",
                "kind": "content",
                "operations": [op.type for op in mutation.operations],
            }
        ]
