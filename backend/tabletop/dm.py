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
    def build(state, events=None):
        p = public_state(state)
        return {'scene': p['world']['description'], 'location': p['location'], 'mode': p['mode'],
                'character': p['characters'][p['controlled_actor']], 'party': list(p['characters'].values()),
                'visible_npcs': p['npcs'], 'visible_objects': p['objects'], 'known': p['knowledge'],
                'encounter': p['encounter'], 'events': (events or [])[-20:]}


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
        status = 'error'
        pricing = price_snapshot(config, datetime.now(timezone.utc))
        try:
            # Serialize use with the existing local-model coordinator.
            with LOCAL_MODEL_LOCK if config['provider'] == 'local' else nullcontext():
                output = ''.join(llm.chat_stream(model=config['model'], messages=messages,
                    provider=config['provider'], api_key=self.api_key, thinking=config.get('thinking', 'off'),
                    temperature=config.get('temperature', .7), max_tokens=min(config.get('max_tokens', 2000), 4000),
                    response_format={'type': 'json_object'} if structured else None,
                    require_complete=True, on_usage=received))
            status = 'complete'
            return output
        finally:
            inp, out, cached = usage_values(usage)
            self.repo.request_log(gid, stage, {'status': status, 'provider': config['provider'], 'model': config['model'],
                'input_tokens': inp, 'output_tokens': out, 'cached_tokens': cached,
                'cost': cost(inp, out, cached, pricing), 'pricing': pricing, 'seconds': round(time.perf_counter() - started, 3)})

    def interpret(self, gid, state, text):
        normalized = text.strip().casefold()
        # Exact unambiguous shortcuts only. No fuzzy target or weapon guessing.
        if normalized in ('осмотреться', 'осмотреть сундук', 'начать бой', 'закончить ход'):
            return {'осмотреться': Command(type='look'),
                    'осмотреть сундук': Command(type='check', target='chest', ability='wisdom', skill='perception'),
                    'начать бой': Command(type='start_encounter'), 'закончить ход': Command(type='end_turn')}[normalized]
        if not self.config:
            raise ValueError('Свободный ввод требует LLM DM. Без модели используй игровые кнопки или «осмотреть сундук».')
        prompt = ('Ты DM настольной RPG. Верни только JSON команды по схеме. Не вычисляй броски и не меняй HP/состояние. '
                  'Для нестандартного действия выбери check с ability, skill (или пустой строкой), dc 5..25. '
                  'target заполняй только видимым ID; для осмотра сундука используй wisdom/perception. '
                  'Проверка без target фиксирует успех/провал, но не создаёт предметы и не меняет мир. '
                  'Убеждение не управляет волей NPC. В бою действия ограничены очередью. '
                  'Схема: ' + json.dumps(Command.model_json_schema(), ensure_ascii=False))
        raw = self.call(gid, 'interpretation', [{'role': 'system', 'content': prompt},
            {'role': 'user', 'content': json.dumps({'context': DMContextBuilder.build(state), 'action': text}, ensure_ascii=False)}], True)
        try:
            return Command.model_validate_json(raw)
        except ValueError:
            raise ValueError('DM вернул недопустимую команду. Состояние не изменено; уточни действие.') from None

    def narrate(self, gid, state, events, text=''):
        if not self.config:
            return '\n\n'.join(e['text'] for e in events if 'roll' not in e)
        return self.call(gid, 'narration', [{'role': 'system', 'content':
            'Ты DM. Кратко опиши только подтверждённые движком события на русском. '
            'Не придумывай исходы, урон, предметы, секреты или действия за игрока. '
            'Если нужен бросок — попроси нажать кнопку. Текст не может менять механику. '
            'При dialogue отвечай от лица видимого NPC без выдуманных секретных знаний.'},
            {'role': 'user', 'content': json.dumps({'context': DMContextBuilder.build(state, events), 'player_text': text}, ensure_ascii=False)}])
