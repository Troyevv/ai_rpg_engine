from backend.runtime_v3.weather import weather_at
from backend.runtime_v3.models import identity
"""Scene-first Narrative and Extraction projections of one canonical world."""
from backend.runtime_v3.birth_identity import is_game_birth
from backend.runtime_v3.knowledge import context_rows
from copy import deepcopy
from pathlib import Path
import json
from backend.runtime_v3.scope import RelevanceResolver, CharacterContextClassifier, FULL_PRESENT, FULL_OBSERVED, FULL_REMOTE, ACTIVE_REFERENCED, COMPACT_REFERENCED, INDEX
from backend.runtime_v3.context_contract import EXTRACTION_CONTRACT, NARRATIVE_CONTRACT, TIME_CONTRACT, REMOTE_EXTRACTION_CONTRACT, REMOTE_NARRATIVE_CONTRACT
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
    actor = snapshot['world_state']['camera'].get('pov_actor_id') or snapshot['world_state']['camera']['controlled_actor_id']
    main = snapshot.get('campaign', {}).get('protagonist_id')
    return [t if kind == 'background' and actor is None else actor_view(t, actor, main) for t in turns if t.get('kind') != 'communication'
            if kind == 'background' and actor is None or visible(t, actor, main)]


def canonical_slice(state, scope, extraction=False, query=""):
    current = dict(meta={k:v for k,v in state['meta'].items() if k not in ('genre','weather','calendar','current_protagonist_id','protagonist_required','protagonist_periods','narrative_pacing','narrative_risk','outcome_preference','pacing_recent','communication','interaction_focus')},
        weather=weather_at(state),
        current_time=current_time(state), calendar_context=nearby_calendar(state, scope.relevant_actor_ids), camera=deepcopy(state['camera']),
        locations={lid: deepcopy(state['locations'][lid]) for lid in scope.location_ids},
        characters={cid: deepcopy(state['characters'][cid]) for cid in sorted(scope.relevant_actor_ids)},
        facts={fid: state['facts'][fid] for fid in scope.fact_ids},
        knowledge=context_rows(state, scope.knowledge_ids, extraction=extraction),
        relationships=[state['relationships'][key] for key in scope.relationship_pairs],
        threads=[state['threads'][tid] for tid in scope.thread_ids],
        scheduled_events=[commitment_view(state,state['scheduled_events'][eid]) for eid in scope.scheduled_event_ids])
    for field in ('subject_id','pov_actor_id'):
        if current['camera'].get(field) in (None,scope.controlled_actor_id): current['camera'].pop(field,None)
    from backend.runtime_v3.pacing import NarrativeDeathPolicy
    protected = [cid for cid in current['characters'] if not NarrativeDeathPolicy().permits_autonomous_death(state,cid)]
    if protected: current['death_protected_actor_ids'] = protected
    from backend.runtime_v3.possessions import context_possessions
    possessions = context_possessions(state, scope, extraction=extraction, query=query)
    if possessions: current['possessions'] = possessions
    development_ids = sorted(scope.relevant_actor_ids, key=lambda cid:(
        cid != scope.controlled_actor_id, cid not in scope.present_actor_ids,
        cid not in scope.remote_actor_ids, -scope.actor_scores.get(cid,0), cid))[:8]
    for character in current['characters'].values():
        character.pop('portraits', None)
        from backend.runtime_v3.appearance import context_profile as appearance_context
        character['appearance']=appearance_context(state,character['id'],observer=scope.pov_actor_id or scope.controlled_actor_id,omniscient=extraction,known_actor_ids=scope.relevant_actor_ids)
        if character['appearance'] is None: character.pop('appearance')
        character['age'] = age_on(character.get('birth_date'), current['current_time']['date'], profile_of(state))
        from backend.runtime_v3.personality import context_profile
        profile = context_profile(character, evaluation=extraction)
        character.pop('personality', None)
        if extraction and profile and character['id'] in development_ids:
            character['personality'] = profile
        from backend.runtime_v3.lifecycle import context_records
        from backend.runtime_v3.values import context_values
        values = context_values(character, evaluation=extraction)
        character.pop('values', None)
        if values and (not extraction or character['id'] in development_ids): character['values'] = values
        for key in ('goals', 'intentions', 'obligations'):
            from backend.runtime_v3.remote import authored_record_visible
            records=character[key] if extraction else [r for r in character[key] if authored_record_visible(state,r,scope.pov_actor_id or scope.controlled_actor_id)]
            character[key] = context_records(records, evaluation=extraction, turn=state['meta']['turn_id'])
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
    from backend.runtime_v3.reproduction import context_projection, private_fact_ids, known_birth
    current.update(context_projection(state, relevant, scope.pov_actor_id or scope.controlled_actor_id, extraction))
    if current.get('social_knowledge'):
        # Reuse canonical relation IDs instead of repeating every full edge for
        # each parent. Current objective edges stay authoritative; certainty and
        # perceived phase remain observer-specific (including outdated beliefs).
        relation_ids = {row['id'] for row in current['objective_relations']}
        current['social_knowledge']={cid:[{k:row[k] for k in ('id','certainty','status','outcome')}
            if row['id'] in relation_ids else row for row in rows]
            for cid,rows in current['social_knowledge'].items()}
        current['objective_relations']=[{k:v for k,v in row.items()
            if k not in ('evidence','source_turn') and v not in (None,'')} for row in current['objective_relations']]
    # Even GM-labelled Narrative blocks cannot reveal these hidden outcomes.
    if extraction:
        # Atomic reproduction assertions are already represented by the typed
        # process/child/relation projections with their fact IDs. Do not repeat
        # each assertion as prose for every newborn in a multiple birth.
        ids=private_fact_ids(state)
        current['facts']={fid:f for fid,f in current['facts'].items() if fid not in ids}
        compact={}
        for row in current['knowledge']:
            if row['fact_id'] in ids:
                compact.setdefault(row['actor_id'],{})[row['fact_id']]=[row['status'],row.get('revision',0)]
        if compact: current['reproductive_knowledge']=compact
        current['knowledge']=[row for row in current['knowledge'] if row['fact_id'] not in ids]
    if not extraction:
        from backend.runtime_v3.remote import commitment_visible
        current['scheduled_events']=[e for e in current['scheduled_events'] if commitment_visible(state,e,scope.pov_actor_id or scope.controlled_actor_id)]
        hidden_births={cid for cid in current['characters'] if not known_birth(state,cid,scope.pov_actor_id or scope.controlled_actor_id)}
        current['characters']={cid:c for cid,c in current['characters'].items() if cid not in hidden_births}
        current['objective_relations']=[r for r in current['objective_relations'] if not {r['source_id'],r['target_id']}&hidden_births]
        current['relationships']=[r for r in current['relationships'] if not {r['source_id'],r['target_id']}&hidden_births]
        for section in ('threads','scheduled_events'):
            current[section]=[r for r in current[section] if not set(r.get('character_ids',[]))&hidden_births]
        current['camera']['present_character_ids']=[cid for cid in current['camera']['present_character_ids'] if cid not in hidden_births]
        current['camera']['observed_character_ids']=[cid for cid in current['camera'].get('observed_character_ids',[]) if cid not in hidden_births]

        from backend.runtime_v3.possessions import private_fact_ids as possession_facts
        protected = private_fact_ids(state) | possession_facts(state)
        allowed = {k['fact_id'] for k in state['knowledge'].values()
            if k['actor_id']==(scope.pov_actor_id or scope.controlled_actor_id) and k['status']=='known'}
        current['scheduled_events'] = [e for e in current['scheduled_events'] if e['id'] not in state.get('pregnancies',{}) or state['pregnancies'][e['id']]['fact_id'] in allowed]
        possession_beliefs = {k['fact_id'] for k in state['knowledge'].values()
            if k['actor_id']==(scope.pov_actor_id or scope.controlled_actor_id) and k['status']!='unknown'} & possession_facts(state)
        current['facts'] = {k:v for k,v in current['facts'].items() if k not in protected or k in allowed | possession_beliefs}
        current['knowledge'] = [k for k in current['knowledge'] if k['fact_id'] in current['facts']]
    for actor in current['characters'].values():
        actor.pop('birth_date_provenance',None)
        if not extraction and state['characters'][actor['id']].get('name_history') and not is_game_birth(state,actor['id']):
            from backend.runtime_v3.kinship import visible_name
            actor['display_name']=visible_name(state,actor['id'],scope.pov_actor_id or scope.controlled_actor_id,'')
        if not extraction and is_game_birth(state,actor['id']):
            from backend.runtime_v3.reproduction import birth_name
            actor.pop('display_name', None)
            name = birth_name(state, actor['id'], scope.pov_actor_id or scope.controlled_actor_id)
            if name: actor['display_name'] = name
        for key in ('birth_provenance','birth_date_provenance','identity_components','biological_sex','reproductive_capability'):
            if not extraction or not actor.get(key) or actor.get(key)=='unknown': actor.pop(key,None)
        if extraction and current.get('pregnancies'):
            # Empty defaults carry no assertions. Immutable birth provenance is
            # already available through the pregnancy's child/event references.
            actor.pop('birth_provenance', None)
            for key in list(actor):
                if actor[key] in (None, '', [], {}): actor.pop(key)
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
        from backend.runtime_v3.personality import project_card
        snapshot['character_cards'] = [project_card(c, snapshot['world_state']['characters'][c['id']]) for c in snapshot['character_cards']]
        from backend.runtime_v3.appearance import project_card as appearance_card
        snapshot['character_cards'] = [appearance_card(c, snapshot['world_state'], scope.pov_actor_id or scope.controlled_actor_id, omniscient=self.extraction, bounded=True,known_actor_ids=scope.relevant_actor_ids) for c in snapshot['character_cards']]
        for card in snapshot['character_cards']:
            card['name'] = snapshot['world_state']['characters'][card['id']].get('display_name') or card['name']
        from backend.runtime_v3.reproduction import known_birth, birth_name
        if kind != 'background' or scope.pov_actor_id:
            state=snapshot['world_state']; observer=state['camera'].get('pov_actor_id') or state['camera']['controlled_actor_id']
            snapshot['character_cards']=[c for c in snapshot['character_cards'] if known_birth(state,c['id'],observer)]
            from backend.runtime_v3.kinship import visible_name
            for card in snapshot['character_cards']:
                card['name']=visible_name(state,card['id'],observer,card['name'])
        from backend.runtime_v3.director import plan
        state = snapshot['world_state']; campaign = snapshot.get('campaign', {})
        prompt_name = 'background_prompt.md' if kind == 'background' else 'game_system_prompt.md'
        rules = (prompts or {}).get(prompt_name, {}).get('content') or (PROMPTS/prompt_name).read_text(encoding='utf-8')
        rules += '\n' + NARRATIVE_CONTRACT
        if current.get('communication'): rules += REMOTE_NARRATIVE_CONTRACT
        cards, index, behavioral = [], [], []
        classifier = CharacterContextClassifier()
        for card in snapshot['character_cards']:
            mode = classifier.classify(card['id'], scope)
            if mode in (FULL_PRESENT, FULL_OBSERVED, FULL_REMOTE):
                card = deepcopy(card)
                actor = state['characters'][card['id']]
                age = age_on(actor.get('birth_date'),current_time(state)['date'],profile_of(state))
                if age is not None: card['fields']['Возраст'] = str(age)
                # These fields are supplied once by the bounded canonical slice.
                for field in ('Чего хочет','Намерения','Обязательства','Ценности','Приоритеты'):
                    card['fields'].pop(field,None)
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
        for card in cards: card.pop('is_player',None)
        messages = [block('Кампания / GM-only', dict(campaign={k:v for k,v in campaign.get('campaign', {}).items() if k != 'genre'},
                    story_notes=campaign.get('story_notes', ''), tone=campaign.get('sections', {}).get('tone', ''))),
                    block('ContextScope / GM-only', scope.summary()),
                    block('Текущее состояние / GM-only', current),
                    block('Карточки присутствующих / GM-only', cards),
                    block('Поведенческие профили / GM-only', behavioral),
                    block('Индекс персонажей', index),
                    block('Знания POV', pov_knowledge(state, state['camera'].get('pov_actor_id') or scope.controlled_actor_id, current)),
                    block('Знания действующих персонажей / GM-only', actor_knowledge(state, scope, current)),
                    block('Память', dict(strategy='canonical_history', llm_calls=0)),
                    block('Недавняя история / GM-only', scope.history_events),
                    block('Director / GM-only', plan(state, kind, scope=scope))]
        from backend.runtime_v3.genre import guidance
        genre = guidance(state['meta'].get('genre'))
        if genre: messages.append(block('Genre / soft creative guidance', genre))
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


