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
from backend.runtime_v3.player_actions import EXTRACTION_VERSION
from backend.runtime_v3.calendar import current_time, nearby_calendar, age_on, profile_of, scheduled_time, commitment_view

PROMPTS = Path(__file__).resolve().parents[2] / 'prompts'


def block(name, value):
    return dict(role='user', content=name+'\n'+json.dumps(value, ensure_ascii=False, separators=(',', ':')))


def turn_temporal_state(view, side):
    if isinstance(view.get('temporal_' + side), dict):
        return view['temporal_' + side]
    return json.loads(view.get(side + '_json') or '{}').get('world_state', {})


def scene_time(state, view):
    """Read existing turn snapshots; missing historical time stays unknown."""
    result = {}
    for side, key in (('before', 'start'), ('after', 'end')):
        try:
            saved = turn_temporal_state(view, side)
            minute = saved.get('meta', {}).get('world_time')
            if type(minute) is int:
                result[key] = time_stamp(saved, minute)
        except (ValueError, TypeError, KeyError):
            pass
    return result or {'time': 'unknown'}


def time_stamp(state, minute):
    value = current_time(state, minute)
    return {key: value[key] for key in ('world_time', 'date', 'weekday_name', 'time')}


def project_temporal_context(snapshot, turns, current):
    """Transient observations across a jump are a projection, never a migration.

    Turn snapshots already own the branch and before/after times. Only unchanged
    situations inherited across the last accepted jump are demoted. Later scene
    updates stay current; location, health and other enduring state are untouched.
    """
    state = snapshot['world_state']
    now = state['meta']['world_time']
    later = []
    for view in reversed(turns):
        try:
            changes = json.loads(view.get('changes_json') or '{}')
        except (TypeError, ValueError):
            changes = {}
        if not isinstance(changes, dict):
            changes = {}
        jump = view.get('kind') == 'long_term' or bool(changes.get('time_skip'))
        if not jump:
            later.append(view)
            continue
        try:
            before = turn_temporal_state(view, 'before')
            after = turn_temporal_state(view, 'after')
            start, end = before['meta']['world_time'], after['meta']['world_time']
            if type(start) is not int or type(end) is not int:
                continue
        except (KeyError, TypeError, ValueError):
            continue
        if not start < end <= now:
            continue
        current['last_time_advance'] = dict(start=time_stamp(before, start), end=time_stamp(after, end),
            elapsed_minutes=end-start, elapsed_since_minutes=now-end,
            instruction='Past activity is not current. Do not invent player decisions.')
        stale = {}
        candidates = [('camera', current['camera'], before['camera'], after['camera'])]
        candidates += [(cid, row, before['characters'].get(cid, {}), after['characters'].get(cid, {}))
                       for cid, row in current['characters'].items()]
        for key, row, old, new in candidates:
            situation = row.get('situation')
            if key not in view.get('_refreshed_situations', ()) and situation and situation == old.get('situation') == new.get('situation'):
                stale[key] = situation
        # A subsequent real update refreshes the observation, even if the actor
        # later returned to the same situation. No prose interpretation.
        for following in reversed(later):
            if not stale:
                break
            try:
                prior = turn_temporal_state(following, 'before')
                updated = turn_temporal_state(following, 'after')
            except (ValueError, TypeError, KeyError):
                continue
            for key in list(stale):
                a = prior['camera'] if key == 'camera' else prior['characters'].get(key, {})
                b = updated['camera'] if key == 'camera' else updated['characters'].get(key, {})
                if a.get('situation') != b.get('situation'):
                    del stale[key]
        if stale:
            current['past_situations'] = dict(observed_no_later_than=time_stamp(before, start), situations=stale)
            for key in stale:
                row = current['camera'] if key == 'camera' else current['characters'][key]
                row.pop('situation', None)
        return


class ContextMessages(list):
    """Wire-compatible list; diagnostics do not consume LLM tokens."""
    def __init__(self, messages, selection):
        super().__init__(messages)
        self.selection = selection


def visible_views(snapshot, turns, kind):
    from backend.services.pov import visible, actor_view
    actor = snapshot['world_state']['camera'].get('pov_actor_id') or snapshot['world_state']['camera']['controlled_actor_id']
    main = snapshot.get('campaign', {}).get('protagonist_id')
    observing = snapshot['world_state']['camera']['mode'] == 'observer'
    return [t if kind == 'background' and actor is None else actor_view(t, actor, main, observer=observing) for t in turns if not t.get('_temporal_only') and t.get('kind') != 'communication'
            if kind == 'background' and actor is None or visible(t, actor, main)]


