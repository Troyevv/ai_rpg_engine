"""Provider usage is authoritative. Missing usage/cost remains unknown, not zero."""
from decimal import Decimal
import time
from context_builder import estimate

PRICE_SOURCE = 'https://api-docs.deepseek.com/quick_start/pricing/'
PRICE_VERSION = '2026-09-15'


def price_snapshot(config, now):
    provider, model = config.get('provider','local'), config['model']
    if provider == 'local':
        return {'input':0,'cached':0,'output':0,'currency':'USD','version':'local'}
    # Snapshot the applicable published tariff, never retroactively reprice history.
    rates = {'deepseek-flash': (.3,.006,1.2), 'deepseek-v4-flash': (.3,.006,1.2),
             'deepseek-v4-flash-vision-exp': (.3,.006,1.2), 'deepseek-v4-pro': (1.32,.044,3.96)}
    if provider != 'deepseek' or model not in rates:
        return None
    peak = now.weekday()<5 and (1<=now.hour<4 or 6<=now.hour<10)
    factor = Decimal(1) if peak else Decimal('.5')
    return {**{k:str(Decimal(str(v))*factor) for k,v in zip(('input','cached','output'),rates[model])},
            'currency':'USD','version':PRICE_VERSION,'source':PRICE_SOURCE,'period':'peak' if peak else 'off-peak',
            'estimated':True}


def usage_values(usage):
    if not isinstance(usage,dict):
        return None,None,None
    def number(v):
        return v if type(v) is int and v>=0 else None
    inp, out = number(usage.get('prompt_tokens')), number(usage.get('completion_tokens'))
    cached = number(usage.get('prompt_cache_hit_tokens', (usage.get('prompt_tokens_details') or {}).get('cached_tokens')))
    return inp,out,cached


def cost(inp,out,cached,pricing):
    if pricing and pricing.get('version') == 'local':
        return '0'
    if pricing is None or None in (inp,out,cached) or cached>inp:
        return None
    return str(((inp-cached)*Decimal(pricing['input'])+cached*Decimal(pricing['cached'])+out*Decimal(pricing['output']))/Decimal(1000000))


def tracked_stream(storage, stream_fn, job_id, stage, config, messages, diagnostics=None, **kwargs):
    from llm import thinking_options, OutputLimitReached, ProviderHTTPError
    # Persist model settings only. Credentials and transport options belong to stream_fn.
    effective = {key: config[key] for key in (
        'provider', 'model', 'context_length', 'max_tokens', 'update_tokens',
        'temperature', 'private_artifacts',
    ) if key in config}
    effective['thinking'] = thinking_options(
        config.get('provider', 'local'), config['model'], config.get('thinking', 'off')
    )[0]
    effective.update({k:kwargs[k] for k in ('max_tokens','temperature','response_format') if k in kwargs})
    if config.get('_extraction_contract',1) >= 6:
        from backend.services.structured_extraction import STAGES, transport, request_schema
        if stage in STAGES:
            selected=config.get('_extraction_transport',transport(config))
            schema=request_schema(messages)
            effective.update(extraction_contract=config['_extraction_contract'], extraction_transport=selected, extraction_schema=schema)
            if selected=='responses_json_schema':
                effective.pop('response_format',None)
                name = f"extraction_v{config['_extraction_contract']}" if config['_extraction_contract'] >= 9 else 'extraction_v6'
                effective['text_format']={'type':'json_schema','name':name}
                if config['_extraction_contract'] >= 9:
                    kwargs['structured_name'] = name
                kwargs.update(structured_schema=schema, extraction_transport=selected)
            elif selected!='chat_json_object':
                raise ValueError('Неизвестный записанный transport Extraction.')
    diagnostics = dict(diagnostics or {'estimated_tokens':estimate(messages), 'parts':[]})
    # Chat owns its own reply/summary context contract and has already run preflight.
    if '_budget_caps' in config:
        from backend.services.token_budget import plan_request
        plan = plan_request(config, stage, messages, kwargs['max_tokens'],
                            **{k:kwargs[k] for k in ('temperature','response_format','structured_schema','structured_name') if k in kwargs})
        effective['max_tokens'] = kwargs['max_tokens'] = plan['output_allowance']
        diagnostics.update(budget_plan=plan, estimated_tokens=plan['estimated_input'], token_method=plan['estimate_method'])
    from backend.services.provider_attempt import CURRENT, failed
    rid = storage.begin_request(job_id,stage,effective,messages,diagnostics)
    if hasattr(messages, '__dict__'):
        messages.request_id = rid  # Exact request identity for subsequent candidate audit.
    attempt = dict(request_id=rid, job_id=job_id, stage=stage, stream_complete=False, terminal_seen=False)
    epoch = getattr(storage, 'worker_epoch', None)
    if epoch is not None: attempt['attempt_epoch'] = epoch
    persist = getattr(storage, 'record_provider_attempt', None)
    token = CURRENT.set(dict(data=attempt, persist=(lambda data: persist(rid, data)) if persist else None))
    started=time.perf_counter()
    response = []
    usage, status, finish_reason = None, 'error', None
    provider_error = None
    def received(value):
        nonlocal usage
        usage = value
    def finished(value):
        nonlocal finish_reason
        finish_reason=value
        attempt['finish_reason'] = value
    try:
        for chunk in stream_fn(messages=messages, thinking=effective['thinking'], on_usage=received, on_finish=finished, **kwargs):
            response.append(chunk)
            yield chunk
        if finish_reason == 'length': raise OutputLimitReached('Достигнут лимит ответа.')
        status = 'complete'
        attempt['stream_complete'] = True
    except GeneratorExit as exc:
        failed(exc)
        status = 'stopped'
        raise
    except OutputLimitReached as exc:
        failed(exc)
        status = 'length'
        raise
    except ProviderHTTPError as exc:
        failed(exc)
        provider_error = exc.diagnostic
        raise
    except Exception as exc:
        failed(exc)
        raise
    finally:
        event = kwargs.get('cancel_event')
        if event is not None and event.is_set():
            status = 'stopped'
        attempt.update(status=status, finish_reason=finish_reason, usage_received=usage is not None)
        try:
            storage.finish_request(
                rid, status, usage, time.perf_counter() - started, finish_reason,
                response_text=''.join(response), provider_error=provider_error, provider_attempt=attempt,
            )
        finally:
            CURRENT.reset(token)
