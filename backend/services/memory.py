"""Objective and actor-scoped memory: private scenes never enter absent actors' input."""
from copy import deepcopy
import uuid
import json
from backend.services.memory_compactor import Compactor, MemoryDeferred
from pathlib import Path
from context_builder import encoded
from backend.services.pov import protagonist,visible,actor_view


def compact(storage, job, state, history, config, generate, cancelled):
    state=deepcopy(state)
    sequence=max((t['sequence'] for t in history),default=-1)
    if sequence<state.get('memory_maintenance',{}).get('retry_after_sequence',-1):
        return state
    try:
        result=_compact(storage,job,state,history,config,generate,cancelled)
        if not cancelled.is_set():result.pop('memory_maintenance',None)
        return result
    except MemoryDeferred as exc:
        if cancelled.is_set():return state
        # No cursor advancement or archival for the failed chunk. Previous
        # successfully compacted chunks remain usable; full source stays in DB.
        state['memory_maintenance']={'retry_after_sequence':sequence+max(1,config.get('memory_batch',4))}
        with storage.connect() as db:
            row=db.execute('SELECT warnings_json FROM game_jobs WHERE id=?',(job['id'],)).fetchone()
            warnings=json.loads(row[0] or '[]')
            warnings.append({'section':'Память','reason':'Обновление памяти отложено: '+str(exc)+' Предыдущая память и полная история сохранены.','rejected':None})
            db.execute('UPDATE game_jobs SET warnings_json=? WHERE id=?',(encoded(warnings),job['id']))
        return state


def _compact(storage, job, state, history, config, generate, cancelled):
    memory=state.get('memory',{})
    recent=config.get('recent_turns',6)
    batch=config.get('memory_batch',4)
    candidates=[t for t in history[:-recent] if t['sequence']>memory.get('through_sequence',-1)]
    prompt=(config.get('_prompts',{}).get('memory_prompt.md') or {}).get('content')
    if prompt is None:
        prompt=(Path(__file__).resolve().parents[2]/'prompts/memory_prompt.md').read_text(encoding='utf-8')
    summarize=Compactor(prompt,config,generate,cancelled).summarize
    while candidates:
        chunk=candidates[:batch]
        summary=summarize(memory.get('summary',''),chunk,'Объективная память ведущего')
        if cancelled.is_set():
            return state
        per_actor=deepcopy(memory.get('per_actor',{}))
        main=protagonist(state)
        if not per_actor and memory.get('summary'):
            # Legacy summaries only had protagonist scenes; never assign to other POVs.
            per_actor[main]={'summary':memory['summary'],'through_sequence':memory.get('through_sequence',-1)}
        for card in state['characters']:
            actor=card['id']
            seen=[actor_view(t,actor,main) for t in chunk if visible(t,actor,main)]
            if seen:
                prior=per_actor.get(actor,{})
                per_actor[actor]={'summary':summarize(prior.get('summary',''),seen,actor),'through_sequence':chunk[-1]['sequence']}
            if cancelled.is_set():
                return state
        mid=uuid.uuid4().hex
        memory={'id':mid,'summary':summary,'per_actor':per_actor,'through_sequence':chunk[-1]['sequence'],
                'source_node_ids':[t.get('node_id') for t in chunk],'previous_id':memory.get('id')}
        with storage.connect() as db:
            db.execute('INSERT INTO memory_versions(id,save_id,job_id,through_sequence,payload) VALUES(?,?,?,?,?)',
                       (mid,job['save_id'],job['id'],memory['through_sequence'],encoded(memory)))
        state['memory']=memory
        candidates=candidates[batch:]
    return state
