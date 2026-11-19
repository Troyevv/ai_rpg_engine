"""Versioned application targets. Context selection and spend accounting stay with their owners."""
import json
from dataclasses import dataclass
from backend.services import model_capabilities as capabilities
from backend.chat import tokenization
from context_builder import estimate
from llm import thinking_options

class BudgetError(ValueError):
    """Request rejected locally, before opening the provider transport."""
    code = "budget_preflight"


VERSION = 1
MARGIN = 256
INPUT_TARGET = 18000


@dataclass(frozen=True)
class Detail:
    visible: int
    headroom: int
    guidance: str


DETAILS = {
    'brief': Detail(450, 450, 'Выбери несколько точных живых деталей, сохрани голос и диалог.'),
    'balanced': Detail(1000, 1000, 'Дай сцене обычный литературный объём, чередуя действие, диалог и наблюдение.'),
    'detailed': Detail(1800, 1300, 'Раскрой восприятие, обстановку и нюансы реплик внутри текущего момента.'),
    'extended': Detail(3000, 1800, 'Разверни значимые ощущения и оттенки взаимодействия без повторов и наполнителя.'),
}


def prose_guidance(detail):
    return ('Подробность повествования. ' + DETAILS[detail].guidance +
            ' Заверши смысловой фрагмент естественно. Можно закончить раньше. '
            'Сохрани темп событий, время, жанр, инициативу NPC и границы канала. '
            'Остановись там, где игроку предстоит решение.')


def prepare(config, operation, *, loaded=None, detail='balanced', api_key=None):
    """Resolve one job's technical working copy; saved manual preferences are never mutated."""
    provider = config.get('provider', 'local')
    mode = config.get('budget_mode')
    if loaded is not None:
        caps = dict(context_length=loaded.get('config', {}).get('context_length'),
                    source='LM Studio: loaded_instances.config.context_length')
    elif provider in ('local','deepseek') or mode:
        caps = capabilities.discover(provider, config['model'], api_key=api_key)
    else:
        caps = {}
    window = caps.get('context_length')
    window = window if type(window) is int and window > 0 else None
    if window is not None and window <= MARGIN + 256:
        raise BudgetError('Окно модели слишком мало для запроса и резерва ответа.')
    if window is None and caps.get('max_input') and caps.get('max_output'):
        # Builder envelope for independent limits. The wire preflight checks each
        # dimension, and the metadata retains the provider's original semantics.
        window = caps['max_input'] + caps['max_output']
    auto = mode == 'auto'
    if auto and not window:
        raise BudgetError('Окно выбранной модели неизвестно. Загрузите локальную модель или укажите проверенные лимиты вручную.')
    if mode == 'manual' and window and config['context_length'] > window:
        raise BudgetError(f'Ручной контекст превышает окно модели ({window}). Уменьшите его или включите автоматический режим.')
    use_window = auto or (mode is None and config.get('auto_context'))
    context = window if use_window and window else min(config['context_length'], window or config['context_length'])
    caps = dict(caps, source=caps.get('source') if window else 'Ручная настройка, не подтверждена провайдером')
    working = dict(config, provider=provider, context_length=context, _budget_caps=caps, _detail=detail)
    recorded = config.get('_recorded_budget') or {}
    detail_policy = DETAILS[detail]
    working['_visible_target'] = recorded.get('visible_target') or detail_policy.visible
    working['_policy_version'] = recorded.get('policy_version', VERSION)
    thinking = thinking_options(provider, config['model'], config.get('thinking'))[0]
    reasoning = {'off':0, 'low':768, 'high':2048}[thinking]
    working['_reasoning_reserve'] = recorded.get('reasoning_reserve', reasoning)
    if auto:
        target = {'idea':6000, 'summary':12000, 'draft_world':32768, 'draft_editor':16000,
                  'draft_field':2048, 'draft_character':6000, 'character_draft':8000, 'npc_card_field':2048}.get(operation)
        output = (target if target is not None else detail_policy.visible + detail_policy.headroom) + reasoning
        working['_output_target'] = output
        working.update(max_tokens=min(output, caps.get('max_output') or output, context - MARGIN),
                       update_tokens=min(6144 + reasoning, caps.get('max_output') or context, context - MARGIN))
    elif mode == 'manual':
        maximum = min(context - MARGIN, caps.get('max_output') or context)
        limits = [config['max_tokens']]
        if operation in ('turn','start','background','pov','long_term','communication'):
            limits.append(config['update_tokens'])
        if max(limits) > maximum:
            raise BudgetError(f'Ручной лимит ответа превышает возможности модели ({maximum}).')
        if operation in ('turn','start','background','pov','long_term'):
            working['max_tokens'] = min(config['max_tokens'], detail_policy.visible + detail_policy.headroom + reasoning)
    # Preserve the old default aggregate envelope independently of the model window.
    if auto and config.get('_draft_task') in ('world', 'editor'):
        from backend.services.draft_response import MAX_FRAGMENTS
        working.setdefault('_draft_token_budget', 3 * MAX_FRAGMENTS * (32768 + 12000))

    pinned = config.get('_budget_snapshot')
    if pinned:
        previous = pinned['_budget_caps']
        smaller = any(caps.get(k) and previous.get(k) and caps[k] < previous[k]
                      for k in ('context_length', 'max_input', 'max_output'))
        if (smaller or previous.get('endpoint_id') != caps.get('endpoint_id')
                or caps.get('max_output') and max(pinned['max_tokens'], pinned['update_tokens']) > caps['max_output']
                or caps.get('max_input') and not previous.get('max_input') and pinned['context_length'] > caps['max_input']):
            raise BudgetError('Возможности модели изменились. Сохранённый план несовместим. Подтвердите новые лимиты для восстановления.')
        working.update(pinned)
    return working


