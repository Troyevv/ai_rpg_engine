"""Bounded DM interpretation and public narration; mechanical authority stays in code."""

import json
import time
from datetime import datetime, timezone
from contextlib import nullcontext
import llm
from backend.services.coordinator import LOCAL_MODEL_LOCK
from backend.services.usage import usage_values, cost, price_snapshot
from .models import Command
from .projection import public_state


class DMContextBuilder:
    @staticmethod
    def build(state, events=None, role="narration"):
        from .projection import DMProjection, PublicProjection

        if role == "interpretation":
            return DMProjection.build(state, events)
        p = PublicProjection.build(state)
        return {
            "scene": p["scene"],
            "location": p["location"],
            "mode": p["mode"],
            "characters": p["characters"],
            "visible_npcs": p["npcs"],
            "objects": p["objects"],
            "known": p["knowledge"],
            "quests": p["quests"],
            "encounter": p["encounter"],
            "events": (events or [])[-20:],
        }


class DMAgent:
    def __init__(self, repo, config=None, api_key=None):
        self.repo, self.config, self.api_key = repo, config, api_key

    def call(self, gid, stage, messages, structured=False):
        config = self.config
        usage = None

        def received(value):
            nonlocal usage
            usage = value

        started = time.perf_counter()
        status = "error"
        pricing = price_snapshot(config, datetime.now(timezone.utc))
        try:
            # Serialize use with the existing local-model coordinator.
            with LOCAL_MODEL_LOCK if config["provider"] == "local" else nullcontext():
                output = "".join(
                    llm.chat_stream(
                        model=config["model"],
                        messages=messages,
                        provider=config["provider"],
                        api_key=self.api_key,
                        thinking=config.get("thinking", "off"),
                        temperature=config.get("temperature", 0.7),
                        max_tokens=(
                            max(config.get("max_tokens", 2000), 10000)
                            if stage in ("campaign_generation", "content_generation")
                            else min(config.get("max_tokens", 2000), 4000)
                        ),
                        response_format={"type": "json_object"} if structured else None,
                        require_complete=True,
                        on_usage=received,
                    )
                )
            status = "complete"
            return output
        finally:
            inp, out, cached = usage_values(usage)
            self.repo.request_log(
                gid,
                stage,
                {
                    "status": status,
                    "provider": config["provider"],
                    "model": config["model"],
                    "input_tokens": inp,
                    "output_tokens": out,
                    "cached_tokens": cached,
                    "cost": cost(inp, out, cached, pricing),
                    "pricing": pricing,
                    "seconds": round(time.perf_counter() - started, 3),
                },
            )

    def interpret(self, gid, state, text):
        if not self.config:
            raise ValueError(
                "Свободный ввод требует LLM DM. Без модели используй игровые кнопки."
            )
        prompt = (
            "Ты DM настольной RPG. Верни только одну JSON команду по схеме. "
            "Используй семантическую difficulty, никогда dc или результат броска. "
            "Для поиска: check purpose=search без target. Для убеждения: check purpose=persuade target=NPC. "
            "dialogue — обычный разговор. Move target=ID известной локации; distance только для боя. "
            "Если игрок хочет пойти в ещё не созданное место: expand topic=описание места. "
            "Не выдавай скрытые ID/секреты в topic и не назначай последствия за пределами схемы. "
            "Для неожиданного действия: check с ability/skill и семантической difficulty; исход не даёт произвольных изменений. "
            "Схема: " + json.dumps(Command.model_json_schema(), ensure_ascii=False)
        )
        raw = self.call(
            gid,
            "interpretation",
            [
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "context": DMContextBuilder.build(
                                state, role="interpretation"
                            ),
                            "action": text,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            True,
        )
        try:
            return Command.model_validate_json(raw)
        except ValueError:
            raise ValueError(
                "DM вернул недопустимую команду. Состояние не изменено."
            ) from None

    def narrate(self, gid, state, events, text=""):
        if not self.config:
            return "\n\n".join(e["text"] for e in events if "roll" not in e)
        dialogue = any(e.get("kind") == "dialogue" for e in events)
        context = DMContextBuilder.build(state, events)
        if dialogue and state.session_state.dialogue_actor:
            npc = state.actor(state.session_state.dialogue_actor)
            # Portrayal has public traits, public lore and only engine-authorized disclosures.
            # Interpretation knows relevant secrets; the player-facing speaker does not.
            context["speaker"] = {
                "name": npc.name,
                "personality": npc.personality,
                "attitude": npc.attitude,
                "public_lore": npc.public_lore,
                "disclosed": [
                    state.player_knowledge[i]
                    for i in npc.knowledge
                    if i in state.player_knowledge
                ],
            }
        return self.call(
            gid,
            "npc_dialogue" if dialogue else "narration",
            [
                {
                    "role": "system",
                    "content": "Ты DM настольной RPG. Пиши по-русски. Опиши только подтверждённые механические события. "
                    "Для dialogue отвечай от лица указанного NPC, учитывая характер и отношение. "
                    "Не выдумывай секреты, победы, предметы, успешные проверки или изменения HP. "
                    "Если нужен бросок, попроси его выполнить. Решения игрока не дописывай. В конце можно предложить 2 коротких действия.",
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"context": context, "player_text": text}, ensure_ascii=False
                    ),
                },
            ],
        )