def state_outcome(snapshot):
    return snapshot['world_state']['meta'].get('outcome_preference','natural')


class ExtractionContextBuilder:
    extraction = True

    def build(self, snapshot, scope, current, views, user_text, kind, prompts, extraction_text):
        snapshot = deepcopy(snapshot)
        from backend.runtime_v3.personality import project_card
        snapshot['character_cards'] = [project_card(c, snapshot['world_state']['characters'][c['id']]) for c in snapshot['character_cards']]
        from backend.runtime_v3.appearance import project_card as appearance_card
        snapshot['character_cards'] = [appearance_card(c, snapshot['world_state'], scope.pov_actor_id or scope.controlled_actor_id, omniscient=self.extraction, bounded=True,known_actor_ids=scope.relevant_actor_ids) for c in snapshot['character_cards']]
        for card in snapshot['character_cards']:
            card['name'] = snapshot['world_state']['characters'][card['id']].get('display_name') or card['name']
        default = (PROMPTS/'state_update_prompt.md').read_text(encoding='utf-8')
        saved = (prompts or {}).get('state_update_prompt.md', {}).get('content')
        # Preserve user overrides, but do not send the bundled generic contract twice.
        rules = (saved + '\n' if saved and saved.strip() != default.strip() else '') + EXTRACTION_CONTRACT
        from backend.services.private_artifacts import enabled as historical_enabled
        historical = historical_enabled(snapshot['world_state'])
        if current.get('communication'): rules += REMOTE_EXTRACTION_CONTRACT
        if historical:
            from backend.runtime_v3.context_contract import HISTORICAL_EXTRACTION_CONTRACT
            rules += HISTORICAL_EXTRACTION_CONTRACT
        if current.get('relationship_evidence'):
            from backend.runtime_v3.context_contract import RELATIONSHIP_EVIDENCE_CONTRACT
            rules += RELATIONSHIP_EVIDENCE_CONTRACT
        reproductive = bool(current.get('pregnancies')) or any(
            c.get('reproductive_capability','unknown')!='unknown' or is_game_birth(snapshot['world_state'],c['id'])
            for c in current['characters'].values())
        if reproductive:
            from backend.runtime_v3.context_contract import REPRODUCTION_CONTRACT
            rules += REPRODUCTION_CONTRACT
        # Affected IDs and canonical runtime, plus a bounded actor-owned choice
        # projection. No other actors' card prose or old narratives are needed.
        # Include physical/emotion baseline also for referenced actors affected in completed text.
        for cid in current['characters']:
            for key in ('physical_state', 'emotion'):
                current['characters'][cid][key] = snapshot['world_state']['characters'][cid][key]
        return rules, [block('Текущее состояние / GM-only', current),
                       block('Choice context / controlled actor', choice_context(snapshot, scope, current, views, kind)),
                       block('Entity IDs', [dict(id=c['id'], name=c['name'], aliases=c.get('aliases', []))
                            for c in snapshot['character_cards'] if c['id'] in scope.relevant_actor_ids]),
                       block('JSON Schema', prompt_schema(historical=historical, elapsed_required=kind=='turn' and not snapshot.get('_time_skip'), relationship_evidence=bool(current.get('relationship_evidence')), communication=bool(current.get('communication')), voice=bool(current.get('communication',{}).get('active_call')), reproduction=reproductive, births=any(p['status']!='born' for p in current.get('pregnancies',[])), favorable_paths=state_outcome(snapshot)=='guaranteed_happy_path'))]


