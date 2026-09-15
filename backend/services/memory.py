"""Objective and actor-scoped memory: private scenes never enter absent actors' input."""
from copy import deepcopy
import uuid
from pathlib import Path
from context_builder import encoded, estimate
from backend.services.pov import protagonist,visible,actor_view


def compact(storage, job, state, history, config, generate, cancelled):
    state=deepcopy(state)
    memory=state.get('memory',{})
    recent=config.get('recent_turns',6)
    batch=config.get('memory_batch',4)
    candidates=[t for t in history[:-recent] if t['sequence']>memory.get('through_sequence',-1)]
    prompt=(config.get('_prompts',{}).get('memory_prompt.md') or {}).get('content')
    if prompt is None:
        prompt=(Path(__file__).resolve().parents[2]/'prompts/memory_prompt.md').read_text(encoding='utf-8')
    def summarize(previous,turns,pov):
        messages=[{'role':'system','content':prompt},{'role':'user','content':encoded({'POV':pov,'previous_memory':previous,
            'turns':[{'sequence':t['sequence'],'player':t['user_text'],'narrator':t['assistant_text']} for t in turns]})}]
        if estimate(messages)>config['context_length']-config['update_tokens']-256:
            raise ValueError('Пакет памяти не помещается в контекст. Уменьши пакет или увеличь контекст.')
        result=''.join(generate(messages)).strip()
        if cancelled.is_set():
            return ''
        if not result or len(result)>8000:
            raise ValueError('Выжимка памяти пуста или длиннее 8000 символов.')
        return result
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
