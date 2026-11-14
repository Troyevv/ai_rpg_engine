"""Explicit transport capability and lossless wire schema projection."""
from copy import deepcopy
import json

STAGES=frozenset(('extraction','extraction_repair','world_simulation_delta','world_simulation_repair','long_term_extraction','long_term_repair'))
RESPONSES_MODELS=frozenset(('deepseek-flash','deepseek-v4-pro'))


def transport(config):
    return 'responses_json_schema' if config.get('provider')=='deepseek' and config.get('model') in RESPONSES_MODELS else 'chat_json_object'


def wire_schema(schema):
    """Anchors -> standard local pointers, discriminators -> disjoint oneOf.

    Required/nullable/additionalProperties and all validation constraints remain
    intact. Unknown unsupported provider features fail at dispatch, no downgrade.
    """
    anchors={}
    def collect(value,path=''):
        if isinstance(value,dict):
            if '$anchor' in value:anchors['#'+value['$anchor']]='#'+path
            for k,v in value.items():collect(v,path+'/'+k.replace('~','~0').replace('/','~1'))
        elif isinstance(value,list):
            for i,v in enumerate(value):collect(v,path+'/'+str(i))
    collect(schema)
    def project(value):
        if isinstance(value,dict):
            return {k:(anchors.get(v,v) if k=='$ref' else project(v)) for k,v in value.items()
                    if k not in ('$anchor','discriminator')}
        if isinstance(value,list):return [project(v) for v in value]
        return value
    return project(deepcopy(schema))


def request_schema(messages):
    schemas=[json.loads(m['content'].split('\n',1)[1]) for m in messages if isinstance(m.get('content'),str) and m['content'].startswith('JSON Schema\n')]
    if len(schemas)!=1:raise ValueError('Extraction требует одну фактическую JSON Schema.')
    return wire_schema(schemas[0])


def response_events(stream, cancel_event, on_usage, on_finish):
    """Parse Responses SSE; terminal status and a single text output required."""
    complete=False;chunks=[];seen=set()
    for event in stream:
        if cancel_event is not None and cancel_event.is_set():raise RuntimeError('Генерация остановлена.')
        if complete:raise RuntimeError('Данные после terminal response.')
        obj=event if isinstance(event,dict) else event.model_dump()
        kind=obj.get('type')
        if kind=='response.output_text.delta':
            seen.add((obj.get('output_index',0),obj.get('content_index',0)))
            if len(seen)>1:raise RuntimeError('Несколько структурированных результатов провайдера.')
            delta=obj.get('delta')
            if not isinstance(delta,str):raise RuntimeError('Повреждённый Responses stream.')
            chunks.append(delta);yield delta
        elif kind in ('response.completed','response.incomplete','response.failed'):
            response=obj.get('response',{})
            usage=response.get('usage')
            if usage and on_usage:
                on_usage(dict(prompt_tokens=usage['input_tokens'],completion_tokens=usage['output_tokens'],
                    total_tokens=usage.get('total_tokens',usage['input_tokens']+usage['output_tokens']),
                    prompt_cache_hit_tokens=(usage.get('input_tokens_details') or {}).get('cached_tokens',0),
                    completion_tokens_details={'reasoning_tokens':(usage.get('output_tokens_details') or {}).get('reasoning_tokens',0)}))
            status=response.get('status')
            reason=(response.get('incomplete_details') or {}).get('reason')
            finish='stop' if kind=='response.completed' and status=='completed' else 'length' if reason=='max_output_tokens' else status or 'failed'
            if on_finish:on_finish(finish)
            if finish=='length':
                from llm import OutputLimitReached
                raise OutputLimitReached('Достигнут лимит структурированного ответа.')
            if finish!='stop':raise RuntimeError('Структурированный ответ не завершён.')
            outputs=response.get('output',[])
            messages=[o for o in outputs if o.get('type')=='message']
            if len(messages)!=1 or any(o.get('type') not in ('message','reasoning') for o in outputs):
                raise RuntimeError('Ожидался один текстовый результат, без tool calls.')
            parts=messages[0].get('content',[])
            if len(parts)!=1 or parts[0].get('type')!='output_text' or parts[0].get('text')!=''.join(chunks):
                raise RuntimeError('Терминальный результат не совпадает с Responses stream.')
            if complete:raise RuntimeError('Повторный terminal response.')
            complete=True
    if not complete or not ''.join(chunks).strip():raise RuntimeError('Пустой или незавершённый структурированный ответ.')