def canonical_slice(state, scope, extraction=False, query=""):
    current = dict(meta={k:v for k,v in state['meta'].items() if k not in ('visual_field_facts','genre','weather','calendar','current_protagonist_id','protagonist_required','protagonist_periods','narrative_pacing','narrative_risk','outcome_preference','pacing_recent','communication','interaction_focus')},
        weather=weather_at(state),
        current_time=current_time(state), calendar_context=nearby_calendar(state, scope.relevant_actor_ids), camera=deepcopy(state['camera']),
        locations={lid: deepcopy(state['locations'][lid]) for lid in scope.location_ids},
        characters={cid: deepcopy(state['characters'][cid]) for cid in sorted(scope.relevant_actor_ids)},
        facts={fid: {k:v for k,v in state['facts'][fid].items() if (state['facts'][fid].get('story_secret') or k not in ('story_secret','secret_subject_ids','secret_keeper_ids','secret_biography_ids','secret_existence')) and (k!='secret_biography_ids' or v) and (k!='origin_remote_event_id' or v is not None)} for fid in scope.fact_ids},
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
        # Presentation metadata belongs to the UI, never to either LLM context.
        for field in ('portraits', 'procedural_portrait', 'portrait_mode'):
            character.pop(field, None)
        from backend.runtime_v3.appearance import context_profile as appearance_context
        character['appearance']=appearance_context(state,character['id'],observer=scope.pov_actor_id or scope.controlled_actor_id,omniscient=extraction,known_actor_ids=scope.relevant_actor_ids)
        if character['appearance'] is None: character.pop('appearance')
        character['age'] = age_on(character.get('birth_date'), character.get('death_date') if character.get('life_status')=='dead' else current['current_time']['date'], profile_of(state))
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
    if not extraction:
        from backend.runtime_v3.kinship import knowledge_status
        observer = scope.pov_actor_id or scope.controlled_actor_id
        protected = private_fact_ids(state)
        # A parent may be relevant while the newborn is unknown and absent
        # from current.characters. Gate both projections by the edge's fact.
        hidden_edges = {rid for rid, row in state['objective_relations'].items()
                        if row.get('fact_id') in protected and knowledge_status(state, observer, row['fact_id']) != 'known'}
        current['objective_relations'] = [r for r in current['objective_relations'] if r['id'] not in hidden_edges]
        for cid, rows in current['social_knowledge'].items():
            current['social_knowledge'][cid] = [r for r in rows if r['id'] not in hidden_edges]
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
    if state['camera']['mode'] == 'actor':
        scene_actors = scope.present_actor_ids | scope.observed_actor_ids | scope.remote_actor_ids | scope.active_actor_ids | {scope.controlled_actor_id}
        for cid, character in current['characters'].items():
            if cid not in scene_actors:
                for key in ('goals', 'intentions', 'obligations', 'emotion', 'situation', 'personality', 'values'):
                    character.pop(key, None)
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

    def __init__(self, contract_version=EXTRACTION_VERSION):
        self.contract_version = contract_version

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
        style_override = None
        if self.contract_version >= 11 and prompts and prompt_name in prompts:
            from backend.repositories.documents import is_builtin_prompt
            if not is_builtin_prompt(prompt_name, rules):
                style_override = rules.replace('Разрешены последствия указанного действия и принятые Runtime непроизвольные последствия.', '')
            rules = (PROMPTS/prompt_name).read_text(encoding='utf-8')
        if self.contract_version < 9:
            rules += '\nВарианты следующего действия создаёт Extraction; не разыгрывай их как уже выбранные.'
        narrative_rules = NARRATIVE_CONTRACT
        if self.contract_version >= 10:
            from backend.runtime_v3.context_contract import LIFE_CONTRACT, RESIDENCE_CONTRACT
            narrative_rules = narrative_rules.replace(LIFE_CONTRACT,
                'Family ties, consent, feelings and individual knowledge are separate. '
                'Respect identity, conditions and capabilities. Never choose for the player. '
                'Death is lasting. No ordinary activity by the dead. Others learn through their own experiences. '
                'A wedding need not follow an engagement. A finished phase remains history.\n')
            narrative_rules = narrative_rules.replace(RESIDENCE_CONTRACT,
                'Distinguish a visit from a permanent move and a second job from a replacement. '
                'Consider established addresses, employers, obligations and the viewpoint. '
                'An unknown address or role does not establish homelessness or unemployment.\n')
        if self.contract_version >= 11:
            narrative_rules = narrative_rules.replace('illness/injury/death need canonical Condition/Life State.',
                'author new events according to established conditions, causality and the selected risk.')
            narrative_rules = narrative_rules.replace('Routine waiting/travel/work may be summarized up to continuity.compression.max_minutes.',
                'Summarize authorized routine time to its narrated endpoint. Unresolved appointments remain plans.')
        rules += '\n' + narrative_rules
        from backend.runtime_v3.player_actions import NARRATIVE_CONTRACT as action_contract, required as agency_required
        if agency_required(snapshot['world_state'], user_text, kind): rules += action_contract
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
                    block('Карточки присутствующих / GM-only', [c for c in cards if c['context_mode']==FULL_PRESENT]),
                    block('Поведенческие профили / GM-only', behavioral),
                    block('Индекс персонажей', index),
                    block('Знания POV', pov_knowledge(state, state['camera'].get('pov_actor_id') or scope.controlled_actor_id, current)),
                    block('Знания действующих персонажей / GM-only', actor_knowledge(state, scope, current)),
                    block('Память', dict(strategy='canonical_history', llm_calls=0)),
                    block('Недавняя история / GM-only', scope.history_events),
                    block('Director / GM-only', plan(state, kind, scope=scope))]
        for title, mode in [('Наблюдаемые вне физической сцены', FULL_OBSERVED),
                            ('Удалённые собеседники', FULL_REMOTE),
                            ('Упомянутые, присутствие не установлено', COMPACT_REFERENCED)]:
            group = [c for c in cards if c['context_mode']==mode]
            if group:
                messages.append(block(title+' / GM-only', group))
        from backend.runtime_v3.reproduction import birth_authoring_context
        births = birth_authoring_context(state, scope)
        if births:
            messages.append(block('Birth authoring constraints / GM-only', dict(
                pregnancies=births,
                instruction='Canonical child IDs and sex constrain only an actual delivery in this scene. '
                'This is NOT character Knowledge, not proof of delivery, and not permission to reveal a secret. '
                'Before delivery never mention hidden count/sex. If delivery occurs, use canonical sex only '
                'when anatomy is actually observed or a grounded speaker reports it; otherwise omit sex. '
                'Only characters who perceive that specific observation/announcement learn it. '
                'Respect POV, capability and player agency. Do not invent an examination or announcement.')))
        from backend.runtime_v3.genre import guidance
        genre = guidance(state['meta'].get('genre'))
        if genre: messages.append(block('Genre / soft creative guidance', genre))
        legacy = legacy_knowledge(snapshot, scope)
        if legacy: messages.append(block('Legacy knowledge / GM-only, ownership unknown', legacy))
        # Knowledge rows are projected once into their ownership blocks.
        current_without_knowledge = dict(current, knowledge=[])
        messages[2] = block('Текущее состояние / GM-only', current_without_knowledge)
        if style_override:
            messages.append(block('Авторские настройки стиля и тона (формат ответа задан системными правилами)', style_override))
        if self.contract_version >= 11:
            observer = scope.pov_actor_id or scope.controlled_actor_id
            experience = {}
            for cid in sorted(scope.present_actor_ids | scope.remote_actor_ids):
                profile = state['characters'][cid].get('personality') or {}
                visible = [entry for entry in profile.get('evidence', {}).values()
                           if cid == observer or observer in entry['witnesses']]
                if visible:
                    experience[cid] = [dict(meaning=entry['meaning'], theme=entry.get('theme'))
                                       for entry in visible[-3:]]
            if experience:
                messages.append(block('Наблюдавшийся опыт / по владельцу', experience))
        # Exchange pairs remain indivisible when the builder budgets the literary tail.
        for view in views:
            timing = scene_time(state, view)
            if self.contract_version >= 11:
                status = json.loads(view.get('changes_json') or '{}').get('interpretation')
                if status in ('pending', 'partial', 'deferred'):
                    timing['interpretation'] = status
                    if 'end' in timing:
                        timing['last_applied_time'] = timing.pop('end')
            stamp = json.dumps(timing, ensure_ascii=False, separators=(',', ':'))
            messages.extend([dict(role='user', content='Прошлая сцена / canonical time '+stamp+'\n'+(view.get('user_text') or 'Продолжить.')),
                             dict(role='assistant', content=view.get('assistant_text', ''))])
        return rules, messages