def choice_context(snapshot, scope, current, views, kind):
    """Read-only projection inside the existing builder, never a personality store.

    Extraction also needs GM truth to resolve this turn. This separately labelled
    block is the permitted *personalization* source, not a grant of that GM knowledge.
    Reuse ContextScope's retrieval/budget and #67/#75 projections; do not retrieve
    another history or infer personality from clicks/unselected suggestions.
    """
    from backend.runtime_v3.life import capabilities
    from backend.runtime_v3.personality import context_profile, CARD_FIELDS
    from backend.runtime_v3.lifecycle import context_records
    from backend.runtime_v3.values import context_values
    state = snapshot['world_state']; cid = scope.controlled_actor_id
    if kind == 'background' or state['camera']['mode'] == 'observer' or not cid:
        return dict(enabled=False)
    actor = state['characters'][cid]; ability = capabilities(state, cid)
    if not ability['can_act']:
        return dict(enabled=False, actor_id=cid)
    profile = context_profile(actor)
    # Legacy absence only: an intentionally empty/retired canonical profile must
    # never be repopulated from the original card.
    if profile is None:
        card = next((c for c in snapshot['character_cards'] if c['id'] == cid), {})
        profile = dict(items={field:dict(field=field, text=card.get('fields', {}).get(label, '')[:600])
            for field, label in CARD_FIELDS.items() if card.get('fields', {}).get(label, '').strip()})
    main = snapshot.get('campaign', {}).get('protagonist_id')
    recent = []
    for view in views:
        if (view.get('kind', 'turn') == 'turn' and (view.get('pov_actor_id') or main) == cid
                and view.get('user_text', '').strip()):
            text = view['user_text']
            recent.append(dict(sequence=view.get('sequence'), player_input=text[:800], truncated=len(text)>800))
    participants = scope.present_actor_ids | scope.observed_actor_ids | scope.remote_actor_ids
    from backend.runtime_v3.reproduction import context_projection
    reproductive=context_projection(state,scope.relevant_actor_ids,cid)
    return deepcopy(dict(enabled=True, actor_id=cid, personality=profile,
        values=context_values(actor), capabilities=ability, **({'reproduction':reproductive} if reproductive else {}),
        **{key:context_records(actor[key]) for key in ('goals','intentions','obligations')},
        relationships=[r for r in current['relationships'] if r['source_id']==cid and r['target_id'] in participants],
        knowledge=[dict(fact_id=k['fact_id'], status=k['status'], text=current['facts'][k['fact_id']]['text'])
            for k in current['knowledge'] if k['actor_id']==cid and k['status'] in ('known','suspected')
            and k['fact_id'] in current['facts']],
        scene=dict(location_id=state['camera']['location_id'], present_actor_ids=sorted(scope.present_actor_ids),
                   observed_actor_ids=sorted(scope.observed_actor_ids), remote_actor_ids=sorted(scope.remote_actor_ids), situation=state['camera']['situation']),
        recent_player_expression=recent))



