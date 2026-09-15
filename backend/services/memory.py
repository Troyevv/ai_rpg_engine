"""Compact completed history in bounded batches; keep originals and version every result."""
from copy import deepcopy
import uuid
from context_builder import encoded, estimate


def compact(storage, job, state, history, config, generate, cancelled):
    state = deepcopy(state)
    memory = state.get('memory',{})
    recent = config.get('recent_turns',6)
    batch = config.get('memory_batch',4)
    candidates = [t for t in history[:-recent] if t['sequence']>memory.get('through_sequence',-1)]
    while candidates:
        chunk = candidates[:batch]
        messages = [{'role':'system','content':'Обнови компактную память ролевой игры по завершённым ходам. '
                     'Сохрани важные события, причинные связи, обещания, изменения отношений и кто что знает. '
                     'Не принимай предложенные действия за события. Не придумывай факты. '
                     'Верни только выжимку до 8000 символов, сохрани важное из предыдущей памяти.'},
                    {'role':'user','content':encoded({'previous_memory':memory.get('summary',''),
                      'turns':[{'sequence':t['sequence'],'player':t['user_text'],'narrator':t['assistant_text']} for t in chunk]})}]
        if estimate(messages)>config['context_length']-config['update_tokens']-256:
            raise ValueError('Пакет памяти не помещается в контекст. Уменьши размер пакета или увеличь контекст.')
        summary = ''.join(generate(messages)).strip()
        if cancelled.is_set():
            return state
        if not summary or len(summary)>8000:
            raise ValueError('Выжимка памяти пустая или длиннее 8000 символов. Увеличь лимит обработки или уменьши пакет памяти.')
        mid = uuid.uuid4().hex
        memory = {'id':mid,'summary':summary,'through_sequence':chunk[-1]['sequence'],
                  'source_node_ids':[t.get('node_id') for t in chunk],'previous_id':memory.get('id')}
        with storage.connect() as db:
            db.execute('INSERT INTO memory_versions(id,save_id,job_id,through_sequence,payload) VALUES(?,?,?,?,?)',
                       (mid,job['save_id'],job['id'],memory['through_sequence'],encoded(memory)))
        state['memory'] = memory
        candidates = candidates[batch:]
    return state