def snapshot(config):
    keys = ('_budget_caps', '_visible_target', '_policy_version', '_reasoning_reserve',
            '_output_target', '_detail', 'context_length', 'max_tokens', 'update_tokens')
    return {key: config[key] for key in keys if key in config}


def world_output(config, messages):
    from backend.services.world_creation_settings import CreationSettings
    targets = CreationSettings.model_validate(config.get('_creation_settings', {})).cast_targets([])
    source = estimate([m for m in messages if m['role'] == 'user'])
    return 2500 + 650 * targets['core'] + 320 * targets['secondary'] + min(source, 12000) + config['_reasoning_reserve']


def extraction_output(config, scene_size):
    if config.get('budget_mode') != 'auto':
        return config.get('update_tokens',4096)
    target = 4096 + min(scene_size, 12000) + config['_reasoning_reserve']
    return min(target, config['_budget_caps'].get('max_output') or target, config['context_length'] - MARGIN)


def plan_request(config, stage, messages, requested, *, response_format=None, structured_schema=None,
                 structured_name='extraction_v6', expected_text=0, temperature=None):
    """Count the effective provider envelope after late blocks and transport selection."""
    from llm import request_payload
    payload = request_payload(config.get('provider','local'), config['model'], messages, requested,
                              temperature, config.get('thinking','off'), response_format, structured_schema, structured_name)
    counted, method = tokenization.count(payload, dict(config, provider=config.get('provider','local')))
    if method == 'Консервативная оценка UTF-8':
        wire_bytes = counted
        # Existing multilingual projection uses two bytes/token plus per-message
        # framing. Count the serialized transport too, including external schemas.
        # The provider decodes JSON string escaping before tokenizing message
        # content. Large JSON continuations can otherwise count quotes twice.
        wire_messages = payload.get('messages', payload.get('input', []))
        escaping = sum(len(json.dumps(m['content'], ensure_ascii=False).encode()) - 2
                       - len(m['content'].encode()) for m in wire_messages)
        counted = (counted - escaping + 1)//2 + 32*len(wire_messages)
        method = 'Оценка UTF-8 / 2 с резервом протокола'
    else:
        # A cost reservation can use the tokenizer count plus protocol margin.
        wire_bytes = counted
    consumed = counted + expected_text
    caps = config.get('_budget_caps', {})
    if caps.get('max_input') and consumed + MARGIN > caps['max_input']:
        raise BudgetError(f"Полный вход запроса {stage} с резервом превышает предел модели ({caps['max_input']}). "
                          "Сократите исходный ввод или выберите модель с большим окном.")
    window = config['context_length']
    ceiling = requested
    if config.get('budget_mode') == 'manual':
        structured = stage in ('extraction','extraction_repair','world_simulation_delta','world_simulation_repair','long_term_extraction','long_term_repair','communication') or stage.startswith('remote_')
        ceiling = config['update_tokens' if structured else 'max_tokens']
    output = min(requested, ceiling, caps.get('max_output') or requested, window - consumed - MARGIN)
    minimum = min(requested, 256)
    if stage in ('extraction', 'extraction_repair', 'world_simulation_delta', 'world_simulation_repair', 'long_term_extraction', 'long_term_repair'):
        minimum = max(requested, 1024) if config.get('budget_mode') == 'auto' else min(requested, 1024)
    elif stage in ('narrative', 'world_simulation', 'long_term_narrative') and config.get('budget_mode') in ('auto', 'manual'):
        minimum = config['_visible_target'] + config['_reasoning_reserve']
        if output < minimum:
            raise BudgetError(f'Выбранная подробность требует места для {minimum} токенов ответа с учётом Thinking. '
                              f'Доступно {output}. Уменьшите подробность или выберите подходящую модель.')
    if output < minimum:
        raise BudgetError(f'Контекст {window} не вмещает запрос {stage}: вход ≈{consumed}, ответ {requested}, резерв {MARGIN}, окно {window}. '
                         'Выберите подходящую модель, увеличьте ручное окно или уменьшите подробность.')
    detail = config.get('_detail','balanced') if stage in ('narrative','world_simulation','long_term_narrative') else None
    reasons = []
    if ceiling < requested: reasons.append('manual_output_limit')
    if output == window-consumed-MARGIN: reasons.append('context_window')
    if caps.get('max_output') == output: reasons.append('provider_output_limit')
    if detail and config.get('_output_target',0) > requested: reasons.append('stage_limit')
    return dict(policy_version=config.get('_policy_version', VERSION), stage=stage, budget_mode=config.get('budget_mode') or 'manual',
                capabilities=caps, context_window=window, estimated_input=consumed, estimate_method=method,
                reservation_input=wire_bytes + expected_text + MARGIN,
                input_target=min(INPUT_TARGET,window-output-MARGIN), requested_output=requested, output_allowance=output,
                safety_margin=MARGIN, requested_detail=detail, effective_detail=detail,
                visible_target=config.get('_visible_target', DETAILS[detail].visible) if detail else None,
                reasoning_reserve=config.get('_reasoning_reserve',0) if config.get('thinking') in ('low','high') else 0,
                reasons=reasons or ['stage_target'])


def preflight_downstream(config, build_projection, stage='extraction'):
    """Check the ordinary Extraction projection with room for expected visible prose."""
    if not config.get('budget_mode'):
        return
    visible = min(config['_visible_target'], config['max_tokens'])
    reserve = extraction_output(config, visible)
    messages = build_projection(reserve)
    from backend.services.structured_extraction import request_schema
    version = config.get('_extraction_contract', 1)
    structured = version >= 6 and config.get('_extraction_transport') == 'responses_json_schema'
    plan_request(config, stage, messages, reserve, expected_text=visible, temperature=.1,
                 structured_schema=request_schema(messages) if structured else None,
                 structured_name=f'extraction_v{version}' if version >= 9 else 'extraction_v6',
                 response_format={'type':'json_object'})
