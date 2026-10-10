"""Scene-first Narrative and Extraction projections of one canonical world."""
from copy import deepcopy
from pathlib import Path
import json
from backend.runtime_v3.scope import RelevanceResolver, CharacterContextClassifier, FULL_PRESENT, FULL_REMOTE, ACTIVE_REFERENCED, COMPACT_REFERENCED, INDEX
from backend.runtime_v3.context_contract import EXTRACTION_CONTRACT, NARRATIVE_CONTRACT, TIME_CONTRACT
from backend.runtime_v3.raw import prompt_schema
from backend.runtime_v3.calendar import current_time, nearby_calendar, age_on, profile_of, scheduled_time, commitment_view

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


def canonical_slice(state, scope, extraction=False, query=""):
    current = dict(meta={k:v for k,v in state['meta'].items() if k != 'calendar'},
        current_time=current_time(state), calendar_context=nearby_calendar(state, scope.relevant_actor_ids), camera=state['camera'],
        locations={lid: state['locations'][lid] for lid in scope.location_ids},
        characters={cid: deepcopy(state['characters'][cid]) for cid in sorted(scope.relevant_actor_ids)},
        facts={fid: state['facts'][fid] for fid in scope.fact_ids},
        knowledge=[state['knowledge'][key] for key in scope.knowledge_ids],
        relationships=[state['relationships'][key] for key in scope.relationship_pairs],
        threads=[state['threads'][tid] for tid in scope.thread_ids],
        scheduled_events=[commitment_view(state,state['scheduled_events'][eid]) for eid in scope.scheduled_event_ids])
    for character in current['characters'].values():
        character['age'] = age_on(character.get('birth_date'), current['current_time']['date'], profile_of(state))
        for key in ('goals', 'intentions', 'obligations'):
            character[key] = [r for r in character[key] if isinstance(r, str) or r['status'] == 'active']
        if not extraction:
            cid = character['id']
            if cid in scope.referenced_actor_ids:
                character.clear(); character['id'] = cid
            elif cid in scope.active_actor_ids or cid in scope.remote_actor_ids:
                from backend.runtime_v3.scope import words
                # Off-camera runtime is not observable physical scenery.
                for key in ('location_id', 'physical_state', 'emotion', 'emotion_source_sequence'):
                    character.pop(key, None)
                if not words(character.get('situation', '')) & scope.query_words:
                    character.pop('situation', None)
                for key in ('goals', 'intentions', 'obligations'):
                    character[key] = [r for r in character[key] if words(r if isinstance(r, str) else r['text']) & scope.query_words][:3]
    from backend.runtime_v3.life import capabilities
    relevant = scope.relevant_actor_ids
    relations = [r for r in state.get('objective_relations',{}).values()
        if {r['source_id'],r['target_id']} & relevant]
    current['objective_relations'] = deepcopy(sorted(relations,
        key=lambda r:(r['status'] != 'active', -(r.get('source_turn') or 0), r['id']))[:64])
    current['conditions'] = [deepcopy(c) for c in state.get('conditions',{}).values()
        if c['actor_id'] in relevant and c['status'] in ('active','unknown_outcome')]
    for cid, actor in current['characters'].items():
        if extraction or cid not in scope.referenced_actor_ids:
            projected = capabilities(state,cid)
            if state['characters'][cid].get('life_status','unknown') != 'unknown' or state['characters'][cid].get('developmental_stage','unknown') != 'unknown' or any(not projected[k] for k in ('conscious','can_perceive','can_act','can_speak','can_move')):
                actor['capability_projection'] = projected
            # Unknown defaults are not facts and do not earn per-turn prompt space.
            actor.pop('capabilities',None)
            for field in ('life_fact_id','parentage_complete_fact_id','display_name'):
                if actor.get(field) is None: actor.pop(field,None)
            for field in ('life_status','developmental_stage'):
                if actor.get(field)=='unknown': actor.pop(field,None)
        # Identity history belongs in targeted history queries, not every prompt.
        actor.pop('name_history',None)
    from backend.runtime_v3.kinship import visible_relations
    current['social_knowledge'] = {cid:visible_relations(state,cid) for cid in sorted(
        scope.present_actor_ids | scope.remote_actor_ids | scope.active_actor_ids)}
    for cid in current['social_knowledge']:
        current['social_knowledge'][cid] = [r for r in current['social_knowledge'][cid]
            if {r['source_id'],r['target_id']} & relevant][:64]
    from backend.runtime_v3.residence import visible_social_state
    social = {section:[{k:v for k,v in state[section][rid].items()
        if k not in ('evidence','source_turn','closure_fact_id','name_history')} for rid in ids]
        for section,ids in (('residences',scope.residence_ids),('roles',scope.role_ids),
                            ('organizations',scope.organization_ids))}
    # Do not spend tokens on empty defaults in existing saves.
    current.update({key:rows for key,rows in social.items() if rows})
    established = {r['actor_id'] for section in ('residences','roles')
        for r in state.get(section,{}).values() if r['actor_id'] in relevant}
    if established:
        current['social_status'] = {cid:{section:[r['id'] for r in social[section] if r['actor_id']==cid]
            for section in ('residences','roles')} for cid in sorted(established)}
        current['residence_role_knowledge'] = {cid:visible_social_state(state,cid,relevant)
            for cid in sorted(scope.present_actor_ids | scope.remote_actor_ids | scope.active_actor_ids)}
        for projection in current['residence_role_knowledge'].values():
            for section, rows in projection.items():
                active = [r for r in rows if r['status']=='active']
                closed = sorted((r for r in rows if r['status']=='closed'),key=lambda r:r['until'] or 0,reverse=True)
                projection[section] = active + closed[:8]
    # Targeted old phases remain lower priority than current truth.
    from backend.runtime_v3.scope import words
    old_phases = [dict(r, section=section) for section in ('residences','roles')
        for r in state.get(section,{}).values() if r['actor_id'] in relevant and r['status']=='closed'
        and words(query) & words(' '.join(str(r.get(k,'')) for k in ('title','context','outcome','id')))]
    if old_phases: current['social_history'] = sorted(old_phases,key=lambda r:r['until'] or 0,reverse=True)[:8]
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
        snapshot = deepcopy(snapshot)
        for card in snapshot['character_cards']:
            card['name'] = snapshot['world_state']['characters'][card['id']].get('display_name') or card['name']
        from backend.runtime_v3.director import plan
        state = snapshot['world_state']; campaign = snapshot.get('campaign', {})
        prompt_name = 'background_prompt.md' if kind == 'background' else 'game_system_prompt.md'
        rules = (prompts or {}).get(prompt_name, {}).get('content') or (PROMPTS/prompt_name).read_text(encoding='utf-8')
        rules += '\n' + NARRATIVE_CONTRACT
        cards, index, behavioral = [], [], []
        classifier = CharacterContextClassifier()
        for card in snapshot['character_cards']:
            mode = classifier.classify(card['id'], scope)
            if mode in (FULL_PRESENT, FULL_REMOTE):
                card = deepcopy(card)
                actor = state['characters'][card['id']]
                age = age_on(actor.get('birth_date'),current_time(state)['date'],profile_of(state))
                if age is not None: card['fields']['Возраст'] = str(age)
                cards.append(dict(card, context_mode=mode))
            elif mode == ACTIVE_REFERENCED:
                fields = card.get('fields', {})
                behavioral.append(dict(id=card['id'], name=card['name'], context_mode=mode,
                    role=fields.get('Роль', card.get('role', '')),
                    personality=fields.get('Характер', card.get('personality', '')),
                    communication_style=fields.get('Стиль общения', card.get('communication_style', '')),
                    habits=fields.get('Привычки', '')[:500]))
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
                    block('Поведенческие профили / GM-only', behavioral),
                    block('Индекс персонажей', index),
                    block('Знания POV', pov_knowledge(state, scope.controlled_actor_id, current)),
                    block('Знания действующих персонажей / GM-only', actor_knowledge(state, scope, current)),
                    block('Память', dict(strategy='canonical_history', llm_calls=0)),
                    block('Недавняя история / GM-only', scope.history_events),
                    block('Director / GM-only', plan(state, kind, scope=scope))]
        legacy = legacy_knowledge(snapshot, scope)
        if legacy: messages.append(block('Legacy knowledge / GM-only, ownership unknown', legacy))
        # Knowledge rows are projected once into their ownership blocks.
        current_without_knowledge = dict(current, knowledge=[])
        messages[2] = block('Текущее состояние / GM-only', current_without_knowledge)
        # Up to SIX visible scenes; optional previous inputs, never trim prose for a target.
        for view in views:
            messages.extend([dict(role='user', content=view.get('user_text') or 'Продолжить.'),
                             dict(role='assistant', content=view.get('assistant_text', ''))])
        return rules, messages