def state_outcome(snapshot):
    return snapshot['world_state']['meta'].get('outcome_preference','natural')


class ExtractionContextBuilder:
    extraction = True

    def __init__(self, contract_version=EXTRACTION_VERSION):
        self.contract_version = contract_version

    def legacy_rules(self, snapshot, current, user_text, kind, prompts, historical, explicit_departures):
        saved = (prompts or {}).get('state_update_prompt.md', {}).get('content')
        # Preserve user overrides, but do not send the bundled generic contract twice.
        # Retry/regeneration can retain an older default in their immutable prompt
        # snapshot. Reuse the existing upgrade registry, without rewriting it.
        from backend.repositories.documents import is_builtin_prompt
        custom = saved and not is_builtin_prompt('state_update_prompt.md', saved, PROMPTS)
        rules = (saved + '\n' if custom else '') + EXTRACTION_CONTRACT
        if self.contract_version >= 5:
            from backend.runtime_v3.context_contract import BASE_EXTRACTION_CONTRACT, SEMANTIC_BASE_CONTRACT
            rules = rules.replace(BASE_EXTRACTION_CONTRACT, SEMANTIC_BASE_CONTRACT)
            from backend.runtime_v3.context_contract import (LIFE_EXTRACTION_CONTRACT, RESIDENCE_EXTRACTION_CONTRACT,
                SEMANTIC_LIFE_CONTRACT, SEMANTIC_RESIDENCE_CONTRACT)
            rules = rules.replace(LIFE_EXTRACTION_CONTRACT, SEMANTIC_LIFE_CONTRACT).replace(
                RESIDENCE_EXTRACTION_CONTRACT, SEMANTIC_RESIDENCE_CONTRACT)
            from backend.runtime_v3.context_contract import MOTIVATION_EXTRACTION_CONTRACT, SEMANTIC_MOTIVATION_CONTRACT
            rules = rules.replace(MOTIVATION_EXTRACTION_CONTRACT, SEMANTIC_MOTIVATION_CONTRACT)
        from backend.runtime_v3.context_contract import DEPARTURE_CONTRACT, TEMPORAL_REFINEMENT_CONTRACT
        if self.contract_version < 3:
            rules = rules.replace(TEMPORAL_REFINEMENT_CONTRACT,
                'weekday: legacy zero-based profile index (Gregorian Monday=0).')
        if self.contract_version >= 4:
            from backend.runtime_v3.context_contract import GROUNDED_CHOICES_CONTRACT, CHOICE_CONTRACT
            rules = rules.replace(CHOICE_CONTRACT, GROUNDED_CHOICES_CONTRACT)
        if not explicit_departures:
            rules = rules.replace(DEPARTURE_CONTRACT,
                'Departure without destination: Event + END absence, no completed_arrival, location unknown.')
        from backend.runtime_v3.player_actions import EXTRACTION_CONTRACT as action_contract, required as agency_required
        if agency_required(snapshot['world_state'], user_text, kind):
            from backend.runtime_v3.player_actions import LEGACY_EXTRACTION_CONTRACT
            from backend.runtime_v3.player_actions import CONSEQUENCE_CONTRACT
            rules += CONSEQUENCE_CONTRACT if self.contract_version >= 3 else action_contract if self.contract_version >= 2 else LEGACY_EXTRACTION_CONTRACT
        if current.get('communication'): rules += REMOTE_EXTRACTION_CONTRACT
        if historical:
            from backend.runtime_v3.context_contract import HISTORICAL_EXTRACTION_CONTRACT
            rules += HISTORICAL_EXTRACTION_CONTRACT
        if current.get('relationship_evidence') or self.contract_version >= 5:
            from backend.runtime_v3.context_contract import RELATIONSHIP_EVIDENCE_CONTRACT
            relationship_contract = RELATIONSHIP_EVIDENCE_CONTRACT
            if self.contract_version >= 5:
                from backend.runtime_v3.context_contract import SEMANTIC_RELATIONSHIP_CONTRACT
                relationship_contract = SEMANTIC_RELATIONSHIP_CONTRACT
            rules += relationship_contract
        if self.contract_version >= 5:
            from backend.runtime_v3.context_contract import SEMANTIC_SLICE_CONTRACT
            rules = rules.replace('Directed feelings need prior relationship_evidence', 'Directed feelings need accepted current Events or prior relationship_evidence')
            rules += SEMANTIC_SLICE_CONTRACT
        if self.contract_version >= 6:
            from backend.runtime_v3.scene_steps import CONTRACT as scene_contract
            from backend.runtime_v3.context_contract import SEMANTIC_BASE_CONTRACT, SEMANTIC_SLICE_CONTRACT
            if self.contract_version >= 7:
                from backend.runtime_v3.scene_steps import SPATIAL_CONTRACT as scene_contract
            if self.contract_version >= 8:
                scene_contract = scene_contract.replace('Extraction/7', 'Extraction/8') + "\nMovement input_source contains only quote and meaning, never intended_target_ids. Travellers are not speech addressees. Preserve separate questions and perceived replies, using during_step_id for speech on a route.\n"
            rules = rules.replace(SEMANTIC_BASE_CONTRACT, scene_contract).replace(SEMANTIC_SLICE_CONTRACT, '')
            from backend.runtime_v3.player_actions import CONSEQUENCE_CONTRACT
            rules = rules.replace(CONSEQUENCE_CONTRACT, '')
            rules = rules.replace('EXTERNAL: completed_voluntary_behavior + exact player quote + narrated completion;',
                'EXTERNAL: source_event_id references a completed scene step with input_source;')
            rules = rules.replace('Voluntary EXTERNAL changes require explicit_choice and quoted player_evidence;',
                'Voluntary EXTERNAL appearance changes require source_event_id linked to a completed step with input_source;')
            rules = rules.replace('Order successive Events. EXTERNAL voluntary choices require\nplayer evidence;',
                'Use scene-step order. EXTERNAL voluntary choices require input_source on the referenced step;')
        return rules

    def build(self, snapshot, scope, current, views, user_text, kind, prompts, extraction_text):
        from backend.runtime_v3.player_actions import required as agency_required
        from backend.services.letter_sources import enabled as historical_enabled
        historical = historical_enabled(snapshot['world_state'])
        explicit_departures = self.contract_version >= 4 or kind == 'background'
        if self.contract_version >= 9:
            template = 'state_update_prompt.md' if self.contract_version >= 11 else 'state_update_v10.md' if self.contract_version == 10 else 'state_update_v9.md'
            rules = (prompts or {}).get('_scene_rules', {}).get('content') or (PROMPTS/template).read_text(encoding='utf-8')
            additions = (prompts or {}).get('extraction_author.md', {}).get('content', '')
            if historical:
                from backend.runtime_v3.context_contract import HISTORICAL_EXTRACTION_CONTRACT
                rules += HISTORICAL_EXTRACTION_CONTRACT
            if additions:
                rules += '\nАвторские акценты интерпретации:\n' + additions
        else:
            rules = self.legacy_rules(snapshot, current, user_text, kind, prompts, historical, explicit_departures)
        reproductive = bool(current.get('pregnancies')) or any(
            c.get('reproductive_capability','unknown')!='unknown' or is_game_birth(snapshot['world_state'],c['id'])
            for c in current['characters'].values())
        if reproductive and self.contract_version >= 10:
            rules += ('\nДля завершившихся родов укажи pregnancy_id и фактических наблюдателей в perceived_by. '
                      'Для известного пола используй information с существующим fact_id и получателями. '
                      'Срок, дату рождения, идентичность ребёнка и родственные связи рассчитывает Runtime. '
                      'Для встречи взрослых укажи участников, согласие и защиту. Выбор героя остаётся за игроком.')
        elif reproductive:
            from backend.runtime_v3.context_contract import REPRODUCTION_CONTRACT
            rules += REPRODUCTION_CONTRACT
            if any(p['status'] != 'born' for p in current.get('pregnancies', [])):
                from backend.runtime_v3.context_contract import BIRTH_SEX_CONTRACT
                rules += BIRTH_SEX_CONTRACT
            # Recorded Director continuity is POV-filtered, also on retry. The
            # Extraction contract comes from the immutable pre-turn world.
            from backend.runtime_v3.continuity import due_births_in_scene_clock
            if kind != 'background' and not snapshot.get('_time_skip') and due_births_in_scene_clock(snapshot['world_state']):
                from backend.runtime_v3.context_contract import CURRENT_DUE_BIRTH_CONTRACT, DUE_BIRTH_CONTRACT
                rules += (DUE_BIRTH_CONTRACT if self.contract_version < 9 else CURRENT_DUE_BIRTH_CONTRACT)
        if 6 <= self.contract_version < 9:
            rules = rules.replace('final_scene.', 'scene.')
        # Affected IDs and canonical runtime, plus a bounded actor-owned choice
        # projection. No other actors' card prose or old narratives are needed.
        # Include physical/emotion baseline also for referenced actors affected in completed text.
        for cid in current['characters']:
            for key in ('physical_state', 'emotion'):
                current['characters'][cid][key] = snapshot['world_state']['characters'][cid][key]
        cards = [card for card in snapshot['character_cards'] if card['id'] in scope.relevant_actor_ids]
        if self.contract_version >= 9:
            # IDs are already the keys in the canonical projection. Only card aliases
            # add information beyond the Character name and identity.
            entities = [dict(id=card['id'], aliases=card['aliases']) for card in cards if card.get('aliases')]
        else:
            entities = [dict(id=card['id'], name=snapshot['world_state']['characters'][card['id']].get('display_name') or card['name'],
                             aliases=card.get('aliases', [])) for card in cards]
        return rules, [block('Текущее состояние / GM-only', extraction_state(current, self.contract_version)),
                       *([block('Choice context / controlled actor', choice_context(snapshot, scope, current, views, kind))] if self.contract_version < 9 else []),
                       block('Entity IDs', entities),
                       block('JSON Schema', prompt_schema(spatial_version=self.contract_version, camera_mode=snapshot['world_state']['camera']['mode'], scene_sequence=self.contract_version >= 6, semantic_slice=self.contract_version >= 5, explicit_departures=explicit_departures, grounded_choices=self.contract_version >= 4, consequence_first=self.contract_version >= 3, agency_audit_required=self.contract_version >= 2, player_agency_required=agency_required(snapshot['world_state'], user_text, kind), historical=historical, elapsed_required=kind=='turn' and not snapshot.get('_time_skip'), relationship_evidence=self.contract_version >= 5 or bool(current.get('relationship_evidence')), communication=bool(current.get('communication')), groups=any(c['group'] for c in snapshot['world_state']['conversations'].values()), voice=bool(current.get('communication',{}).get('active_call')), reproduction=reproductive, births=any(p['status']!='born' for p in current.get('pregnancies',[])), favorable_paths=state_outcome(snapshot)=='guaranteed_happy_path'))]


