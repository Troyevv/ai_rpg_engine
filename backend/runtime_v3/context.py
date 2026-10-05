"""Scene-first Narrative and Extraction projections of one canonical world."""
from copy import deepcopy
from pathlib import Path
import json
from backend.runtime_v3.scope import RelevanceResolver, CharacterContextClassifier, FULL_PRESENT, FULL_REMOTE, COMPACT_REFERENCED, INDEX
from backend.runtime_v3.context_contract import EXTRACTION_CONTRACT, NARRATIVE_CONTRACT
from backend.runtime_v3.raw import prompt_schema

PROMPTS = Path(__file__).resolve().parents[2] / 'prompts'


def block(name, value):
    return dict(role='user', content=name+'\n'+json.dumps(value, ensure_ascii=False, separators=(',', ':')))


class ContextMessages(list):
    """Wire-compatible list; diagnostics do not consume LLM tokens."""
    def __init__(self, messages, selection):
        super().__init__(messages)
        self.selection = selection


def visible_views(snapshot, turns, kind):
    from backend.services.pov import visible, actor_view
    actor = snapshot['world_state']['camera']['controlled_actor_id']
    main = snapshot.get('campaign', {}).get('protagonist_id')
    return [t if kind == 'background' else actor_view(t, actor, main) for t in turns
            if kind == 'background' or visible(t, actor, main)]


def canonical_slice(state, scope, extraction=False):
    current = dict(meta=state['meta'], camera=state['camera'],
        locations={lid: state['locations'][lid] for lid in scope.location_ids},
        characters={cid: deepcopy(state['characters'][cid]) for cid in sorted(scope.relevant_actor_ids)},
        facts={fid: state['facts'][fid] for fid in scope.fact_ids},
        knowledge=[state['knowledge'][key] for key in scope.knowledge_ids],
        relationships=[state['relationships'][key] for key in scope.relationship_pairs],
        threads=[state['threads'][tid] for tid in scope.thread_ids],
        scheduled_events=[state['scheduled_events'][eid] for eid in scope.scheduled_event_ids])
    for character in current['characters'].values():
        for key in ('goals', 'intentions', 'obligations'):
            character[key] = [r for r in character[key] if isinstance(r, str) or r['status'] == 'active']
        if character['id'] in scope.referenced_actor_ids and not extraction:
            from backend.runtime_v3.scope import words
            for key in ('goals', 'intentions', 'obligations'):
                character[key] = [r for r in character[key] if words(r if isinstance(r, str) else r['text']) & scope.query_words]

            # Compact runtime, not off-camera appearance or physical observations.
            character.pop('physical_state', None)
            character.pop('emotion', None)
            character.pop('emotion_source_sequence', None)
    return current


def legacy_knowledge(snapshot, scope):
    """Read-only compatibility: only relevant unconverted lines, never duplicate Facts.

    Old prose without holders remains GM-only; it cannot grant Knowledge. Existing
    structured imports were already seeded before v3 migration. No audit debt rewritten.
    """
    from backend.runtime_v3.scope import words, mentions
    text = snapshot.get('campaign', {}).get('sections', {}).get('knowledge', '')
    canonical = {f['text'].strip().casefold() for f in snapshot['world_state']['facts'].values()}
    names = [c['name'] for c in snapshot['character_cards'] if c['id'] in scope.relevant_actor_ids]
    result = []
    for line in text.splitlines():
        value = line.lstrip(' -*·').strip()
        if not value or value.startswith('#') or value.split('|', 1)[0].strip().casefold() in canonical: continue
        if mentions(value, names) or words(value) & scope.query_words:
            result.append(value)
    return result[:20]


class NarrativeContextBuilder:
    extraction = False

    def build(self, snapshot, scope, current, views, user_text, kind, prompts, extraction_text):
        from backend.runtime_v3.director import plan
        state = snapshot['world_state']; campaign = snapshot.get('campaign', {})
        prompt_name = 'background_prompt.md' if kind == 'background' else 'game_system_prompt.md'
        rules = (prompts or {}).get(prompt_name, {}).get('content') or (PROMPTS/prompt_name).read_text(encoding='utf-8')
        rules += '\n' + NARRATIVE_CONTRACT
        cards, index = [], []
        classifier = CharacterContextClassifier()
        for card in snapshot['character_cards']:
            mode = classifier.classify(card['id'], scope)
            if mode in (FULL_PRESENT, FULL_REMOTE): cards.append(dict(card, context_mode=mode))
            elif mode == COMPACT_REFERENCED:
                cards.append(dict(id=card['id'], name=card['name'], context_mode=mode,
                                  role=card.get('fields', {}).get('Роль', card.get('role', ''))))
            elif len(index) < 64:
                index.append(dict(id=card['id'], name=card['name'], role=card.get('fields', {}).get('Роль', card.get('role', ''))))
        messages = [block('Кампания / GM-only', dict(campaign=campaign.get('campaign', {}),
                    story_notes=campaign.get('story_notes', ''), tone=campaign.get('sections', {}).get('tone', ''))),
                    block('ContextScope / GM-only', scope.summary()),
                    block('Текущее состояние / GM-only', current),
                    block('Карточки присутствующих / GM-only', cards),
                    block('Индекс персонажей', index),
                    block('Знания POV', pov_knowledge(state, scope.controlled_actor_id, current)),
                    block('Память', dict(strategy='canonical_history', llm_calls=0)),
                    block('Недавняя история / GM-only', scope.history_events),
                    block('Director / GM-only', plan(state, kind, scope=scope))]
        legacy = legacy_knowledge(snapshot, scope)
        if legacy: messages.append(block('Legacy knowledge / GM-only, ownership unknown', legacy))
        # Up to SIX visible scenes; optional previous inputs, never trim prose for a target.
        for view in views:
            messages.extend([dict(role='user', content=view.get('user_text') or 'Продолжить.'),
                             dict(role='assistant', content=view.get('assistant_text', ''))])
        return rules, messages


