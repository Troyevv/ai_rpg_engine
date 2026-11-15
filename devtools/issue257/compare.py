"""Bounded comparison using production compiler/Resolver/repair. No CLI dispatch.

Call only with an explicitly authorized existing Budget-wrapped transport and a
persistent recorder. Acceptance remains independent human evaluation, never saved.
"""
from copy import deepcopy
import json
import time
from context_builder import estimate
from backend.runtime_v3.scene_repair import SceneCandidate, repair_schema
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.player_actions import resolver_options
from backend.services.structured_extraction import request_schema
from backend.services.world_delta_errors import StructuralDeltaError
from .prepare import compact


def run(case, variant, generate, record, *, candidate_type=SceneCandidate):
    state=case['snapshot']['world_state'];turn=state['meta']['turn_id']+1
    candidate=candidate_type(state,case['narrative'],case['player_input'],turn,version=7,on_record=lambda audit:record(dict(event='candidate',audit=audit)))
    messages=deepcopy(case['messages'][variant]);start=time.monotonic();attempts=[]
    for attempt in range(2):
        usage=[];chunks=[];t=time.monotonic()
        config=dict(provider='deepseek',model=case['profiles'][variant],thinking='off',temperature=.1,max_tokens=8192,
                    response_format={'type':'json_object'},structured_schema=request_schema(messages),extraction_transport='responses_json_schema')
        assert estimate(messages)<case['config']['context_length']-8192-256
        record(dict(event='request',attempt=attempt,messages=messages,config=config))
        try:
            for chunk in generate(messages=messages,require_complete=True,on_usage=usage.append,**config):
                chunks.append(chunk);record(dict(event='chunk',attempt=attempt,text=chunk))
        except BaseException as exc:
            record(dict(event='error',attempt=attempt,error_type=type(exc).__name__,partial=''.join(chunks),usage=usage));raise
        response=''.join(chunks)
        item=dict(attempt=attempt,response=response,usage=usage,provider_seconds=time.monotonic()-t)
        record(dict(event='response',**item));attempts.append(item)
        try:
            raw=candidate.parse(response,defer_errors=True)
            options=case.get('resolver_options') or resolver_options(state,case['player_input'],contract_version=7)
            result=StateResolver(state,case['narrative'],case['player_input'],turn_id=turn,**options).resolve(raw)
            record(dict(event='resolved',state=result.state,history=result.history,semantic_status='REQUIRES_INDEPENDENT_REVIEW'))
            break
        except StructuralDeltaError as exc:
            diagnostics=exc.diagnostics('comparison');record(dict(event='diagnostics',diagnostics=diagnostics))
            if attempt or not exc.repairable:break
            feedback=candidate.feedback(diagnostics,response)
            # Same frozen content and existing production patch schema; no oracle.
            messages=deepcopy(case['messages']['A' if variant=='B' else variant])
            for m in messages:
                if m['content'].startswith('JSON Schema\n'):
                    schema=json.loads(m['content'].split('\n',1)[1]);m['content']='JSON Schema\n'+json.dumps(repair_schema(schema,feedback),ensure_ascii=False,separators=(',',':'))
            messages[0]['content']+='\nПовторно интерпретируй неизменный Narrative; верни ответ по JSON Schema и repair_mode:\n'+feedback
            if variant=='B':messages=compact(messages)
    record(dict(event='end',calls=len(attempts),end_to_end_seconds=time.monotonic()-start))
    return attempts
