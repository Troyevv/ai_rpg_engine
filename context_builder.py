"""Budgeted context; an approximate byte-based estimate never silently clips core state."""
import json
import re
from character_links import character_aliases
from pathlib import Path

PROMPTS = Path(__file__).resolve().parent / 'prompts'


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def estimate(messages):
    # Approximation for multilingual prose; the provider may still reject overflow.
    return sum((len(m['content'].encode('utf-8')) + 1) // 2 + 32 for m in messages) + 256


def build_context(state, history, user_text, kind, context_length, reserve, extraction_text=None):
    rules = (PROMPTS / ('state_update_prompt.md' if extraction_text is not None else 'game_system_prompt.md')).read_text()
    present = set(state.get('scene_meta', {}).get('present_ids', []))
    for alias, cid in character_aliases(state['characters']).items():
        if re.search(r'(?<!\w)' + re.escape(alias) + r'(?!\w)', user_text, re.I):
            present.add(cid)
    for card in state['characters']:
        if card.get('is_player') or card['name'].replace(' (ГГ)', '').casefold() in user_text.casefold():
            present.add(card['id'])
    # Unknown starting presence needs the full cast to establish the opening.
    if kind == 'start' or not state.get('scene_meta'):
        present.update(c['id'] for c in state['characters'])
    cards = []
    for card in state['characters']:
        if card['id'] in present:
            cards.append({'id': card['id'], 'name': card['name'], 'is_player': card['is_player'],
                          'fields': {k: v for k, v in card['fields'].items() if not k.startswith('Отношение к ')}})
    core = {'scene': state['scene'], 'scene_meta': state.get('scene_meta'), 'characters': cards,
            'cast_index': [{'id': c['id'], 'name': c['name']} for c in state['characters']],
            'tone': state['sections']['tone'], 'rules': state['story_notes'],
            'relationships': [dict(r, existing_index=index) for index, r in enumerate(state['relationships']) if r['source_id'] in present],
            'initial_knowledge': state['sections']['knowledge'], 'locations': state['locations'],
            'plans': [p for p in state.get('plans', []) if p['status'] == 'open'],
            'facts': [f for f in state.get('facts', []) if present.intersection(f['known_by'])]}
    task = ('Разыграй стартовую сцену из исходной ситуации. Не пересказывай выжимку. Не делай ход за ГГ.'
            if kind == 'start' else user_text)
    if extraction_text is not None:
        task = encoded({'kind': kind, 'player_input': user_text, 'completed_narrative': extraction_text})
    messages = [{'role': 'system', 'content': rules}, {'role': 'user', 'content': 'Состояние мира (данные):\n' + encoded(core)}]
    end = {'role': 'user', 'content': task}
    budget = int(context_length) - int(reserve) - 256
    if estimate(messages + [end]) > budget:
        raise ValueError('Основное состояние не помещается в контекст. Увеличь контекст модели или сократи основу мира/лимит ответа.')
    # Prefer the newest full turns. Keep chronological order and never split a turn.
    recent = []
    for turn in reversed(history[-6:]):
        pair = ([{'role': 'user', 'content': turn['user_text']}] if turn['user_text'] else [])
        pair.append({'role': 'assistant', 'content': turn['assistant_text']})
        if estimate(messages + pair + recent + [end]) > budget:
            break
        recent = pair + recent
    # Related event records retain exact source turn IDs; the full journal stays in SQLite.
    words = set(re.findall(r'\w{4,}', user_text.casefold()))
    events = sorted(state.get('events', []), key=lambda e: (
        bool(present.intersection(e['character_ids'])), bool(words.intersection(re.findall(r'\w{4,}', e['text'].casefold()))), e['turn']), reverse=True)
    memory = []
    for event in events:
        candidate = {'role': 'user', 'content': 'Память событий:\n' + encoded(memory + [event])}
        if estimate(messages + [candidate] + recent + [end]) <= budget:
            memory.append(event)
    if memory:
        messages.append({'role': 'user', 'content': 'Память событий:\n' + encoded(memory)})
    return messages + recent + [end]