class ExtractionContextBuilder:
    extraction = True

    def build(self, snapshot, scope, current, views, user_text, kind, prompts, extraction_text):
        default = (PROMPTS/'state_update_prompt.md').read_text(encoding='utf-8')
        saved = (prompts or {}).get('state_update_prompt.md', {}).get('content')
        # Preserve user overrides, but do not send the bundled generic contract twice.
        rules = (saved + '\n' if saved and saved.strip() != default.strip() else '') + EXTRACTION_CONTRACT
        # Only affected IDs and canonical runtime: no card prose, tone, or old narratives.
        # Include physical/emotion baseline also for referenced actors affected in completed text.
        for cid in current['characters']:
            for key in ('physical_state', 'emotion'):
                current['characters'][cid][key] = snapshot['world_state']['characters'][cid][key]
        return rules, [block('Текущее состояние / GM-only', current),
                       block('Entity IDs', [dict(id=c['id'], name=c['name'], aliases=c.get('aliases', []))
                            for c in snapshot['character_cards'] if c['id'] in scope.relevant_actor_ids]),
                       block('JSON Schema', prompt_schema())]


def pov_knowledge(state, actor, current):
    return [dict(k, text=current['facts'][k['fact_id']]['text']) for k in current['knowledge']
            if k['actor_id'] == actor and k['status'] != 'unknown']


def build_context(snapshot, turns, user_text, kind, context_length, reserve, extraction_text=None,
                  validation_feedback=None, recent_turns=6, prompts=None, world_history=None,
                  target_context_budget=18000):
    from context_builder import estimate
    state = snapshot['world_state']; camera = state['camera']
    all_views = visible_views(snapshot, turns, kind)
    # Respect an explicit smaller user setting, but never exceed six narrative turns.
    views = all_views[-min(6, max(0, recent_turns)):] if recent_turns else []
    scope = RelevanceResolver().resolve(snapshot, user_text, all_views[-3:], world_history, extraction_text)
    current = canonical_slice(state, scope, extraction_text is not None)
    builder = ExtractionContextBuilder() if extraction_text is not None else NarrativeContextBuilder()
    rules, messages = builder.build(snapshot, scope, current, views, user_text, kind, prompts, extraction_text)
    rules += f'\nRuntime v3. controlled_actor_id={camera["controlled_actor_id"]}; mode={camera["mode"]}; world_time={state["meta"]["world_time"]} минут.'
    if snapshot.get('_time_skip'): rules += '\nДетерминированный Time Skip: ' + json.dumps(snapshot['_time_skip'], ensure_ascii=False) + '. Описывай только до actual_target, не позже. Hidden не становится знанием игрока.'
    if validation_feedback: rules += '\nИсправь структурную ошибку, верни полный JSON:\n' + validation_feedback
    messages.insert(0, dict(role='system', content='Постоянные правила\n'+rules))
    messages.append(block('Текущий ввод', dict(kind=kind, player_input=user_text)))
    if extraction_text is not None: messages.append(block('completed_narrative', extraction_text))
    hard_context_limit = context_length - reserve - 256
    target = min(target_context_budget, hard_context_limit)

    def replace_block(title, value):
        for i, message in enumerate(messages):
            if message['content'].startswith(title+'\n'): messages[i] = block(title, value); return

    # Only optional records are removed under pressure. Full cards, continuity,
    # motivations, current relationships, topical facts and imminent events survive.
    if estimate(messages) > target:
        replace_block('Индекс персонажей', [])
        optional = [fid for fid in reversed(scope.fact_ids) if scope.fact_scores[fid] < 60]
        for fid in optional:
            if estimate(messages) <= target: break
            del current['facts'][fid]
            current['knowledge'] = [k for k in current['knowledge'] if k['fact_id'] != fid]
            replace_block('Текущее состояние / GM-only', current)
            replace_block('Знания POV', pov_knowledge(state, scope.controlled_actor_id, current))
    if estimate(messages) > hard_context_limit:
        raise ValueError('Контекст v3 не помещается в выбранную модель. Увеличь контекст или уменьши лимит ответа. Критические данные сцены и последние narrative сохранены.')
    classifier = CharacterContextClassifier()
    counts = {mode: 0 for mode in (FULL_PRESENT, FULL_REMOTE, COMPACT_REFERENCED, INDEX)}
    for cid in state['characters']: counts[classifier.classify(cid, scope)] += 1
    sections = {key: dict(selected=len(current[key]), total=len(state[key]))
                for key in ('locations', 'facts', 'knowledge', 'relationships', 'threads', 'scheduled_events')}
    sections['history_events'] = dict(selected=0 if builder.extraction else len(scope.history_events), total=len((world_history or {}).get('events', [])))
    diagnostics = dict(mode=('World Simulation ' if kind == 'background' else '') + ('Extraction' if builder.extraction else 'Narrative'),
        characters=counts, character_total=len(state['characters']), sections=sections,
        narrative_continuity=0 if builder.extraction else len(views), previous_player_inputs=0 if builder.extraction else len(views),
        target_context_budget=target, hard_context_limit=hard_context_limit, target_exceeded=estimate(messages)>target)
    return ContextMessages(messages, diagnostics)
