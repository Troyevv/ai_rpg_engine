"""One disposable deterministic relevance scope per request, never canonical state."""
from backend.runtime_v3.calendar import scheduled_boundary as scheduled_due

from dataclasses import dataclass, field
import re

FULL_PRESENT = 'FULL_PRESENT'
FULL_REMOTE = 'FULL_REMOTE'
ACTIVE_REFERENCED = 'ACTIVE_REFERENCED'
COMPACT_REFERENCED = 'COMPACT_REFERENCED'
INDEX = 'INDEX'


STOP_WORDS = {'который', 'которая', 'которые', 'этого', 'этой', 'после', 'перед', 'только', 'себя', 'свои', 'свой', 'очень', 'может', 'было', 'были', 'есть', 'чтобы', 'когда', 'через', 'this', 'that', 'with', 'from', 'have', 'they'}


def words(text):
    return set(re.findall(r'\w{4,}', str(text).casefold())) - STOP_WORDS


def actor_aliases(card):
    names = [card['id'], card['name'], *card.get('aliases', [])]
    # Surface name forms only; no semantic classification of emotion/motivation.
    for name in list(names):
        if ' ' in name: names.extend(part for part in name.split() if len(part) > 2)
    for name in list(names):
        if not re.fullmatch(r'[А-ЯЁ][а-яё]+', name): continue
        if name.endswith('а'): names.extend(name[:-1]+suffix for suffix in ('ы', 'е', 'у', 'ой', 'ою'))
        elif name.endswith('я'): names.extend(name[:-1]+suffix for suffix in ('и', 'е', 'ю', 'ей', 'ею'))
        elif name.endswith(('й', 'ь')): names.extend(name[:-1]+suffix for suffix in ('я', 'ю', 'ем', 'е'))
        elif name[-1] not in 'ьйеиоуыэю': names.extend(name+suffix for suffix in ('а', 'у', 'ом', 'е'))
    return names


def location_aliases(location):
    # Canonical names may be lowercase. Reuse the same surface inflections for
    # location nouns so "на кухне" resolves existing "Кухня" before extraction.
    return actor_aliases(dict(id=location['id'], name=location['name'].capitalize(), aliases=[location['name']]))


def string_ids(value):
    return {item for item in value if isinstance(item, str)} if isinstance(value, list) else set()


def mentions(text, names):
    return any(re.search(r'(?<!\w)' + re.escape(name) + r'(?!\w)', text, re.I)
               for name in names if name)


@dataclass
class ContextScope:
    controlled_actor_id: str | None
    present_actor_ids: set = field(default_factory=set)
    remote_actor_ids: set = field(default_factory=set)
    active_actor_ids: set = field(default_factory=set)
    acting_scheduled_event_ids: set = field(default_factory=set)
    semantic_scores: dict = field(default_factory=dict)
    semantic_diagnostics: dict = field(default_factory=dict)
    selection_reasons: dict = field(default_factory=dict)
    structural_actor_ids: set = field(default_factory=set)
    referenced_actor_ids: set = field(default_factory=set)
    relevant_actor_ids: set = field(default_factory=set)
    location_ids: list = field(default_factory=list)
    fact_ids: list = field(default_factory=list)
    thread_ids: list = field(default_factory=list)
    event_ids: list = field(default_factory=list)
    scheduled_event_ids: list = field(default_factory=list)
    relationship_pairs: list = field(default_factory=list)
    knowledge_ids: list = field(default_factory=list)
    actor_scores: dict = field(default_factory=dict)
    fact_scores: dict = field(default_factory=dict)
    history_events: list = field(default_factory=list)
    query_words: set = field(default_factory=set)

    def reason(self, kind, entity_id, reason):
        self.selection_reasons.setdefault((kind, entity_id), set()).add(reason)

    def summary(self):
        return {name: sorted(getattr(self, name)) for name in (
            'present_actor_ids', 'remote_actor_ids', 'active_actor_ids', 'referenced_actor_ids',
            'location_ids', 'thread_ids', 'scheduled_event_ids')}


class CharacterContextClassifier:
    def classify(self, actor_id, scope):
        if actor_id in scope.present_actor_ids:
            return FULL_PRESENT
        if actor_id in scope.remote_actor_ids:
            return FULL_REMOTE
        if actor_id in scope.active_actor_ids:
            return ACTIVE_REFERENCED
        if actor_id in scope.referenced_actor_ids:
            return COMPACT_REFERENCED
        return INDEX


