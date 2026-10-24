"""Request budgets for authoring; estimates never masquerade as tokenizer usage."""
import json
from copy import deepcopy
from context_builder import estimate
from backend.services.world_authoring_compiler import CompileError

MARGIN = 512
# Published model capabilities, checked 2026-10-24:
# https://api-docs.deepseek.com/api/list-models/
DEEPSEEK_LIMITS = {name: (1048576, 393216) for name in (
    'deepseek-flash', 'deepseek-v4-flash', 'deepseek-v4-flash-vision-exp', 'deepseek-v4-pro')}


def limits(config, loaded=None):
    model_context, model_output = DEEPSEEK_LIMITS.get(config.get('model'), (None, None)) if config.get('provider') == 'deepseek' else (None, None)
    if config.get('provider') == 'local' and loaded:
        model_context = loaded.get('config', {}).get('context_length') or model_context
    context = min(config['context_length'], int(model_context or config['context_length']))
    output = min(config['max_tokens'], int(model_output or config['max_tokens']))
    return context, output, model_context


def schema_for(stage, schema, data):
    """Only assigned sections and reachable definitions; validation stays canonical."""
    result = deepcopy(schema)
    definitions = result.get('$defs', {})
    if 'Opening' in definitions and 'Time' in definitions:
        # History supports vague/relative time; the executable opening does not.
        opening_time = deepcopy(definitions['Time'])
        props = opening_time['properties']
        props['clock'] = {'type': 'string', 'pattern': r'^([01]\d|2[0-3]):[0-5]\d$'}
        props['date'] = {'anyOf': [{'type': 'string', 'pattern': r'^\d{4}-\d{2}-\d{2}$'}, {'type': 'null'}], 'default': None}
        for field in ('period', 'day_offset'):
            props[field] = {'type': 'null', 'default': None}
        props['weekday']['description'] = 'Zero-based calendar index. Gregorian: Monday=0, Tuesday=1, Wednesday=2, Thursday=3, Friday=4, Saturday=5, Sunday=6.'
        opening_time['required'] = ['clock']
        opening_time['anyOf'] = [
            {'required': ['date'], 'properties': {'date': {'type': 'string'}}},
            {'required': ['weekday'], 'properties': {'weekday': {'type': 'integer'}}},
        ]
        definitions['OpeningTime'] = opening_time
        definitions['Opening']['properties']['time'] = {'$ref': '#/$defs/OpeningTime'}
        if stage in ('author_plan_page', 'author_plan'):
            definitions.pop('Time')  # planning has no historical-time records
    if stage == 'author_plan_page':
        result['properties'].pop('continuation', None)
        result.get('$defs', {}).pop('PlanContinuation', None)
        # Match the provider-visible contract to this exact scheduled page.
        result['properties']['records']['maxItems'] = min(32, data.get('max_records', 32))
    if stage == 'author_batch':
        sections = {r['section'] for r in data['assigned_records']}
        result['properties'] = {k:v for k,v in result['properties'].items() if k in sections}
        result['required'] = sorted(sections)
        needed = set()
        def refs(value):
            if isinstance(value, dict):
                if '$ref' in value:
                    name = value['$ref'].rsplit('/', 1)[-1]
                    if name not in needed:
                        needed.add(name); refs(result['$defs'][name])
                for k,v in value.items():
                    if k != '$defs': refs(v)
            elif isinstance(value, list):
                for v in value: refs(v)
        refs(result['properties'])
        result['$defs'] = {k:v for k,v in result.get('$defs', {}).items() if k in needed}
    return result


def messages(prompt, stage, data):
    rules = prompt['interpretation'] if stage == 'author_brief' else prompt['rules']
    schema = schema_for(stage, prompt['schemas'][stage], data)
    system = rules + '\nJSON Schema:\n' + json.dumps(schema, ensure_ascii=False, separators=(',', ':')) + '\n\nStage: ' + stage
    return [dict(role='system', content=system), dict(role='user', content=json.dumps(data, ensure_ascii=False))]


def response_budget(stage, data, ceiling, context):
    # A ceiling is not a reservation. Small extraction tasks do not reserve a
    # world's entire output allowance. Large source sections are split upstream.
    if stage == 'author_brief':
        wanted = max(1024, 512 + 2 * estimate([dict(content=data.get('source', ''))]))
    elif stage == 'author_plan_page':
        wanted = 1200 + 400 * data.get('max_records', 1)
    elif stage == 'author_document':
        wanted = data.get('response_budget', ceiling)
    elif stage == 'author_batch':
        wanted = 512 + sum(1800 if r['section']=='characters' else 650 for r in data['assigned_records'])
    else:
        wanted = ceiling
    return min(ceiling, wanted, max(256, context // 3)) if stage == 'author_brief' else min(ceiling, wanted)


def check(messages, output, context, stage, *, user_context=None, model_context=None):
    incoming = estimate(messages)
    required = incoming + output + MARGIN
    if required > context:
        raise CompileError('author/request/' + stage,
            f'Недостаточно контекста: требуется ≈{required} токенов '
            f'(вход со схемой ≈{incoming}, ответ {output}, запас {MARGIN}); доступно {context}. '
            f'Настройка пользователя: {user_context or context}; окно модели: {model_context or "неизвестно"}. '
            'Вход оценён по UTF-8, не токенизатором провайдера.',
            'Уменьшите размер задания или измените бюджет в пределах окна модели; запрос не отправлен.')
    return dict(estimated_tokens=incoming, output_budget=output, margin=MARGIN,
                effective_context=context, user_context=user_context or context,
                model_context=model_context, token_method='conservative UTF-8 estimate', parts=[])