def extraction_state(current, version):
    if version < 9:
        return current
    result = dict(current)
    for domain in ('characters', 'locations', 'facts'):
        result[domain] = {key: {k:v for k,v in row.items() if k != 'id' or v != key}
                          for key,row in current[domain].items()}
    return result


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
                   observed_actor_ids=sorted(scope.observed_actor_ids), remote_actor_ids=sorted(scope.remote_actor_ids), situation=current['camera'].get('situation', '')),
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
                  target_context_budget=18000, pacing_decision=None, initiative_decision=None, continuity_decision=None, extraction_contract=EXTRACTION_VERSION, suggestions=(), public_observation=False):
    from context_builder import estimate
    state = snapshot['world_state']; camera = state['camera']
    if extraction_text is None:
        # Apply the knowledge boundary before relevance/pacing can summarize a
        # private commitment, not just before rendering the final calendar list.
        from backend.runtime_v3.remote import visible_commitments
        observer = camera.get('pov_actor_id') or camera.get('controlled_actor_id')
        # Reproduction has a typed, Knowledge-filtered projection. Its calendar
        # reminders are internal even when the pregnancy itself is known.
        schedule = visible_commitments(state, observer, world_history)
        state = dict(state, scheduled_events={
            eid: event for eid, event in schedule.items() if eid not in state.get('pregnancies', {})})
        snapshot = dict(snapshot, world_state=state)
    all_views = visible_views(snapshot, turns, kind)
    # Recorded versions keep their original six-scene projection.
    if extraction_contract >= 10 and extraction_text is None:
        recent_turns = max(1, recent_turns)
    views = all_views[-min(20 if extraction_contract >= 9 else 6, max(0, recent_turns)):] if recent_turns else []
    scope = RelevanceResolver().resolve(snapshot, user_text, all_views[-3:], world_history, extraction_text)
    observer = scope.pov_actor_id or scope.controlled_actor_id
    remote_private = {identity('communicated_text', e['id']) for e in state.get('remote_events', {}).values()
                      if e['channel']!='VOICE_CALL' and observer not in e['read_by'] and observer != e['sender_id']}
    private_context_facts = set()
    if camera['mode'] == 'actor':
        # Relevance of a mentioned off-scene NPC does not authorize exposing
        # their private facts or legacy threads to this player-facing scene.
        actors = scope.present_actor_ids | scope.observed_actor_ids | scope.remote_actor_ids | scope.active_actor_ids | {scope.controlled_actor_id}
        available = {k['fact_id'] for k in state['knowledge'].values()
                     if k['actor_id'] in actors and (k['status'] in ('known', 'suspected')
                     or k['actor_id'] in scope.active_actor_ids)}
        private_context_facts = {fid for fid in scope.fact_ids
                           if state['facts'][fid].get('visibility') == 'secret' and fid not in available}
        remote_private |= private_context_facts
        scope.thread_ids = [tid for tid in scope.thread_ids
            if (state['threads'][tid].get('discovered_by') is not None and actors.intersection(state['threads'][tid].get('discovered_by')))
            or (state['threads'][tid].get('discovered_by') is None and
                (not state['threads'][tid]['character_ids'] or actors.intersection(state['threads'][tid]['character_ids'])))]
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
    scope.continuity_decision = deepcopy(continuity_decision) if continuity_decision is not None else continuity_project(state, scope, world_history, version=extraction_contract)
    if snapshot.get('_time_skip') or kind == 'background': scope.continuity_decision['compression'] = {'max_minutes':0,'boundary_ids':[]}
    scope.pacing_decision = deepcopy(pacing_decision) if pacing_decision is not None else evaluate(state, scope)
    from backend.runtime_v3.initiative import scene_plan
    scope.initiative_decision = deepcopy(initiative_decision) if initiative_decision is not None else scene_plan(state, scope)
    current = canonical_slice(state, scope, extraction_text is not None, user_text+'\n'+(extraction_text or ''))
    project_temporal_context(snapshot, turns, current)
    if extraction_text is not None and extraction_contract >= 3:
        from backend.runtime_v3.calendar import weekday_options
        current['calendar_weekdays'] = weekday_options(state)
    scope.history_events = deepcopy(scope.history_events)
    for event in scope.history_events:
        event['event_time'] = time_stamp(state, event['minute']) if type(event.get('minute')) is int else {'time': 'unknown'}
        if type(event.get('recorded_minute')) is int:
            event['recorded_time'] = time_stamp(state, event['recorded_minute'])
    if extraction_text is not None and extraction_contract >= 5:
        current['chronology_events'] = [dict(id=e['id'], text=e.get('text', '')[:600], minute=e['minute'],
            date=e['event_time'].get('date'), elapsed_days=state['meta']['world_time']//1440-e['minute']//1440)
            for e in scope.history_events if type(e.get('minute')) is int][-8:]
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
            from backend.runtime_v3.remote_semantics import staged_sources, relationship_sources
            sources=staged_sources(snapshot)
            if sources:
                remote['accepted_semantic_messages']=list(sources.values())
                remote['relationship_sources']=[e for e in relationship_sources(snapshot) if e['id'] in sources]
                remote['constraints'] += (' Extract consequences of these accepted messages through the normal locations, threads, scheduled_event_changes, '
                    'relationship_changes (canonical relationship_sources and grounded_feelings), and explicit intentions_updates. '
                    'A proposal requires actual assent; cite remote_source_ids and remote_time_source_id. Unread confirmation can establish GM truth, never recipient Knowledge. '
                    'Group requests to the controlled actor use group_request_changes with canonical source_event_id, '
                    'target_id, exact evidence and expires_at. Only explicit answers/refusals authored by that actor in the same '
                    'group use group_response_changes. Reading, silence and Narrative turns are not answers. '
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
    if extraction_text is not None and extraction_contract >= 9:
        for actor in current['characters'].values():
            for key in ('appearance_history','name_history','goals','intentions','obligations','values','personality'):
                if key in actor and actor[key] in (None,[],{}):
                    del actor[key]
    builder = ExtractionContextBuilder(extraction_contract) if extraction_text is not None else NarrativeContextBuilder(extraction_contract)
    rules, messages = builder.build(snapshot, scope, current, views, user_text, kind, prompts, extraction_text)
    reply_format = None
    if not builder.extraction and (kind != 'background' or public_observation) and extraction_contract >= 9:
        if extraction_contract >= 10:
            from backend.runtime_v3.context_contract import PROSE_ONLY_OUTPUT
            from backend.runtime_v3.narrative_frame import FORMAT, RECORDED_FORMAT, AUTHOR_FORMAT
            rules = rules.replace(PROSE_ONLY_OUTPUT, '')
            from backend.runtime_v3.life import capabilities
            directs = camera['mode']=='observer' or (scope.controlled_actor_id and
                        not capabilities(state,scope.controlled_actor_id)['can_act'])
            if extraction_contract >= 11:
                rules = rules.replace('Не выводи варианты действий.', '')
                rules += '\n' + AUTHOR_FORMAT
            reply_format = (FORMAT if extraction_contract >= 11 else RECORDED_FORMAT) + (' Варианты задают направление истории в режиме наблюдателя.'
                                     if directs else ' Варианты от лица героя.')
            if state['meta'].get('interaction_focus')=='call':
                reply_format += ' Предложи продолжения этого звонка.'
        elif camera['mode']=='actor' and scope.controlled_actor_id:
            from backend.runtime_v3.life import capabilities
            from backend.runtime_v3.suggestions import NARRATIVE_INSTRUCTION
            if capabilities(state, scope.controlled_actor_id)['can_act']:
                rules += NARRATIVE_INSTRUCTION
    if builder.extraction and extraction_contract >= 10:
        for message in messages:
            if message['content'].startswith('JSON Schema\n'):
                schema = json.loads(message['content'].split('\n', 1)[1])
                if not suggestions:
                    schema['properties'].pop('choices', None)
                if extraction_contract >= 11:
                    scene_fields = schema['properties']['scene']['properties']
                    scene_fields.pop('compression', None)
                    scene_fields.pop('situation_evidence', None)
                    # The compiler still reads explicit links in saved responses.
                    for name in ('role_changes','residence_changes','social_relation_changes'):
                        phase = schema['properties'][name]['items']['properties']
                        phase.pop('fact_id', None)
                        phase.pop('closure_fact_id', None)
                for section in ('reproductive_events','social_relation_changes','role_changes','residence_changes','life_changes'):
                    if section not in schema['properties'] or not scope.controlled_actor_id:
                        continue
                    properties = schema['properties'][section]['items'].get('properties', {})
                    if 'player_evidence' not in properties:
                        continue
                    properties.pop('player_assertion', None)
                    properties['player_evidence']['description'] = (
                        f'Для добровольного решения героя {scope.controlled_actor_id} укажи его слова из текущего ввода дословно.')
                if 'births' in schema['properties']:
                    schema['properties']['births']['items']['properties'].pop('sex_observations', None)
                from backend.runtime_v3.raw import prune_schema_definitions
                prune_schema_definitions(schema)
                message['content'] = block('JSON Schema', schema)['content']
                break
    if builder.extraction and suggestions and extraction_contract >= 9:
        if extraction_contract >= 10:
            rules += '\nУкажи в choices индексы готовых предложений и доступные герою источники grounding.'
        messages.append(block('Предложения Narrative / ещё не выбраны', suggestions))
    from backend.runtime_v3.context_contract import CONTROL_CONTRACT
    from backend.runtime_v3.context_contract import EXTRACTION_TIME_CONTRACT
    clock_rules = EXTRACTION_TIME_CONTRACT if builder.extraction else TIME_CONTRACT
    if not builder.extraction and extraction_contract >= 11:
        clock_rules = clock_rules.replace('Если дан time_skip_target, завершай описание и формируй choices для этого конечного времени.',
            'При time_skip_target доведи сцену до цели или до фактически произошедшего прерывания.')
    if builder.extraction and extraction_contract >= 11:
        clock_rules = clock_rules.replace(' End prose/choices at time_skip_target.', '')
    rules += '\n' + clock_rules
    rules += '\n' + (CONTROL_CONTRACT if extraction_text is None else 'death_protected_actor_ids: reject autonomous death.')
    if extraction_contract >= 11:
        rules = rules.replace('; accepted Runtime involuntary consequences can be narrated.', '.')
        rules += ('\nPublished scenes happened. Use the last saved mechanics for calculations. '
                  'After partial or deferred interpretation the saved clock and positions may lag the prose. '
                  'Later explicit player corrections take precedence. Preserve individual Knowledge.')
        if all_views:
            status = json.loads(all_views[-1].get('changes_json') or '{}').get('interpretation')
            if status in ('pending','partial','deferred'):
                messages.append(block('Статус механики последней видимой сцены', dict(interpretation=status,
                    note='Часы и позиции отражают последние применённые изменения. Конец сцены подтверждён не полностью.')))
    elif extraction_contract >= 10:
        rules += ('\nPublished scenes happened. Records may lag. Honor later player edits, calendar, '
                  'ages, pregnancies and individual knowledge.')
    else:
        rules += ('\nWorldState overrides historical Milestones/History/biography (roles, relations, homes, names). '
              'Milestones grant no Knowledge; known_by limits actor access.')
    if extraction_contract >= 10 and not builder.extraction:
        # Explicit edits are branch-local. Expose only still-current edits
        # relevant to this POV, and no knowledge about another recipient.
        edits = []
        for row in (world_history or {}).get('state_changes', []):
            if row.get('kind') == 'manual_scene' and row.get('location_id') == camera.get('location_id'):
                if scope.controlled_actor_id in row.get('present_ids',[]):
                    edits.append(dict(turn=row['turn_id'],location_id=row['location_id']))
            elif row.get('kind') == 'manual_knowledge' and row.get('actor_id') == scope.controlled_actor_id:
                fid = row['fact_id']
                belief = state['knowledge'].get(scope.controlled_actor_id + ':' + fid, {})
                if fid in current['facts'] and belief.get('status') == row['status']:
                    edits.append(dict(turn=row['turn_id'], fact=state['facts'][fid]['text'], status=row['status']))
        if edits:
            messages.append(block('Ручные исправления канона', edits[-6:]))
    if not builder.extraction: rules += f'\nRuntime v3. controlled_actor_id={camera["controlled_actor_id"]}; mode={camera["mode"]}; world_time={state["meta"]["world_time"]} минут.'
    if current.get('weather'): rules += '\nWeather is canonical environmental context, not an instruction to mention it each turn. Do not invent contradictory weather, force actions or move characters because of it.'
    if snapshot.get('_time_skip'):
        rules += '\nДетерминированный Time Skip: ' + json.dumps(snapshot['_time_skip'], ensure_ascii=False)
        if builder.extraction and extraction_contract >= 11:
            rules += '. Учитывай цель и фактическое время завершённой сцены.'
        else:
            rules += '. Описывай только до actual_target, не позже. Hidden не становится знанием игрока.'
    if validation_feedback:
        try:
            feedback = json.loads(validation_feedback)
        except (ValueError, TypeError):
            feedback = None  # Older/custom feedback remains verbatim.
        if isinstance(feedback, dict) and isinstance(feedback.get('known_locations'), dict):
            feedback['known_locations'] = {lid:row for lid,row in feedback['known_locations'].items()
                                           if lid not in current['locations']}
            if not feedback['known_locations']:
                feedback.pop('known_locations')
            validation_feedback = json.dumps(feedback, ensure_ascii=False, separators=(',', ':'))
        if isinstance(feedback, dict):
            if 5 <= extraction_contract < 6 and 'contract' in feedback:
                # Existing semantic rules above remain authoritative. Feedback
                # supplies differences, not a second copy of the same contract.
                feedback['contract'] = ('Reinterpret the unchanged full Narrative and input against immutable before. '
                    'Fix all diagnostics/dependencies together; preserve ALL confirmed consequences and learning. '
                    'Rejected JSON is not canon: do not fabricate consent, arrivals, speakers or hide outcomes. '
                    'For violated Narrative use the existing agency/chronology findings, not JSON laundering. '
                    'Return full RawTurnResult with final_scene and every response_required section; '
                    'recheck omitted_sections_from_previous_proposal. Feedback keys are input only, never a patch. '
                    'Only one automatic repair; never rewrite Narrative or History.')
                validation_feedback = json.dumps(feedback, ensure_ascii=False, separators=(',', ':'))
            for message in messages:
                if message['content'].startswith('JSON Schema\n'):
                    schema = json.loads(message['content'].split('\n', 1)[1])
                    if extraction_contract >= 5 and 'knowledge_gained' in feedback.get('response_required', []):
                        from backend.runtime_v3.raw import extraction_schema
                        schema['properties']['knowledge_gained'] = extraction_schema()['properties']['knowledge_gained']
                    if extraction_contract >= 6:
                        from backend.runtime_v3.scene_repair import repair_schema
                        schema = repair_schema(schema, validation_feedback)
                    schema['required'] = list(dict.fromkeys(schema.get('required', []) + [key
                        for key in feedback.get('response_required', []) if key in schema['properties']]))
                    message['content'] = block('JSON Schema', schema)['content']
        repair_intro = ('Повторно интерпретируй неизменный Narrative; верни ответ по JSON Schema и repair_mode:'
                        if extraction_contract >= 6 else
                        'Повторно интерпретируй неизменный Narrative по feedback; верни полный JSON:')
        rules += '\n' + repair_intro + '\n' + validation_feedback
    from backend.services.world_creation_settings import presentation_rule
    rules += presentation_rule(state['meta'].get('npc_expressiveness','realistic'))
    messages.insert(0, dict(role='system', content='Постоянные правила\n'+rules))
    current_input = dict(kind=kind, player_input=user_text)
    if reply_format:
        current_input['response_format'] = reply_format
    messages.append(block('Текущий ввод', current_input))
    if extraction_text is not None: messages.append(block('completed_narrative', extraction_text))
    # Authoring support participates in the same token budget as every other
    # Narrative source. It must never be appended after context selection.
    from backend.services.letter_sources import enabled as letters_enabled, author_context
    letter_context_index = None
    if not builder.extraction and letters_enabled(state):
        letter_context_index = len(messages)
        messages.append(author_context(state))
    hard_context_limit = context_length - reserve - 256
    target = min(target_context_budget, hard_context_limit)
    if builder.extraction and not validation_feedback:
        # Leave soft headroom for the previous JSON plus diagnostic feedback.
        # Critical source blocks still use the real hard limit when unavoidable.
        target = min(target, max(0, hard_context_limit - reserve - 1024))
    if extraction_contract >= 9 and not builder.extraction:
        # Remove whole oldest literary exchanges; keep the most recent scene.
        literary_cost = sum(estimate([m])-256 for m in messages if m['role']=='assistant' or m['content'].startswith('Прошлая сцена / canonical time '))
        literary_target = min(hard_context_limit, max(target, estimate(messages)-literary_cost + 4096))
        while len(views) > 1 and estimate(messages) > literary_target:
            at = next(i for i,m in enumerate(messages) if m['content'].startswith('Прошлая сцена / canonical time '))
            del messages[at:at + 2]
            views = views[1:]
            if letter_context_index is not None:
                letter_context_index -= 2
    if letter_context_index is not None:
        for limit in range(5, -1, -1):
            if estimate(messages) <= target: break
            messages[letter_context_index] = author_context(state, limit)


    reader = (world_history or {}).get('_literary_sources')
    if reader and not builder.extraction and extraction_contract >= 9:
        recent = {v.get('sequence') for v in views}
        sources = (e.get('source_sequence', e['turn_id']-1 if type(e.get('turn_id')) is int else None)
                   for e in scope.history_events)
        source_sequences = {n for n in sources if type(n) is int and n >= 0} - recent
        archive_limit = min(hard_context_limit, max(target, estimate(messages) + 1800))
        if source_sequences:
            for view in reversed(visible_views(snapshot, reader(sorted(source_sequences)[-3:]), kind)):
                excerpt = block('Прошлая сцена / литературная память' if extraction_contract >= 10 else 'Прошлая сцена / архив, канон текущего состояния имеет приоритет', dict(
                    time=scene_time(state,view), sequence=view['sequence'], prose=view['assistant_text']))
                if estimate([*messages,excerpt]) <= archive_limit:
                    messages.insert(-1, excerpt)

    def replace_schema(schema):
        # Do not pay for format instructions for omitted optional annotations.
        # Core Event/state/agency rules remain in the mandatory contract.
        from backend.runtime_v3.context_contract import SCENE_ACTION_EXTRACTION_CONTRACT, CONTINUITY_EXTRACTION_CONTRACT
        for fields, contract in [(('scene_actions',), SCENE_ACTION_EXTRACTION_CONTRACT),
                                 (('scene_transitions', 'continuity_beats'), CONTINUITY_EXTRACTION_CONTRACT)]:
            if all(field not in schema['properties'] for field in fields):
                messages[0]['content'] = messages[0]['content'].replace(contract, '')
        replace_block('JSON Schema', schema)

    def replace_block(title, value):
        for i, message in enumerate(messages):
            if message['content'].startswith(title+'\n'): messages[i] = block(title, value); return

    selected = {key: len(current[key]) for key in ('locations', 'facts', 'knowledge', 'relationships', 'threads', 'scheduled_events')}
    # Retrieval diagnostics retain selected-but-not-transmitted candidates.
    # This metadata is never a model context or a grant of Knowledge.
    selected['facts'] += len(private_context_facts)
    selected_history = list(scope.history_events)
    def refresh_current():
        replace_block('Текущее состояние / GM-only', extraction_state(current, extraction_contract) if builder.extraction else dict(current, knowledge=[]))
        if builder.extraction and extraction_contract < 9:
            replace_block('Choice context / controlled actor', choice_context(snapshot, scope, current, views, kind))
        elif not builder.extraction:
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
        title = 'Упомянутые, присутствие не установлено / GM-only'
        card_message = next((m for m in messages if m['content'].startswith(title+'\n')), None)
        cards = json.loads(card_message['content'].split('\n', 1)[1]) if card_message else []
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
        if estimate(messages) <= (hard_context_limit if extraction_contract >= 9 else target): break
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
        if extraction_contract < 9:
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
                    if section not in schema.get('required', []):
                        schema['properties'].pop(section, None)
                if 'value_deltas' not in schema.get('required', []) and not any(actor.get('values') for actor in current['characters'].values()):
                    schema['properties'].pop('value_deltas', None)
                # Shared definitions belonging only to omitted evaluations do
                # not need to remain in the wire schema.
                from backend.runtime_v3.raw import prune_schema_definitions
                prune_schema_definitions(schema)
                replace_schema(schema)
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
                    if section not in schema.get('required', []):
                        schema['properties'].pop(section, None)
                    from backend.runtime_v3.raw import prune_schema_definitions
                    prune_schema_definitions(schema)
                    replace_schema(schema)
                break
    if builder.extraction and estimate(messages) > target:
        # Optional structured profile enrichment duplicates the eleven descriptive
        # card fields. Keep every identity/life/capability field and the full card;
        # omit only this enrichment in tight wire schemas, never canonical data.
        for message in messages:
            if message['content'].startswith('JSON Schema\n'):
                schema = json.loads(message['content'].split('\n', 1)[1])
                def dereference(node):
                    while '$ref' in node: node=schema['$defs'][node['$ref'].split('/')[-1].removeprefix('#')]
                    return node
                if 'promotions' not in schema['properties']:
                    break  # Scoped repair has no unrelated promotion payload.
                promotion=dereference(schema['properties']['promotions']['items'])
                character=dereference(promotion['properties']['character'])
                for field in ('appearance','personality','values'):
                    character['properties'].pop(field,None)
                from backend.runtime_v3.raw import prune_schema_definitions
                prune_schema_definitions(schema)
                replace_schema(schema)
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
    annotation_budget = target if builder.extraction and extraction_contract >= 5 else hard_context_limit
    if builder.extraction and estimate(messages) > annotation_budget:
        # Mandatory action provenance takes priority over optional Director
        # annotations, just as communication outcomes do above. Domain Events,
        # state, agency and presence contracts remain complete and validated.
        for message in messages:
            if message['content'].startswith('JSON Schema\n'):
                schema = json.loads(message['content'].split('\n', 1)[1])
                from backend.runtime_v3.raw import prune_schema_definitions
                for section in ('scene_transitions', 'narrative_developments', 'consequences', 'continuity_beats', 'scene_actions'):
                    if estimate(messages) <= annotation_budget: break
                    if section not in schema.get('required', []):
                        schema['properties'].pop(section, None)
                    prune_schema_definitions(schema)
                    replace_schema(schema)
                break
    if builder.extraction and extraction_contract >= 6 and estimate(messages) > hard_context_limit:
        # Optional choice personalization must not block mandatory consequences.
        # Keep the choices schema and canonical actor/Knowledge context; the
        # existing choice owner still rejects inaccessible sources. Narrative
        # authoring and its personalization are unaffected.
        messages[:] = [m for m in messages if not m['content'].startswith('Choice context / controlled actor\n')]
    # Give lossless/default/schema compaction a chance before discarding the last
    # canonical relationship source to make room for the mandatory agency review.
    if estimate(messages) > hard_context_limit and current.get('relationship_evidence'):
        current.pop('relationship_evidence')
        replace_block('Текущее состояние / GM-only', extraction_state(current, extraction_contract) if builder.extraction else dict(current, knowledge=[]))
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
        {c['id'] for title in ('Карточки присутствующих / GM-only', 'Наблюдаемые вне физической сцены / GM-only',
                             'Удалённые собеседники / GM-only', 'Упомянутые, присутствие не установлено / GM-only',
                             'Поведенческие профили / GM-only', 'Индекс персонажей') for c in contents(title)})
    included_counts = {mode: sum(classifier.classify(cid, scope) == mode for cid in included_actors) for mode in counts}
    selected_ids = dict(characters=set(state['characters']), locations=set(scope.location_ids), facts=set(scope.fact_ids) | private_context_facts,
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
        choices = contents('Choice context / controlled actor') or {}
        diagnostics['choice_context'] = dict(enabled=choices.get('enabled', False), actor_id=choices.get('actor_id'),
            recent_inputs=len(choices.get('recent_player_expression', [])), knowledge=len(choices.get('knowledge', [])))
        if not choices:
            diagnostics['choice_context']['omitted_for_budget'] = True
    return ContextMessages(messages, diagnostics)
