"""Named, bounded prompt blocks. Saved verbatim for reproducible regeneration."""
import json
import re
from pathlib import Path
from character_links import character_aliases
from backend.services.pov import protagonist,controlled,visible,role_rules,actor_view

PROMPTS = Path(__file__).resolve().parent / 'prompts'


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def estimate(messages):
    # Conservative multilingual UTF-8 estimate, not a provider tokenizer.
    return sum((len(m['content'].encode('utf-8'))+1)//2+32 for m in messages)+256


def describe_context(messages):
    parts = []
    for i,m in enumerate(messages):
        title = m['content'].split('\n',1)[0]
        if len(title)>100:
            title = 'Сообщение ' + str(i+1)
        parts.append({'name':title,'role':m['role'],'estimated_tokens':estimate([m])-256,'content':m['content']})
    return {'parts':parts,'overhead_tokens':256,'estimated_tokens':estimate(messages),
            'token_method':'Оценка UTF-8, не точный токенизатор. Фактический input — из usage API.'}


def build_context(state, history, user_text, kind, context_length, reserve, extraction_text=None,
                  validation_feedback=None, recent_turns=6, prompts=None):
    prompt_name = 'state_update_prompt.md' if extraction_text is not None else 'background_prompt.md' if kind=='background' else 'game_system_prompt.md'
    if kind=='background' and extraction_text is None and state.get('camera',{}).get('scope')=='scene':prompt_name='game_system_prompt.md'
    rules = prompts[prompt_name]['content'] if prompts and prompt_name in prompts else (PROMPTS/prompt_name).read_text(encoding='utf-8')
    from backend.services.world import normalize,knowledge_for
    from backend.services.director import Director
    state=normalize(state)
    world=state['world']
    contract=(prompts or {}).get('world_state_prompt.md',{}).get('content') or (PROMPTS/'world_state_prompt.md').read_text(encoding='utf-8')
    rules += '\n'+(contract if extraction_text is not None else contract.split('ТОЛЬКО при извлечении')[0])
    from backend.services.timeline import current_time,label
    dynamic = '\nЕдиное время мира: '+label(current_time(state))+'. Не возвращай время назад. В scene.time используй День N (день недели) HH:MM. Переход POV синхронный, без флешбэка.'
    dynamic += ('\nПРАВИЛО ЧАСОВ: действия и разговоры занимают игровое время. При извлечении добавь в scene '
                'elapsed_minutes — целую длительность показанного хода. Оцени по действиям (короткий обмен обычно 1–3 минуты), '
                'учти явно прошедшее время; не сохраняй старые часы автоматически. scene.time — конечное время, '
                'согласованное с elapsed_minutes. Ноль допустим для мгновенной реакции, стартового/POV-вступления '
                'или параллельной симуляции до текущего времени. Не делай необоснованных таймскипов. '
                'Неделя циклична: после воскресенья понедельник; День N продолжает расти. '
                'Это правило уточняет старые инструкции о сохранении времени.')
    dynamic += role_rules(state,kind,extraction_text is not None)
    main,actor=protagonist(state),controlled(state)
    if validation_feedback:
        dynamic += ('\nПредыдущее извлечение отклонено: '+validation_feedback+
                  '\nВерни полный исправленный JSON. Копируй evidence непрерывно из completed_narrative или player_input. '
                  'Не используй историю и состояние мира как источник цитаты. Если цитаты нет, исключи изменение. '
                  + ('Сохрани фиксацию сцены и choices=[]. Не продолжай сцену.' if kind=='background' else 'Сохрани фиксацию сцены и ровно 6 вариантов. Не продолжай сцену.'))
    present = set(state.get('scene_meta',{}).get('present_ids',[]))
    for alias,cid in character_aliases(state['characters']).items():
        if re.search(r'(?<!\w)'+re.escape(alias)+r'(?!\w)', user_text, re.I):
            present.add(cid)
    if actor:present.add(actor)
    if kind=='start' or not state.get('scene_meta'):
        present.update(c['id'] for c in state['characters'])
    if kind=='background':
        present=set(state.get('scene_meta',{}).get('present_ids',[]))
        if state['camera'].get('scope')!='scene':present.discard(main)
    cards = [{**c,'is_player':c['id']==actor,'is_protagonist':c['id']==main,'fields':{k:v for k,v in c['fields'].items() if not k.startswith('Отношение к ')}}
             for c in state['characters'] if c['id'] in present]
    objective_memory = state.get('memory',{})
    per_actor=objective_memory.get('per_actor',{})
    memory = {k:v for k,v in objective_memory.items() if k!='per_actor'} if kind=='background' else per_actor.get(actor,objective_memory if actor==main and not per_actor else {})
    def block(name,value):
        return {'role':'user','content':name+'\n'+encoded(value)}
    direction=Director().plan(state,kind)
    knowledge=knowledge_for(world,actor)
    relevant_facts={k['fact_id'] for k in knowledge}
    relevant_facts.update(f['id'] for f in world['facts'].values() if present.intersection(f.get('character_ids',[])))
    relevant_events=[e for e in world['events'].values() if present.intersection(e['participants'])][-12:]
    messages = [
        {'role':'system','content':'Постоянные правила\n'+rules},
        block('Выжимка мира', {'tone':state['sections'].get('tone',''), 'director_only':{'rules':state.get('story_notes',''),
                              'initial_knowledge_unstructured':state['sections'].get('knowledge','')}}),
        {'role':'system','content':'Роли и время текущего запроса\n'+dynamic},
        block('POV и знания', {'protagonist_id':main,'controlled_actor_id':actor,'mode':kind,'world_clock':state.get('world_clock',{}),'transition':state.get('pov_transition') if kind=='pov' else None,
                               'camera':state['camera'],'actor_knowledge':knowledge[-30:],'known_facts':[f for f in knowledge if f['status']=='known'][-30:]}),
        block('NPC и отношения', {'characters':cards,'visibility':'GM-only: карточки не являются общими знаниями','cast_index':[{'id':c['id'],'name':c['name']} for c in state['characters']],
                                 'relationships':[dict(r,existing_index=i) for i,r in enumerate(state['relationships']) if r['source_id'] in present]}),
        block('Память завершённых событий',memory),
        block('Objective world state / GM-only', {
            'characters':[world['characters'][cid] for cid in sorted(present) if cid in world['characters']],
            'knowledge_by_character':{cid:knowledge_for(world,cid)[-20:] for cid in sorted(present)},
            'facts':[world['facts'][fid] for fid in sorted(relevant_facts)[-30:]],
            'relationships':[r for key,r in sorted(world['relationships'].items()) if r['source_id'] in present and r['target_id'] in present][:30],
            'threads':[world['threads'][tid] for tid in direction['thread_ids']],
            'timeline':relevant_events,
            'scheduled_events':[world['scheduled_events'][eid] for eid in direction['due_event_ids']],
            'director':direction}),
        block('Текущая сцена', {'scene':state['scene'],'scene_meta':state.get('scene_meta'),'locations':state['locations'][-20:]})]
    task = ('Разыграй стартовую сцену. Не делай ход за ГГ.' if kind=='start' else user_text)
    if kind=='pov':
        task='Покажи короткое POV-вступление управляемого персонажа здесь и сейчас. Опирайся на последнюю известную точку, его знания, события и открытые линии. Не решай и не действуй за него. Если source_node_id указан, продолжи именно ситуацию завершённой фоновой сцены, не начинай несвязанную. Не раскрывай чужие мысли. Остановись перед выбором игрока; обработчик подготовит 6 действий.'
    if kind=='background':
        task='Продолжи выбранную камерой сцену, соблюдая ограничения участников из правил ролей. Если она ещё не показана, естественно введи её. Учитывай world_clock и незакрытые дела.'
    if extraction_text is not None:
        task = encoded({'kind':kind,'player_input':user_text,'completed_narrative':extraction_text})
    end = {'role':'user','content':'Задача текущего хода\n'+task}
    budget = int(context_length)-int(reserve)-256
    if estimate(messages+[end])>budget:
        raise ValueError('Основное состояние не помещается в контекст. Увеличь контекст модели или сократи основу мира/лимит ответа.')
    recent = []
    eligible = [t for t in history if t['sequence']>memory.get('through_sequence',-1) and (any(visible(t,cid,main) for cid in present) if kind=='background' else visible(t,actor,main))]
    for turn in reversed(eligible[-recent_turns:]):
        if kind!='background':
            turn=actor_view(turn,actor,main)
        pair = ([{'role':'user','content':turn['user_text']}] if turn['user_text'] else [])
        pair.append({'role':'assistant','content':turn['assistant_text']})
        if estimate(messages+pair+recent+[end])>budget:
            break
        recent = pair+recent
    return messages+recent+[end]