def compact_choice_context(current, choice):
    """Lossless wire references to identical, already selected values only.

    Never replace an actor-owned projection with a broader GM object. In
    particular, a partial Knowledge/reproduction view must stay partial.
    """
    def encoded(value):
        return json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    candidates = {}
    def index(value, path):
        if isinstance(value, (dict, list, str)) and value:
            key = encoded(value)
            ref = {'state_ref': path}
            if len(encoded(ref).encode('utf-8')) < len(key.encode('utf-8')):
                candidates.setdefault(key, ref)
        if isinstance(value, dict):
            for key, child in value.items():
                index(child, path + '/' + key.replace('~', '~0').replace('/', '~1'))
        elif isinstance(value, list):
            for i, child in enumerate(value):
                index(child, path + '/' + str(i))
    index(current, '')
    def compact(value):
        if isinstance(value, (dict, list, str)):
            ref = candidates.get(encoded(value))
            if ref is not None:
                return deepcopy(ref)
        if isinstance(value, dict):
            return {key: compact(child) for key, child in value.items()}
        if isinstance(value, list):
            return [compact(child) for child in value]
        return value
    return compact(choice)


def pov_knowledge(state, actor, current):
    return [k for k in current['knowledge'] if k['actor_id'] == actor]


def actor_knowledge(state, scope, current):
    active = scope.present_actor_ids | scope.remote_actor_ids | scope.active_actor_ids
    return [k for k in current['knowledge'] if k['actor_id'] in active and k['actor_id'] != scope.controlled_actor_id]


