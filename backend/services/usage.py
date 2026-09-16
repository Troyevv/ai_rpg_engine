"""Provider usage is authoritative. Missing usage/cost remains unknown, not zero."""
from decimal import Decimal
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
    from llm import thinking_options, OutputLimitReached
    effective = dict(config, thinking=thinking_options(config.get('provider','local'),config['model'],config.get('thinking','off'))[0])
    effective.update({k:kwargs[k] for k in ('max_tokens','temperature','response_format') if k in kwargs})
    rid = storage.begin_request(job_id,stage,effective,messages,diagnostics or {'estimated_tokens':estimate(messages),'parts':[]})
    usage, status = None, 'error'
    def received(value):
        nonlocal usage
        usage = value
    try:
        yield from stream_fn(messages=messages, thinking=effective['thinking'], on_usage=received, **kwargs)
        status = 'complete'
    except OutputLimitReached:
        status = 'length'
        raise
    finally:
        event = kwargs.get('cancel_event')
        if event is not None and event.is_set():
            status = 'stopped'
        storage.finish_request(rid,status,usage)