class RelevanceResolver:
    """Linear scans + deterministic ranking; no graph closure through the protagonist."""
    def resolve(self, snapshot, user_text, recent_views=(), world_history=None, completed_narrative=None, semantic_retriever=None):
        state = snapshot['world_state']
        camera = state['camera']
        cards = {c['id']: c for c in snapshot['character_cards']}
        names = {cid: actor_aliases(c) for cid, c in cards.items()}
        scope = ContextScope(camera['controlled_actor_id'])
        scope.present_actor_ids = set(camera['present_character_ids'])
        # A remote flag is a renewed current-scene interaction, not a relevance score.
        scope.remote_actor_ids = {r['actor_id'] for r in camera.get('remote_interactions', [])
                                  if r['last_active_turn'] == state['meta']['turn_id']}
        from backend.services.player_agency import declarations
        remote_input = re.sub(r'«[^»]*»|“[^”]*”|"[^"]*"', '', user_text, flags=re.S)
        for statement in declarations(re.sub(r':[^.\n]*', '', remote_input)):
            # Only an explicit current communication action, never reading old messages,
            # a plan to call, or merely saying somebody's name.
            match = re.match(r'^(?:я\s+)?(?:пишу|звоню|отправляю сообщение|связываюсь по рации с)\s+(.+)', statement, re.I)
            if match:
                target = re.split(r'[:,«"]', match[1], maxsplit=1)[0]
                scope.remote_actor_ids.update(cid for cid, aliases in names.items() if mentions(target, aliases))
        scope.remote_actor_ids -= scope.present_actor_ids
        from backend.runtime_v3.participation import active_actors
        scope.active_actor_ids = active_actors(snapshot, user_text, names, recent_views, world_history) - scope.present_actor_ids - scope.remote_actor_ids
        core = scope.present_actor_ids | scope.remote_actor_ids | scope.active_actor_ids
        scores = {cid: 0 for cid in cards}
        query = user_text + '\n' + (completed_narrative or '')
        scope.query_words = words(query)
        for cid, aliases in names.items():
            if mentions(query, aliases): scores[cid] += 50
            for age, view in enumerate(reversed(list(recent_views)[-3:])):
                if mentions(view.get('assistant_text', ''), aliases): scores[cid] += (40, 25, 10)[age]
        motivations = '\n'.join(r if isinstance(r, str) else r['text']
                                for cid in core for key in ('goals', 'intentions', 'obligations')
                                for r in state['characters'][cid][key]
                                if isinstance(r, str) or r['status'] == 'active')
        for cid, aliases in names.items():
            if mentions(motivations, aliases): scores[cid] += 30
        structural_scores = dict(scores)
        if completed_narrative is None:
            from backend.runtime_v3.semantic import retrieve, documents
            # Current input leads; one latest scene and a small motivation tail only.
            latest = recent_views[-1].get('assistant_text', '') if recent_views else ''
            semantic_query = user_text[:1200] + '\n' + latest[-600:] + '\n' + motivations[:400]
            result = (semantic_retriever.search(documents(snapshot, world_history), semantic_query)
                      if semantic_retriever is not None else retrieve(snapshot, world_history, semantic_query))
            scope.semantic_scores, scope.semantic_diagnostics = result.scores, result.diagnostics
            for (kind, eid), similarity in result.scores.items():
                scope.reason(kind, eid, 'SEMANTIC')
                if kind == 'characters' and eid in scores: scores[eid] += 25 + similarity*10
        else: scope.semantic_diagnostics = dict(status='not_requested')
        semantic = lambda kind, eid: scope.semantic_scores.get((kind, eid), 0)
        topic_words = scope.query_words | words(motivations)
        continuity_words = words(recent_views[-1].get('assistant_text', '')) if recent_views else set()
        for relationship in state['relationships'].values():
            pair = {relationship['source_id'], relationship['target_id']}
            if pair & core and words(relationship['context']) & topic_words:
                for cid in pair-core:
                    scores[cid] = scores.get(cid, 0) + 20
                    structural_scores[cid] = structural_scores.get(cid, 0) + 20
        current_location = camera['location_id']
        locations = {current_location} if current_location else set()
        for lid, location in state['locations'].items():
            if mentions(query + '\n' + motivations, location_aliases(location)): locations.add(lid)
        events = [e for e in (world_history or {}).get('events', [])
                  if isinstance(e, dict) and isinstance(e.get('text'), str)
                  and isinstance(e.get('participants'), list)
                  and all(isinstance(cid, str) for cid in e['participants'])]
        structural_locations = set(locations)
        locations.update(eid for kind, eid in scope.semantic_scores if kind == 'locations' and eid in state['locations'])
        recent = []
        for index, event in enumerate(events):
            turn = event.get('turn_id')
            age = state['meta']['turn_id'] - turn if type(turn) is int else len(events)-index-1
            if 0 <= age < 3 and (set(event['participants']) & core or event.get('location_id') == current_location):
                recent.append(event)
                for cid in event['participants']:
                    if cid in scores:
                        scores[cid] += (25, 15, 5)[age]
                        structural_scores[cid] += (25, 15, 5)[age]
        semantic_only = {cid for (kind, cid) in scope.semantic_scores if kind == 'characters' and structural_scores.get(cid, 0) < 25}
        mentioned = {cid for cid, score in scores.items() if score >= 25} - semantic_only
        scope.structural_actor_ids = mentioned | core
        ranked_threads = []
        for tid, thread in state['threads'].items():
            if thread['status'] not in ('active', 'developing'): continue
            ids = set(thread['character_ids'])
            topic = bool(topic_words & words(thread['description'] + ' ' + thread['state']))
            # Sharing only the controlled actor is not enough.
            score = 60*topic + 25*bool(continuity_words & words(thread['description'] + ' ' + thread['state'])) + 35*bool(ids & (core - {scope.controlled_actor_id})) + 30*bool(ids & (mentioned-core))
            score += 70*semantic('threads', tid)
            if score:
                ranked_threads.append((score + thread['relevance']*10, tid))
        scope.thread_ids = [tid for _, tid in sorted(ranked_threads, key=lambda x: (-x[0], x[1]))[:6]]
        for tid in scope.thread_ids:
            for cid in state['threads'][tid]['character_ids']:
                scores[cid] = scores.get(cid, 0) + 35
                thread = state['threads'][tid]
                if words(thread['description']+' '+thread['state']) & (topic_words | continuity_words) or set(thread['character_ids']) & (core - {scope.controlled_actor_id}):
                    scope.structural_actor_ids.add(cid)
        scope.actor_scores = scores
        scope.referenced_actor_ids = set(sorted((cid for cid, score in scores.items() if score >= 25 and cid not in core), key=lambda cid: (-scores[cid], cid))[:12])
        scope.relevant_actor_ids = core | scope.referenced_actor_ids
        now = state['meta']['world_time']
        ranked_scheduled = []
        acting_scheduled = set()
        for eid, event in state['scheduled_events'].items():
            due = scheduled_due(state, event)
            pending = event['status'] == 'pending'
            imminent = pending and due is not None and due <= now + 60
            linked = bool(set(event['character_ids']) & scope.relevant_actor_ids) or bool(event.get('location_id') and event['location_id'] in locations)
            topic = bool(topic_words & words(event['description']))
            structural_link = bool(set(event['character_ids']) & scope.structural_actor_ids) or event.get('location_id') in structural_locations
            if pending and due is not None and due <= now and (structural_link or event.get('interrupts')):
                acting_scheduled.add(eid)
            recent_terminal = not pending and event.get('source_turn') is not None and state['meta']['turn_id']-event['source_turn'] <= 8
            active_interval = pending and event.get('started_minute') is not None
            if linked and (recent_terminal or active_interval) or (imminent and (linked or event.get('interrupts'))) or (linked and (topic or due is None)) or semantic('scheduled_events', eid):
                ranked_scheduled.append((100*imminent + 40*linked + 30*topic + 70*semantic('scheduled_events', eid), eid))
        scope.scheduled_event_ids = [eid for _, eid in sorted(ranked_scheduled, key=lambda x: (-x[0], x[1]))[:12]]
        scope.acting_scheduled_event_ids = acting_scheduled & set(scope.scheduled_event_ids)
        for eid in scope.scheduled_event_ids:
            if state['scheduled_events'][eid].get('location_id'): locations.add(state['scheduled_events'][eid]['location_id'])
        thread_text = '\n'.join(state['threads'][tid]['description'] + ' ' + state['threads'][tid]['state'] for tid in scope.thread_ids)
        for lid, location in state['locations'].items():
            if mentions(thread_text, location_aliases(location)): locations.add(lid)
        # Imminent arrivals are referenced, never physically present or remote yet.
        for eid in scope.scheduled_event_ids:
            event = state['scheduled_events'][eid]
            if event['status'] == 'pending' and scheduled_due(state, event) is not None and scheduled_due(state, event) <= now + 60:
                scope.referenced_actor_ids.update(set(event['character_ids']) - core)
        # Director due actions are personalized output requests, not presence.
        for eid in scope.scheduled_event_ids:
            event = state['scheduled_events'][eid]
            if eid in acting_scheduled:
                scope.active_actor_ids.update(set(event['character_ids']) - scope.present_actor_ids - scope.remote_actor_ids)
                for cid in event['character_ids']: scope.reason('characters', cid, 'SCHEDULED')
        core |= scope.active_actor_ids
        scope.referenced_actor_ids -= core
        scope.relevant_actor_ids = core | scope.referenced_actor_ids
        scope.location_ids = sorted(locations)
        location_words = set().union(*(words(state['locations'][lid]['name']) for lid in locations)) if locations else set()
        event_facts = set().union(*(string_ids(e.get('fact_ids')) for e in recent))
        for fid, fact in state['facts'].items():
            ids = set(fact['character_ids'])
            text_words = words(fact['text'])
            score = 100*bool(text_words & topic_words) + 60*(fid in event_facts) + 35*bool(text_words & continuity_words)
            score += 40*bool(text_words & location_words) + 30*bool(ids & (scope.structural_actor_ids - core))
            score += 25*(len(ids & core) >= 2)
            score += 80*semantic('facts', fid)
            if score: scope.fact_scores[fid] = score
        ranked = sorted(scope.fact_scores, key=lambda fid: (-scope.fact_scores[fid], fid))
        # High topical/causal facts are mandatory; bounded lower-relevance support.
        scope.fact_ids = ranked[:24]
        # One hop: identify actors attached to retrieved facts, without expanding
        # back into their other facts, relationships or knowledge.
        neighbors = sorted({cid for fid in scope.fact_ids if semantic('facts', fid) for cid in state['facts'][fid]['character_ids']} - core)[:6]
        scope.referenced_actor_ids.update(neighbors)
        scope.relevant_actor_ids |= set(neighbors)
        facts = set(scope.fact_ids)
        scope.knowledge_ids = [key for key, row in state['knowledge'].items()
                               if row['actor_id'] in (scope.relevant_actor_ids if completed_narrative is not None else core) and row['fact_id'] in facts]
        scope.relationship_pairs = [key for key, r in state['relationships'].items()
                                    if r['source_id'] in scope.relevant_actor_ids and r['target_id'] in scope.relevant_actor_ids
                                    and (r['source_id'] in core or r['target_id'] in core)]
        from backend.runtime_v3.history_selector import HistorySelector
        scope.history_events = HistorySelector(state, world_history).select_scope(scope, 2400)
        scope.event_ids = [e['id'] for e in scope.history_events if isinstance(e.get('id'), str)]
        for cid in scope.relevant_actor_ids:
            if cid in scope.present_actor_ids: scope.reason('characters', cid, 'PRESENT')
            if cid in scope.remote_actor_ids: scope.reason('characters', cid, 'REMOTE')
            if cid in scope.active_actor_ids: scope.reason('characters', cid, 'ACTIVE_NARRATIVE')
            if mentions(query, names.get(cid, [])): scope.reason('characters', cid, 'EXPLICIT_MENTION')
            if any(mentions(v.get('assistant_text', ''), names.get(cid, [])) for v in recent_views[-3:]): scope.reason('characters', cid, 'CONTINUITY')
            if mentions(motivations, names.get(cid, [])): scope.reason('characters', cid, 'MOTIVATION')
            if any(cid in state['threads'][tid]['character_ids'] for tid in scope.thread_ids): scope.reason('characters', cid, 'THREAD')
        for fid in scope.fact_ids:
            text_words = words(state['facts'][fid]['text'])
            if text_words & topic_words: scope.reason('facts', fid, 'TOPIC')
            if text_words & continuity_words: scope.reason('facts', fid, 'CONTINUITY')
            if fid in event_facts: scope.reason('facts', fid, 'HISTORY')
            if not scope.selection_reasons.get(('facts', fid)): scope.reason('facts', fid, 'RELATIONSHIP')
        for kind, ids, reason in [('locations', scope.location_ids, 'SCENE'), ('threads', scope.thread_ids, 'THREAD'),
                ('scheduled_events', scope.scheduled_event_ids, 'SCHEDULED'), ('history_events', scope.event_ids, 'HISTORY'),
                ('relationships', scope.relationship_pairs, 'RELATIONSHIP'), ('knowledge', scope.knowledge_ids, 'KNOWLEDGE_BOUNDARY')]:
            for eid in ids: scope.reason(kind, eid, reason)
        return scope