class ExtractionContextBuilder:
    extraction = True

    def build(self, snapshot, scope, current, views, user_text, kind, prompts, extraction_text):
        snapshot = deepcopy(snapshot)
        for card in snapshot['character_cards']:
            card['name'] = snapshot['world_state']['characters'][card['id']].get('display_name') or card['name']
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
    return [k for k in current['knowledge'] if k['actor_id'] == actor]


def actor_knowledge(state, scope, current):
    active = scope.present_actor_ids | scope.remote_actor_ids | scope.active_actor_ids
    return [k for k in current['knowledge'] if k['actor_id'] in active and k['actor_id'] != scope.controlled_actor_id]


def build_context(snapshot, turns, user_text, kind, context_length, reserve, extraction_text=None,
                  validation_feedback=None, recent_turns=6, prompts=None, world_history=None,
                  target_context_budget=18000):
    from context_builder import estimate
    state = snapshot['world_state']; camera = state['camera']
    all_views = visible_views(snapshot, turns, kind)
    # Respect an explicit smaller user setting, but never exceed six narrative turns.
    views = all_views[-min(6, max(0, recent_turns)):] if recent_turns else []
    scope = RelevanceResolver().resolve(snapshot, user_text, all_views[-3:], world_history, extraction_text)
    current = canonical_slice(state, scope, extraction_text is not None, user_text+'\n'+(extraction_text or ''))
    from backend.runtime_v3.milestones import select_context
    milestones = select_context(state, scope, (world_history or {}).get('_milestone_query'))
    if milestones: current['milestones'] = list(milestones)
    if snapshot.get('_time_skip'):
        current['time_skip_target'] = current_time(state,snapshot['_time_skip']['actual_target'])
    builder = ExtractionContextBuilder() if extraction_text is not None else NarrativeContextBuilder()
    rules, messages = builder.build(snapshot, scope, current, views, user_text, kind, prompts, extraction_text)
    rules += '\n' + TIME_CONTRACT
    rules += ('\nMilestones — исторический GM-only индекс принятых переходов, не текущее состояние и не знание персонажей. '
              'Текущий canonical WorldState имеет приоритет над Milestones, History и старой биографией. '
              'known_by ограничивает доступ действующих персонажей к milestone; остальные не знают его автоматически. '
              'Исторический брак/роль/дом не означает, что они активны сейчас; исторические имена не заменяют текущие.')
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

    selected = {key: len(current[key]) for key in ('locations', 'facts', 'knowledge', 'relationships', 'threads', 'scheduled_events')}
    selected_history = list(scope.history_events)
    def refresh_current():
        replace_block('Текущее состояние / GM-only', current if builder.extraction else dict(current, knowledge=[]))
        if not builder.extraction:
            replace_block('Знания POV', pov_knowledge(state, scope.controlled_actor_id, current))
            replace_block('Знания действующих персонажей / GM-only', actor_knowledge(state, scope, current))

    if estimate(messages) > target and 'social_history' in current:
        current.pop('social_history')
        refresh_current()
    while estimate(messages) > target and current.get('milestones'):
        current['milestones'].pop()
        refresh_current()
    if estimate(messages) > target and current.get('residence_role_knowledge'):
        for projection in current['residence_role_knowledge'].values():
            for section, rows in projection.items():
                projection[section] = [r for r in rows if r['status']=='active']
        refresh_current()
    # Weak semantic-only actor candidates go before facts or behavioral identity.
    if not builder.extraction and estimate(messages) > target:
        title = 'Карточки присутствующих / GM-only'
        card_message = next(m for m in messages if m['content'].startswith(title+'\n'))
        cards = json.loads(card_message['content'].split('\n', 1)[1])
        weak = sorted(scope.referenced_actor_ids - scope.structural_actor_ids,
                      key=lambda cid: (scope.actor_scores.get(cid, 0), cid))
        for cid in weak:
            if estimate(messages) <= target: break
            cards = [c for c in cards if c['id'] != cid]
            current['characters'].pop(cid, None)
            current['relationships'] = [r for r in current['relationships'] if cid not in (r['source_id'], r['target_id'])]
            replace_block(title, cards)
            refresh_current()

    # Soft pressure removes supporting content, never the cheap identity index.
    optional = sorted((fid for fid in scope.fact_ids if scope.fact_scores[fid] < 100),
                      key=lambda fid: (scope.fact_scores[fid], fid))
    for fid in optional:
        if estimate(messages) <= target: break
        del current['facts'][fid]
        current['knowledge'] = [k for k in current['knowledge'] if k['fact_id'] != fid]
        refresh_current()
    if not builder.extraction:
        for event in list(scope.history_events):
            if estimate(messages) <= target: break
            turn_id = event.get('turn_id')
            if type(turn_id) is int and state['meta']['turn_id'] - turn_id < 3: continue
            scope.history_events.remove(event)
            replace_block('Недавняя история / GM-only', scope.history_events)
        if estimate(messages) > target:
            replace_block('Legacy knowledge / GM-only, ownership unknown', [])
        # Only hard pressure can discard optional INDEX. Behavioral identity,
        # ownership boundaries and all six visible scenes remain mandatory.
        if estimate(messages) > hard_context_limit:
            replace_block('Индекс персонажей', [])
    if estimate(messages) > hard_context_limit:
        raise ValueError('Контекст v3 не помещается в выбранную модель. Увеличь контекст или уменьши лимит ответа. Критические данные сцены и последние narrative сохранены.')
    classifier = CharacterContextClassifier()
    counts = {mode: 0 for mode in (FULL_PRESENT, FULL_REMOTE, ACTIVE_REFERENCED, COMPACT_REFERENCED, INDEX)}
    for cid in state['characters']: counts[classifier.classify(cid, scope)] += 1
    sections = {key: dict(selected=selected[key], included=len(current[key]), total=len(state[key]))
                for key in ('locations', 'facts', 'knowledge', 'relationships', 'threads', 'scheduled_events')}
    sections['history_events'] = dict(selected=0 if builder.extraction else len(selected_history), included=0 if builder.extraction else len(scope.history_events), total=len((world_history or {}).get('events', [])))
    sections['milestones'] = dict(selected=len(milestones), included=len(current.get('milestones', [])))
    def contents(title):
        return next((json.loads(m['content'].split('\n', 1)[1]) for m in messages if m['content'].startswith(title+'\n')), [])
    included_actors = (set(current['characters']) if builder.extraction else
        {c['id'] for title in ('Карточки присутствующих / GM-only', 'Поведенческие профили / GM-only', 'Индекс персонажей') for c in contents(title)})
    included_counts = {mode: sum(classifier.classify(cid, scope) == mode for cid in included_actors) for mode in counts}
    selected_ids = dict(characters=set(state['characters']), locations=set(scope.location_ids), facts=set(scope.fact_ids),
        threads=set(scope.thread_ids), scheduled_events=set(scope.scheduled_event_ids), knowledge=set(scope.knowledge_ids),
        relationships=set(scope.relationship_pairs), history_events={e.get('id') for e in selected_history})
    included_ids = dict(characters=included_actors, locations=set(current['locations']), facts=set(current['facts']),
        threads={r['id'] for r in current['threads']}, scheduled_events={r['id'] for r in current['scheduled_events']},
        knowledge={r['actor_id']+':'+r['fact_id'] for r in current['knowledge']},
        relationships={r['source_id']+':'+r['target_id'] for r in current['relationships']},
        history_events=set() if builder.extraction else {e.get('id') for e in scope.history_events})
    entities = []
    for entity_kind in selected_ids:
        candidates = selected_ids[entity_kind] | {eid for t, eid in scope.semantic_scores if t == entity_kind}
        for eid in sorted(candidates):
            entities.append(dict(entity_type=entity_kind, entity_id=eid,
                semantic_similarity=scope.semantic_scores.get((entity_kind, eid)),
                selection_reasons=sorted(scope.selection_reasons.get((entity_kind, eid), {'INDEX'} if entity_kind == 'characters' else set())),
                selected=eid in selected_ids[entity_kind], included=eid in included_ids[entity_kind]))
    knowledge_counts = {'selected': selected['knowledge'], 'POV': sum(k['actor_id'] == scope.controlled_actor_id for k in current['knowledge'])}
    for mode in (FULL_PRESENT, FULL_REMOTE, ACTIVE_REFERENCED):
        knowledge_counts[mode] = sum(k['actor_id'] != scope.controlled_actor_id and classifier.classify(k['actor_id'], scope) == mode for k in current['knowledge'])
    diagnostics = dict(mode=('World Simulation ' if kind == 'background' else '') + ('Extraction' if builder.extraction else 'Narrative'),
        characters=counts, character_included=included_counts, knowledge=knowledge_counts,
        semantic=scope.semantic_diagnostics, entities=entities, character_total=len(state['characters']), sections=sections,
        narrative_continuity=0 if builder.extraction else len(views), previous_player_inputs=0 if builder.extraction else len(views),
        target_context_budget=target, hard_context_limit=hard_context_limit, target_exceeded=estimate(messages)>target)
    return ContextMessages(messages, diagnostics)
