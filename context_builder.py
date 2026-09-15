"""Named, bounded prompt blocks. Saved verbatim for reproducible regeneration."""
import json
import re
from pathlib import Path
from character_links import character_aliases

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
                  validation_feedback=None, recent_turns=6):
    rules = (PROMPTS / ('state_update_prompt.md' if extraction_text is not None else 'game_system_prompt.md')).read_text(encoding='utf-8')
    if validation_feedback:
        rules += ('\nПредыдущее извлечение отклонено: '+validation_feedback+
                  '\nВерни полный исправленный JSON. Копируй evidence непрерывно из completed_narrative или player_input. '
                  'Не используй историю и состояние мира как источник цитаты. Если цитаты нет, исключи изменение. '
                  'Сохрани фиксацию сцены и ровно 6 вариантов. Не продолжай сцену.')
    present = set(state.get('scene_meta',{}).get('present_ids',[]))
    for alias,cid in character_aliases(state['characters']).items():
        if re.search(r'(?<!\w)'+re.escape(alias)+r'(?!\w)', user_text, re.I):
            present.add(cid)
    present.update(c['id'] for c in state['characters'] if c.get('is_player'))
    if kind=='start' or not state.get('scene_meta'):
        present.update(c['id'] for c in state['characters'])
    cards = [{**c,'fields':{k:v for k,v in c['fields'].items() if not k.startswith('Отношение к ')}}
             for c in state['characters'] if c['id'] in present]
    memory = state.get('memory',{})
    def block(name,value):
        return {'role':'user','content':name+'\n'+encoded(value)}
    messages = [
        {'role':'system','content':'Постоянные правила\n'+rules},
        block('Выжимка мира', {'tone':state['sections'].get('tone',''), 'rules':state.get('story_notes',''),
                              'initial_knowledge':state['sections'].get('knowledge','')}),
        block('NPC и отношения', {'characters':cards,'cast_index':[{'id':c['id'],'name':c['name']} for c in state['characters']],
                                 'relationships':[dict(r,existing_index=i) for i,r in enumerate(state['relationships']) if r['source_id'] in present]}),
        block('Память завершённых событий',memory),
        block('Важные события и знания', {'events':state.get('events',[])[-20:],
              'facts':[f for f in state.get('facts',[]) if present.intersection(f['known_by'])][-30:],
              'plans':[p for p in state.get('plans',[]) if p['status']=='open'][-20:]}),
        block('Текущая сцена', {'scene':state['scene'],'scene_meta':state.get('scene_meta'),'locations':state['locations'][-20:]})]
    task = ('Разыграй стартовую сцену. Не делай ход за ГГ.' if kind=='start' else user_text)
    if extraction_text is not None:
        task = encoded({'kind':kind,'player_input':user_text,'completed_narrative':extraction_text})
    end = {'role':'user','content':'Задача текущего хода\n'+task}
    budget = int(context_length)-int(reserve)-256
    if estimate(messages+[end])>budget:
        raise ValueError('Основное состояние не помещается в контекст. Увеличь контекст модели или сократи основу мира/лимит ответа.')
    recent = []
    eligible = [t for t in history if t['sequence']>memory.get('through_sequence',-1)]
    for turn in reversed(eligible[-recent_turns:]):
        pair = ([{'role':'user','content':turn['user_text']}] if turn['user_text'] else [])
        pair.append({'role':'assistant','content':turn['assistant_text']})
        if estimate(messages+pair+recent+[end])>budget:
            break
        recent = pair+recent
    return messages+recent+[end]
