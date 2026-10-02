"""Bounded DM interpretation and public narration; mechanical authority stays in code."""

import json
import time
from datetime import datetime, timezone
from contextlib import nullcontext
import llm
from backend.services.coordinator import LOCAL_MODEL_LOCK
from backend.services.usage import usage_values, cost, price_snapshot
from .models import Command
from .settings import preferences_prompt
from .narration import contains_mechanical_instruction, safe_narration


class DMContextBuilder:
    @staticmethod
    def build(state, events=None, role="narration"):
        from .projection import DMProjection, NarrationProjection

        if role == "interpretation":
            return DMProjection.build(state, events)
        return NarrationProjection.build(state, events)


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
                            or stage.startswith("authoring_")
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
                "Для игры настрой AI-ведущего: выбери провайдера и модель."
            )
        prompt = (
            "Ты DM настольной RPG. Верни только одну JSON команду по схеме. "
            "Для доступных available_checks выбери check/save с check_id: только движок применяет их последствия. "
            "Без неопределённости и значимых последствий используй look/dialogue/interact, без броска. "
            "Используй семантическую difficulty, никогда dc или результат броска. "
            "Для поиска: check purpose=search без target. Для убеждения: check purpose=persuade target=NPC. "
            "Магия: cast_spell с известным spell_id, target и необязательным slot_level. Ячейки и броски определяет движок. "
            "Способности применяй через use_feature с feature_id из листа; не придумывай эффекты. "
            "grapple/shove/hide/ready/search/use_object — явные механические действия. "
            "dialogue — обычный разговор. Move target=ID известной локации; distance только для боя. "
            "Если игрок хочет пойти в ещё не созданное место: expand topic=описание места. "
            "Не выдавай скрытые ID/секреты в topic и не назначай последствия за пределами схемы. "
            "Для неожиданного действия: check с ability/skill и семантической difficulty; исход не даёт произвольных изменений. "
            "Любая проверка или спасбросок — только check/save request с reason; не обещай бросок текстом. "
            "Если нужно уточнение цели или действия, верни request_choice с 2–6 публичными вариантами и typed commands. "
            "Не раскрывай секреты в reason/prompt/label. Не выбирай за игрока. "
            "Схема: " + json.dumps(Command.model_json_schema(), ensure_ascii=False)
        )
        raw = self.call(
            gid,
            "interpretation",
            [
                {
                    "role": "system",
                    "content": prompt + preferences_prompt(state.dm_settings),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "context": DMContextBuilder.build(
                                state, self.recent_events(gid), role="interpretation"
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

    def recent_events(self, gid):
        return [
            event for turn in self.repo.history(gid)[-6:] for event in turn["events"]
        ][-20:]

    def narrate(self, gid, state, events, text=""):
        # No result-generation call while any mechanical resolution remains pending.
        if not state.session_state.mechanical_resolution_complete:
            return ""
        if not self.config:
            return "\n\n".join(e["text"] for e in events if "roll" not in e)
        dialogue = any(e.get("kind") == "dialogue" for e in events)
        context = DMContextBuilder.build(state, events)
        context["recent_events"] = self.recent_events(gid)
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
        narrative = self.call(
            gid,
            "npc_dialogue" if dialogue else "narration",
            [
                {
                    "role": "system",
                    "content": "Ты DM настольной RPG. Пиши по-русски. Опиши только подтверждённые механические события. "
                    "Для dialogue отвечай от лица указанного NPC, учитывая характер и отношение. "
                    "Не выдумывай секреты, победы, предметы, успешные проверки или изменения HP. "
                    "Механическое разрешение уже завершено. Никогда не требуй новых бросков или проверок. "
                    "Запрещено: брось d20, сделай saving throw, потеряй HP, получи предмет, потрать spell slot, "
                    "брось initiative, нанеси damage, добавь modifier/condition, DC 15, выбери действие 1/2, нажми кнопку. "
                    "Всю механику показывает UI. Ты описываешь мир и реакцию NPC, без численных HP/урона/бонусов. "
                    "Учитывай biography/personality/ideals/bonds/flaws героя без механических бонусов. "
                    "Решения, мысли и чувства игрока не дописывай."
                    + preferences_prompt(state.dm_settings),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"context": context, "player_text": text}, ensure_ascii=False
                    ),
                },
            ],
        )

        if contains_mechanical_instruction(narrative):
            self.repo.request_log(
                gid,
                "narration_guard",
                {
                    "status": "rejected",
                    "provider": self.config["provider"],
                    "model": self.config["model"],
                    "seconds": 0,
                    "input_tokens": None,
                    "output_tokens": None,
                    "cached_tokens": None,
                    "cost": None,
                    "reason": "mechanical_instruction_in_prose",
                },
            )
        return safe_narration(narrative)