def build_context(snapshot, turns, user_text, kind, context_length, reserve, extraction_text=None,
                  validation_feedback=None, recent_turns=6, prompts=None, world_history=None,
                  target_context_budget=18000, pacing_decision=None, initiative_decision=None, continuity_decision=None):
    from context_builder import estimate
    state = snapshot['world_state']; camera = state['camera']
    if extraction_text is None:
        # Apply the knowledge boundary before relevance/pacing can summarize a
        # private commitment, not just before rendering the final calendar list.
        from backend.runtime_v3.remote import visible_commitments
        observer = camera.get('pov_actor_id') or camera.get('controlled_actor_id')
        state = dict(state, scheduled_events=visible_commitments(state,observer,world_history))
        snapshot = dict(snapshot, world_state=state)
    all_views = visible_views(snapshot, turns, kind)
    # Respect an explicit smaller user setting, but never exceed six narrative turns.
    views = all_views[-min(6, max(0, recent_turns)):] if recent_turns else []
    scope = RelevanceResolver().resolve(snapshot, user_text, all_views[-3:], world_history, extraction_text)
    observer = scope.pov_actor_id or scope.controlled_actor_id
    remote_private = {identity('communicated_text', e['id']) for e in state.get('remote_events', {}).values()
                      if e['channel']!='VOICE_CALL' and observer not in e['read_by'] and observer != e['sender_id']}
    scope.fact_ids = [fid for fid in scope.fact_ids if fid not in remote_private]
    scope.knowledge_ids = [key for key in scope.knowledge_ids if state['knowledge'][key]['fact_id'] not in remote_private]
    from backend.runtime_v3.scope import string_ids
    scope.history_events = [e for e in scope.history_events if not string_ids(e.get('fact_ids', [])) & remote_private]
    if extraction_text is None:
        from backend.runtime_v3.possessions import private_fact_ids as possession_facts, known
        from backend.runtime_v3.scope import string_ids
        protected = possession_facts(state)
        hidden = protected - {fid for fid in protected if known(state, scope.pov_actor_id or scope.controlled_actor_id, fid)}
        observer=scope.pov_actor_id or scope.controlled_actor_id
        scope.history_events = [e for e in scope.history_events if not
            (string_ids(e.get('fact_ids', [])) & hidden) and (observer is None or observer in e.get('witnesses',[]) or all(known(state,observer,fid) for fid in string_ids(e.get('fact_ids',[]))) and bool(string_ids(e.get('fact_ids',[]))))]
    from backend.runtime_v3.pacing import development_sources, evaluate, extraction_policy
    scope.development_sources = development_sources(state, scope, (world_history or {}).get('_milestone_query'), world_history)
    from backend.runtime_v3.continuity import project as continuity_project
    scope.continuity_decision = deepcopy(continuity_decision) if continuity_decision is not None else continuity_project(state, scope, world_history)
    if snapshot.get('_time_skip') or kind == 'background': scope.continuity_decision['compression'] = {'max_minutes':0,'boundary_ids':[]}
    scope.pacing_decision = deepcopy(pacing_decision) if pacing_decision is not None else evaluate(state, scope)
    from backend.runtime_v3.initiative import scene_plan
    scope.initiative_decision = deepcopy(initiative_decision) if initiative_decision is not None else scene_plan(state, scope)
    current = canonical_slice(state, scope, extraction_text is not None, user_text+'\n'+(extraction_text or ''))
    from backend.runtime_v3.remote import context_projection as remote_context
    remote = remote_context(state)
    cfg = state['meta']['communication']
    current['communication_capabilities'] = {key: cfg[key] for key in ('text_message', 'voice_call')}
    # Preserve the legacy context budget: absent/disabled future channels and
    # empty optional metadata do not consume tokens on every ordinary turn.
    current['communication_capabilities'].update({key: True for key in
        ('letter', 'courier', 'telegram', 'landline', 'magic') if cfg.get(key)})
    delivery = {key: value for key,value in cfg.get('delivery_policy', {}).items() if cfg.get(key)}
    if delivery: current['communication_capabilities']['delivery_policy'] = delivery
    if cfg.get('delivery_minutes'): current['communication_capabilities']['delivery_minutes'] = cfg['delivery_minutes']
    if cfg.get('author_note'): current['communication_capabilities']['author_note'] = cfg['author_note']
    if cfg['voice_call']:
        current['communication_capabilities']['ring_timeout_minutes'] = cfg['ring_timeout_minutes']
    if remote:
        remote['input_channel'] = snapshot.get('_interaction_input_channel', state['meta']['interaction_focus'])
        current['communication'] = remote
        if remote.get('active_call'):
            from backend.runtime_v3.call_continuity import CONTRACT, sources as call_sources
            remote['constraints'] += '\n' + CONTRACT
            if extraction_text is not None:
                remote['call_sources']=list(call_sources(state,world_history,extraction_text,user_text,snapshot.get('_resolver_turn_id',state['meta']['turn_id']+1)).values())
        if extraction_text is not None and snapshot.get('_remote_batch'):
            from backend.runtime_v3.remote_semantics import staged_sources
            sources=staged_sources(snapshot)
            if sources:
                remote['accepted_semantic_messages']=list(sources.values())
                remote['constraints'] += (' Extract consequences of these accepted messages into scheduled_event_changes and explicit intentions_updates. '
                    'A proposal requires actual assent; cite remote_source_ids and remote_time_source_id. Unread confirmation can establish GM truth, never recipient Knowledge. '
                    'Keep original authored wording and source_event_id for intentions. Relative minute_offset is anchored to the original proposal, not this turn. ')

    if kind == 'background' and not camera.get('pov_actor_id'):
        from backend.runtime_v3.reproduction import context_projection
        current.update(context_projection(state,scope.relevant_actor_ids,None,extraction=True))
        from backend.runtime_v3.possessions import context_possessions
        possessions = context_possessions(state,scope,extraction=True,query=user_text)
        if possessions: current['possessions'] = possessions
    from backend.runtime_v3.milestones import select_context
    milestones = select_context(state, scope, (world_history or {}).get('_milestone_query'))
    if extraction_text is None:
        from backend.runtime_v3.possessions import known
        milestones = [m for m in milestones if not m['category'].startswith('possession_') or known(state, scope.pov_actor_id or scope.controlled_actor_id, m.get('fact_id'))]
    if milestones: current['milestones'] = list(milestones)
    if extraction_text is not None:
        # Reuse the bounded ContextScope history; never expose a new global feed.
        from backend.runtime_v3.relationships import interaction_event
        pairs = [(r['source_id'], r['target_id']) for r in current['relationships']]
        pairs += [(a, b) for a in current['characters'] for b in current['characters'] if a != b]
        evidence = [e for e in scope.history_events if isinstance(e.get('id'), str)
                    and type(e.get('turn_id')) is int and isinstance(e.get('text'), str)
                    and any(interaction_event(e, a, b) for a, b in pairs)]
        if evidence:
            current['relationship_evidence'] = [dict(id=e['id'], participants=e['participants'],
                turn_id=e['turn_id'], text=e['text'][:600]) for e in evidence[-8:]]
        current['continuity'] = {key: value for key, value in scope.continuity_decision.items()
                                 if key not in ('pressure', 'ordinary_scene_valid', 'extra_llm_calls')}
        current['narrative_policy'] = extraction_policy(scope.pacing_decision)
        current['scene_agency'] = {k:v for k,v in scope.initiative_decision.items() if k not in ('optional','extra_llm_calls')}
        if 'actors' in current['scene_agency']:
            current['scene_agency']['actors'] = [{k:v for k,v in actor.items() if k != 'capabilities'} for actor in scope.initiative_decision['actors']]
    from backend.runtime_v3.personality import historical_context, visible_item
    development = historical_context(state,scope,world_history)
    if development: current['personality_history'] = development
    from backend.runtime_v3.lifecycle import historical_context as motivation_history
    lifecycle_history=motivation_history(scope,world_history)
    if lifecycle_history: current['motivation_history']=lifecycle_history
    value_access={cid:{key:[observer for observer in scope.relevant_actor_ids
        if visible_item(state,cid,item,observer)] for key,item in (state['characters'][cid].get('values') or {}).items()
        if item['status']=='active' and key in current['characters'].get(cid,{}).get('values',{})}
        for cid in current['characters'] if current['characters'][cid].get('values')}
    if value_access: current['values_known_by']=value_access
    access = {}
    for cid in sorted(scope.relevant_actor_ids)[:8]:
        profile = state['characters'][cid].get('personality')
        if profile:
            rows = {key:[other for other in scope.relevant_actor_ids if visible_item(state,cid,item,other)]
                    for key,item in profile['items'].items() if item.get('source_ids')}
            if rows: access[cid]=rows
    if access: current['personality_known_by'] = access
    if snapshot.get('_time_skip'):
        current['time_skip_target'] = current_time(state,snapshot['_time_skip']['actual_target'])
    builder = ExtractionContextBuilder() if extraction_text is not None else NarrativeContextBuilder()
    rules, messages = builder.build(snapshot, scope, current, views, user_text, kind, prompts, extraction_text)
    from backend.runtime_v3.context_contract import CONTROL_CONTRACT
    from backend.runtime_v3.context_contract import EXTRACTION_TIME_CONTRACT
    rules += '\n' + (EXTRACTION_TIME_CONTRACT if builder.extraction else TIME_CONTRACT)
    rules += '\n' + (CONTROL_CONTRACT if extraction_text is None else 'death_protected_actor_ids: reject autonomous death.')
    rules += ('\nWorldState overrides historical Milestones/History/biography (roles, relations, homes, names). '
              'Milestones grant no Knowledge; known_by limits actor access.')
    if not builder.extraction: rules += f'\nRuntime v3. controlled_actor_id={camera["controlled_actor_id"]}; mode={camera["mode"]}; world_time={state["meta"]["world_time"]} минут.'
    if current.get('weather'): rules += '\nWeather is canonical environmental context, not an instruction to mention it each turn. Do not invent contradictory weather, force actions or move characters because of it.'
    if snapshot.get('_time_skip'): rules += '\nДетерминированный Time Skip: ' + json.dumps(snapshot['_time_skip'], ensure_ascii=False) + '. Описывай только до actual_target, не позже. Hidden не становится знанием игрока.'
    if validation_feedback: rules += '\nИсправь структурную ошибку, верни полный JSON:\n' + validation_feedback
    from backend.services.world_creation_settings import presentation_rule
    rules += presentation_rule(state['meta'].get('npc_expressiveness','realistic'))
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
        if builder.extraction:
            replace_block('Choice context / controlled actor', choice_context(snapshot, scope, current, views, kind))
        else:
            replace_block('Знания POV', pov_knowledge(state, state['camera'].get('pov_actor_id') or scope.controlled_actor_id, current))
            replace_block('Знания действующих персонажей / GM-only', actor_knowledge(state, scope, current))

    if builder.extraction and estimate(messages) > target:
        def compact_empty_metadata(value):
            if isinstance(value, dict):
                return {k:compact_empty_metadata(v) for k,v in value.items()
                        if (v is not None or k in ('parent_id','location_id','controlled_actor_id','pov_actor_id')) and not (k in ('evidence','source_ids','witnesses','fact_ids',
                            'identity_components','appearance_history','stakes_for','applied','history',
                            'name_history','legacy_text') and v in ('',[],{}))}
            if isinstance(value,list): return [compact_empty_metadata(v) for v in value]
            return value
        current = {k:(v if k in ('meta','camera','current_time','time_skip_target','locations')
                      else compact_empty_metadata(v)) for k,v in current.items()}
        refresh_current()
    if builder.extraction and estimate(messages) > target:
        # Unclassified import prose is optional; never trim current structured traits.
        for actor in current['characters'].values():
            appearance=actor.get('appearance')
            if appearance and appearance.get('legacy_text'):
                appearance.pop('legacy_text')
                appearance['unclassified_legacy_omitted']=True
        refresh_current()
    if builder.extraction and estimate(messages) > target:
        # Development evaluation is optional and already limited to eight actors.
        # Under pressure reduce that set; current appearance/scene are never dropped.
        candidates=sorted(current['characters'],key=lambda cid:(cid in scope.present_actor_ids,cid==scope.controlled_actor_id,cid))
        for cid in candidates:
            if estimate(messages) <= hard_context_limit: break
            actor=current['characters'][cid]
            if actor.get('personality') and not actor['personality'].get('evidence'):
                actor.pop('personality')
                refresh_current()
    while estimate(messages) > target and len(current.get('relationship_evidence', [])) > 1:
        current['relationship_evidence'].pop(0)
        refresh_current()
    if estimate(messages) > hard_context_limit and current.get('relationship_evidence'):
        current.pop('relationship_evidence')
        refresh_current()
    if estimate(messages) > target and 'social_history' in current:
        current.pop('social_history')
        refresh_current()
    if estimate(messages) > target and current.get('motivation_history'):
        current.pop('motivation_history'); refresh_current()
    while estimate(messages) > target and current.get('personality_history'):
        current['personality_history'].pop()
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

    # Recent phone rows are supporting retrieval, not the active call contract.
    # Keep the newest cue and any active call; old text stays in canonical History.
    communication=current.get('communication')
    if communication:
        recent=communication['recent']
        while estimate(messages)>target and len(recent)>1:
            removable=next((row for row in reversed(recent[1:]) if row['id']!=communication.get('active_call')),None)
            if removable is None: break
            recent.remove(removable)
            refresh_current()

    # Soft pressure removes supporting content, never the cheap identity index.
    optional = sorted((fid for fid in scope.fact_ids if scope.fact_scores[fid] < 100),
                      key=lambda fid: (scope.fact_scores[fid], fid))
    for fid in optional:
        if estimate(messages) <= target: break
        current['facts'].pop(fid, None)
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
    # Under hard pressure remove only redundant calendar presentation. Structured
    # date/time, birthdays, participants and commitments remain intact.
    if builder.extraction and estimate(messages)>hard_context_limit:
        current['current_time'].pop('summary',None)
        for occasion in current.get('calendar_context',[]):
            if occasion.get('kind')=='birthday': occasion.pop('id',None)
        refresh_current()
    if builder.extraction and estimate(messages)>hard_context_limit:
        # Wire-only default elision: empty collections/nulls carry no additional
        # truth. Keep section containers and location topology; the canonical
        # state, source IDs, nonempty evidence and Knowledge remain untouched.
        def nonempty(value):
            if isinstance(value,dict):
                return {k:nonempty(v) for k,v in value.items() if v not in (None,'',[],{}) or k in ('parent_id','location_id','controlled_actor_id','pov_actor_id')}
            if isinstance(value,list): return [nonempty(v) for v in value]
            return value
        # Physical resolution needs canonical names/aliases/topology, not optional
        # scenic descriptions. Elide only in Extraction under hard pressure.
        for place in current['locations'].values():
            place.pop('description', None)
        for key in current:
            if key not in ('meta','camera','current_time','time_skip_target','narrative_policy','scene_agency'):
                current[key]=nonempty(current[key])
        refresh_current()
        # Wire-only compaction of repeated empty defaults also applies to choice
        # personalization and the ID index. Keep enabled=false and all real
        # aliases/knowledge; omission is not permission or new canonical truth.
        replace_block('Choice context / controlled actor', nonempty(choice_context(snapshot, scope, current, views, kind)))
        for message in messages:
            if message['content'].startswith('Entity IDs\n'):
                replace_block('Entity IDs', nonempty(json.loads(message['content'].split('\n', 1)[1])))
                break
    if builder.extraction and estimate(messages) > hard_context_limit and not any(
            actor.get('personality') for actor in current['characters'].values()):
        # Optional personality evaluation was already elided above. Its output
        # schema must not crowd out mandatory scene/continuity validation when
        # there is no supplied baseline to evaluate. No canonical data is lost.
        for message in messages:
            if message['content'].startswith('JSON Schema\n'):
                schema = json.loads(message['content'].split('\n', 1)[1])
                for section in ('development_evidence', 'personality_deltas'):
                    schema['properties'].pop(section, None)
                if not any(actor.get('values') for actor in current['characters'].values()):
                    schema['properties'].pop('value_deltas', None)
                # Shared definitions belonging only to omitted evaluations do
                # not need to remain in the wire schema.
                used = set()
                def references(node):
                    if isinstance(node, dict):
                        ref = node.get('$ref', '').removeprefix('#/$defs/')
                        if ref and ref not in used:
                            used.add(ref)
                            references(schema.get('$defs', {}).get(ref, {}))
                        for value in node.values(): references(value)
                    elif isinstance(node, list):
                        for value in node: references(value)
                references(schema['properties'])
                schema['$defs'] = {key:value for key,value in schema.get('$defs', {}).items() if key in used}
                replace_block('JSON Schema', schema)
                break
    # New phone outcomes are essential; optional Director attribution must not
    # crowd them out of a tight extraction request. The parser/Resolver still
    # accept these annotations, but do not require them to establish an event.
    if builder.extraction and communication and estimate(messages) > hard_context_limit:
        for message in messages:
            if message['content'].startswith('JSON Schema\n'):
                schema = json.loads(message['content'].split('\n', 1)[1])
                for section in ('scene_actions', 'narrative_developments', 'consequences', 'continuity_beats', 'scene_transitions', 'physical_projections'):
                    if estimate(messages) <= hard_context_limit: break
                    schema['properties'].pop(section, None)
                    replace_block('JSON Schema', schema)
                break
    # Possession support is bounded by both its own cap and the request budget.
    # Keep explicitly named objects; omit lower-ranked incidental property first.
    for item in reversed(list(current.get('possessions', []))):
        if estimate(messages) <= hard_context_limit: break
        if item['id'] in scope.required_possession_ids: continue
        current['possessions'].remove(item)
        refresh_current()
    if builder.extraction and estimate(messages) > hard_context_limit:
        # Run after every current-state mutation so pointers address the final
        # wire block, including default elision. No additional context is selected.
        for message in messages:
            if message['content'].startswith('Choice context / controlled actor\n'):
                choice = json.loads(message['content'].split('\n', 1)[1])
                compacted = compact_choice_context(current, choice)
                instruction = ('\nChoice state_ref references Текущее состояние / GM-only; grants no extra knowledge.')
                candidate = block('Choice context / controlled actor', compacted)
                # Account for the reference instruction too: compaction must
                # never make a small context larger.
                if len(candidate['content'].encode('utf-8')) + len(instruction.encode('utf-8')) < len(message['content'].encode('utf-8')):
                    replace_block('Choice context / controlled actor', compacted)
                    messages[0]['content'] = messages[0]['content'].replace(
                        'Постоянные правила\n', 'Постоянные правила' + instruction + '\n', 1)
                break
    if estimate(messages) > hard_context_limit:
        raise ValueError(f'Контекст v3 не помещается в выбранную модель ({estimate(messages)} / {hard_context_limit}). Увеличь контекст или уменьши лимит ответа. Критические данные сцены и последние narrative сохранены.')
    classifier = CharacterContextClassifier()
    counts = {mode: 0 for mode in (FULL_PRESENT, FULL_OBSERVED, FULL_REMOTE, ACTIVE_REFERENCED, COMPACT_REFERENCED, INDEX)}
    for cid in state['characters']: counts[classifier.classify(cid, scope)] += 1
    sections = {key: dict(selected=selected[key], included=len(current[key]), total=len(state[key]))
                for key in ('locations', 'facts', 'knowledge', 'relationships', 'threads', 'scheduled_events')}
    sections['history_events'] = dict(selected=0 if builder.extraction else len(selected_history), included=0 if builder.extraction else len(scope.history_events), total=len((world_history or {}).get('events', [])))
    sections['possessions'] = dict(selected=len(scope.possession_ids), included=len(current.get('possessions', [])), total=len(state.get('possessions', {})))
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
    for mode in (FULL_PRESENT, FULL_OBSERVED, FULL_REMOTE, ACTIVE_REFERENCED):
        knowledge_counts[mode] = sum(k['actor_id'] != scope.controlled_actor_id and classifier.classify(k['actor_id'], scope) == mode for k in current['knowledge'])
    diagnostics = dict(mode=('World Simulation ' if kind == 'background' else '') + ('Extraction' if builder.extraction else 'Narrative'),
        continuity=scope.continuity_decision, initiative=scope.initiative_decision, pacing=scope.pacing_decision, characters=counts, character_included=included_counts, knowledge=knowledge_counts,
        semantic=scope.semantic_diagnostics, entities=entities, character_total=len(state['characters']), sections=sections,
        narrative_continuity=0 if builder.extraction else len(views), previous_player_inputs=0 if builder.extraction else len(views),
        target_context_budget=target, hard_context_limit=hard_context_limit, target_exceeded=estimate(messages)>target)
    if not builder.extraction:
        diagnostics['genre_guidance'] = contents('Genre / soft creative guidance') or None
    if builder.extraction:
        choices = contents('Choice context / controlled actor')
        diagnostics['choice_context'] = dict(enabled=choices['enabled'], actor_id=choices.get('actor_id'),
            recent_inputs=len(choices.get('recent_player_expression', [])), knowledge=len(choices.get('knowledge', [])))
    return ContextMessages(messages, diagnostics)
