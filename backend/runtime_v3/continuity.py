"""Bounded projections of existing History for Director and Resolver.

No clock, planner, text similarity or independent canonical memory. Semantic
claims come from the normal Extraction; accepted events own their provenance.
"""
from copy import deepcopy
from hashlib import sha256
import json
from typing import Literal
from pydantic import Field
from backend.runtime_v3.models import StrictModel, fatal
from backend.runtime_v3.calendar import scheduled_boundary
from backend.runtime_v3.commitments import temporal_boundaries


class ContinuityBeat(StrictModel):
    source_event_id: str
    actor_id: str
    target_ids: list[str] = Field(default_factory=list, max_length=8)
    basis_ids: list[str] = Field(min_length=1, max_length=4)
    kind: Literal['question', 'proposal', 'information', 'decision', 'opportunity']
    status: Literal['open', 'resolved', 'rejected']
    evidence: str
    decision_actor_id: str | None = None
    player_evidence: str = Field(default='', description='EACH EXTERNAL decision needs its own full input quote.')


class SceneTransition(StrictModel):
    source_event_id: str
    phase: Literal['started', 'advanced', 'ended']
    actor_ids: list[str] = Field(min_length=1, max_length=8)
    thread_ids: list[str] = Field(default_factory=list, max_length=6)
    evidence: str


class Compression(StrictModel):
    kind: Literal['waiting', 'travel', 'work', 'routine']
    evidence: str
    response_event_id: str | None = None
    player_evidence: str = ''


class DueBirthAssessment(StrictModel):
    """Extraction's reading of immutable prose, not a second birth mechanism."""
    pregnancy_id: str
    narrative_outcome: Literal['ongoing', 'completed', 'unresolved_time_advance']
    evidence: str = ''


def reject(code, **path):
    fatal('Нарушена непрерывность повествования.', code, repairable=False, **path)


def bases(state):
    rows = {key: row for section in ('facts', 'threads', 'scheduled_events', 'roles',
            'residences', 'conditions', 'objective_relations') for key, row in state[section].items()}
    rows.update({r['id']: r for c in state['characters'].values()
                 for field in ('goals', 'intentions', 'obligations') for r in c[field]})
    return rows


def fingerprint(rows, ids):
    # Only structured lifecycle/content, never fuzzy prose similarity. Changes to
    # an unrelated actor or clock cannot make an answered question novel again.
    return sha256(json.dumps([rows.get(key) for key in sorted(ids)],
        sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def beat_key(row):
    return (row['kind'], row['actor_id'], tuple(sorted(row.get('target_ids', []))),
            tuple(sorted(row['basis_ids'])))


def visible_event(state, observer, event):
    witnesses = event.get('witnesses')
    if observer is None or isinstance(witnesses, list) and observer in witnesses: return True
    facts = event.get('fact_ids', [])
    if not isinstance(facts, list) or any(not isinstance(fid, str) for fid in facts): return False
    return bool(facts) and all(state['knowledge'].get(observer+':'+fid, {}).get('status') == 'known' for fid in facts)


def project(state, scope, history=None):
    """Bounded tail, already limited to the active immutable History lineage."""
    history = history or {}
    rows = bases(state)
    core = scope.present_actor_ids | scope.remote_actor_ids | scope.active_actor_ids
    observer = scope.pov_actor_id or scope.controlled_actor_id
    beats, responses = {}, []
    read = history.get('_continuity_query')
    selected = scope.thread_ids + scope.fact_ids + scope.scheduled_event_ids + scope.role_ids + scope.residence_ids
    selected += [source['fact_id'] for source in scope.development_sources if source.get('fact_id')]
    archive = read(selected) if read else []
    for event in archive + history.get('events', [])[-128:]:
        if not isinstance(event, dict) or not visible_event(state, observer, event): continue
        participants = event.get('participants')
        if not isinstance(participants, list) or any(not isinstance(cid, str) for cid in participants) or not core.intersection(participants): continue
        for row in event.get('continuity', [])[:8]:
            if not isinstance(row, dict) or not isinstance(row.get('basis_ids'), list) or not isinstance(row.get('actor_id'), str) or row.get('kind') not in ('question','proposal','information','decision','opportunity'): continue
            if any(not isinstance(key, str) or key not in rows for key in row['basis_ids']): continue
            if observer and any(not actor_knows_dialogue_basis(state, rows, key, observer) for key in row['basis_ids']):
                continue
            if row.get('basis_digest') == fingerprint(rows, row['basis_ids']):
                beats[beat_key(row)] = {key:value for key,value in row.items() if key not in ('evidence','player_evidence')}
        action = event.get('scene_action', {})
        if action.get('response') == 'open' and scope.controlled_actor_id in action.get('target_ids', []):
            responses.append(dict(event_id=event['id'], turn_id=event.get('turn_id')))
    turns = [r for r in history.get('turns', [])[-16:] if r.get('player_observed')
             and r.get('camera', {}).get('controlled_actor_id') == scope.controlled_actor_id]
    recent = [r.get('continuity') for r in turns[-6:] if r.get('continuity')]
    signature = scene_signature(state)
    repeated = [r for r in recent if r.get('scene') == signature and not r.get('progress')]
    # Evidence of repeating the same interaction state, not just elapsed turns.
    pressure = round(min(.25, max(0, len(repeated)-2)*.0625), 4)
    resolved = {r['source_event_id'] for r in beats.values() if r['status'] != 'open'}
    answered = {eid for turn in turns for eid in turn.get('continuity', {}).get('answered_response_ids', [])}
    pending = [r['event_id'] for r in responses if r['event_id'] not in resolved | answered][-4:]
    pending += [r['source_event_id'] for r in beats.values() if r['status'] == 'open'
                and scope.controlled_actor_id in r.get('target_ids', [])
                and r['source_event_id'] not in answered]
    pending = list(dict.fromkeys(pending))[-4:]
    terminal = [dict(id=t['id'], status=t['status']) for t in state['threads'].values()
                if t['status'] in ('resolved', 'dormant', 'paused') and core.intersection(t['character_ids'])][:8]
    return dict(pressure=pressure, ordinary_scene_valid=True,
        recent_beats=list(beats.values())[-16:], pending_response_ids=pending,
        closed_threads=terminal, compression=compression_limit(state, core), extra_llm_calls=0)


def scene_signature(state):
    camera = state['camera']
    return [camera['location_id'], sorted(camera['present_character_ids']), camera['controlled_actor_id']]


def compression_limit(state, actors, max_minutes=30):
    now = state['meta']['world_time']
    limit = max_minutes
    boundaries = []
    for event in temporal_boundaries(state):
        due = event['due_minute']
        relevant = bool(set(event['character_ids']) & actors or event.get('interrupts') or
                        event.get('location_id') and event['location_id'] == state['camera']['location_id'])
        if relevant and due <= now+limit:
            remaining = max(0, due-now)
            if remaining < limit:
                boundaries.clear()
            limit = remaining
            boundaries.append(event['id'])
    return dict(max_minutes=limit, boundary_ids=sorted(boundaries))


def recorded(messages):
    for message in messages:
        if message['content'].startswith('Director / GM-only\n'):
            return deepcopy(json.loads(message['content'].split('\n', 1)[1]).get('continuity', {}))
    return {}


def ordinary_clock_actors(state):
    camera = state['camera']
    return {*camera['present_character_ids'], camera['controlled_actor_id'],
            *(r['actor_id'] for r in camera.get('remote_interactions', []))}


def due_births_in_scene_clock(state):
    """Use the same canonical boundaries as the ordinary turn guard, including old saves."""
    if not state.get('pregnancies'):
        return []
    due_ids = compression_limit(state, ordinary_clock_actors(state), 0)['boundary_ids']
    return [state['pregnancies'][pid] for pid in due_ids if pid in state['pregnancies']]


def due_birth_repair_required(diagnostics):
    """Keep the repair obligation across a saved job's extraction-only retry."""
    return any(row.get('code') == 'ordinary_temporal_boundary'
               and row.get('temporal_boundary', {}).get('due_birth_repair') for row in diagnostics)


def validate_due_birth_assessments(resolver, raw, *, require=False):
    if resolver.mode == 'background' or resolver.runtime_time_skip:
        return
    rows = raw.final_scene.get('due_birth_assessments')
    if rows is None and not require:
        return  # Older payloads/saved contexts remain compatible.
    path = dict(section='final_scene', path='final_scene.due_birth_assessments')
    try:
        if not isinstance(rows, list):
            raise ValueError('Due birth repair requires a Narrative assessment.')
        claims = [DueBirthAssessment.model_validate(row) for row in rows]
        expected = {p['id'] for p in due_births_in_scene_clock(resolver.before)}
        if len(claims) != len(expected) or {c.pregnancy_id for c in claims} != expected:
            raise ValueError('Assess each current due pregnancy exactly once.')
        births = {b.get('pregnancy_id') for b in raw.records['births'] if isinstance(b, dict)}
        for claim in claims:
            if claim.narrative_outcome == 'unresolved_time_advance':
                fatal('Narrative требует продвижения времени через неразрешённые роды; Extraction не может переписать сцену.',
                      'narrative_temporal_conflict', repairable=False, action='reauthor_narrative',
                      entity=claim.pregnancy_id, **path)
            if (claim.narrative_outcome == 'completed') != (claim.pregnancy_id in births):
                raise ValueError('BirthClaim must agree with the Narrative assessment; ongoing labor is not birth_completed.')
    except (ValueError, TypeError) as exc:
        from backend.services.world_delta_errors import StructuralDeltaError
        if isinstance(exc, StructuralDeltaError):
            raise
        fatal(str(exc), 'due_birth_assessment_invalid', repairable=True, **path)


def validate_temporal_boundaries(resolver, elapsed):
    """Ordinary-turn guard, independent of Extraction's compression claim.

    Future boundaries may be reached, never crossed. Already due plans and
    pending responses must be addressed by accepted canonical changes before
    time advances. Validate after domain handlers, before returning a patch.
    Time Skip has a Runtime-owned target; background/LTA own their clock outside
    this ordinary-turn path. Only an already-due birth boundary permits bounded
    reinterpretation; the repair must assess the unchanged Narrative explicitly.
    """
    if resolver.mode == 'background' or resolver.runtime_time_skip or not elapsed:
        return
    state = resolver.before
    actors = ordinary_clock_actors(state)
    now = state['meta']['world_time']
    boundaries = dict(state['scheduled_events'])
    for eid, event in state['scheduled_events'].items():
        due = scheduled_boundary(state, event)
        updated = resolver.state['scheduled_events'].get(eid, event)
        next_due = scheduled_boundary(resolver.state, updated)
        if due is not None and due <= now and updated != event and (
            updated['status'] != 'pending' or next_due is not None and next_due > now
        ):
            boundaries[eid] = updated
    # Only already-due processes can be discharged during this turn. Keep
    # future boundaries from before, even if Extraction claims a later birth.
    pregnancies = {
        pid: resolver.state['pregnancies'][pid] if p['due_minute'] <= now else p
        for pid, p in state['pregnancies'].items()
    }
    boundary = compression_limit(dict(state, scheduled_events=boundaries, pregnancies=pregnancies),
                                 actors, elapsed)
    if elapsed > boundary['max_minutes']:
        rows = [event for event in temporal_boundaries(dict(state,
            scheduled_events=boundaries, pregnancies=pregnancies))
            if event['id'] in boundary['boundary_ids']]
        repairable = bool(rows) and all(event['id'] in pregnancies
            and pregnancies[event['id']]['status'] != 'born'
            and event['due_minute'] <= now for event in rows)
        detail = dict(world_time=now, elapsed_minutes=elapsed,
            max_minutes=boundary['max_minutes'], due_birth_repair=repairable,
            boundaries=[dict(id=e['id'], kind=e.get('type'), due_minute=e['due_minute']) for e in rows])
        fatal('Обычный ход пересекает неразрешённую временную границу. '
              'Повторно интерпретируй исходный Narrative; не выдумывай рождение или длительность.',
              'ordinary_temporal_boundary', repairable=repairable, section='final_scene',
              path='final_scene.elapsed_minutes', source_ids=boundary['boundary_ids'], temporal_boundary=detail)


def validate_compression(resolver, scene, elapsed):
    if 'compression' not in scene or resolver.mode == 'background' or resolver.runtime_time_skip: return
    try:
        claim = Compression.model_validate(scene['compression'])
    except (ValueError, TypeError):
        resolver.warn('final_scene', 0, 'Необязательная аннотация сжатия отклонена.', 'compression', code='compression_invalid'); return
    if elapsed <= 0:
        resolver.warn('final_scene', 0, 'Нулевая длительность без сжатия.', 'compression', code='compression_boundary'); return
    resolver.history.state_changes.append(dict(kind='natural_compression', minutes=elapsed,
        routine=claim.kind, evidence=claim.evidence, turn_id=resolver.turn_id))


def player_targets_match(resolver, claim, event):
    """A witness in a conversation cannot become the player's chosen addressee.

    New Events carry the reviewed action. Older canonical records are not rewritten;
    their existing provenance checks remain in force. NPC-led proposals reverse the
    initiator/recipient roles, so compare the counterparties of the player response.
    """
    action = event.get('player_action')
    if action is None:
        return True
    counterparties = {claim.actor_id, *claim.target_ids} - {resolver.protected_actor_id}
    return counterparties <= set(action['narrative_target_ids'])


def dialogue_evidence_matches(resolver, claim, event):
    """A completed player interaction proves dialogue, never a separate decision."""
    from backend.runtime_v3.resolver import normalized

    if not player_targets_match(resolver, claim, event):
        return False
    if event['medium'] == 'message' and event.get('author_id') != claim.actor_id:
        return False
    action = event.get('scene_action')
    if action and action['actor_id'] not in (claim.actor_id, claim.decision_actor_id):
        return False
    if not claim.evidence.strip() or not event['evidence'].strip():
        return False
    # The Resolver sets player_interaction only for a current-input quote on
    # this accepted Event with the protected actor among its participants.
    event_quote = normalized(event['player_evidence']) if event.get('player_interaction') else ''
    if claim.decision_actor_id is not None and not event_quote:
        # A two-speaker Event must itself attest to the player's part.
        return False
    if claim.player_evidence:
        quote = normalized(claim.player_evidence)
        return bool(quote) and quote in (event_quote or normalized(resolver.player_input))
    return bool(event_quote)


def npc_decision_matches(claim, event, actor):
    """Check who acted on the accepted Event; participant membership is insufficient."""
    action = event.get('scene_action') or {}
    if not claim.evidence.strip() or not event['evidence'].strip():
        return False
    if event['medium'] == 'message' and event.get('author_id') != actor:
        return False
    if action.get('actor_id') != actor:
        return False
    if claim.kind == 'decision' and claim.actor_id == actor:
        terminal_action = (claim.status == 'resolved' and action['phase'] in ('accept', 'refuse', 'redirect', 'end')
                           or claim.status == 'rejected' and action['phase'] == 'refuse')
        return terminal_action and set(claim.target_ids) <= set(action['target_ids'])
    if actor not in claim.target_ids or claim.actor_id not in action['target_ids']:
        return False
    if claim.status == 'rejected':
        return claim.kind in ('proposal', 'question') and action['phase'] == 'refuse'
    return claim.status == 'resolved' and (claim.kind, action['phase']) in {
        ('proposal', 'accept'), ('question', 'answer'),
    }


def validate_player_decision(resolver, claim, event, index):
    """Bind Extraction's decision classification to one accepted input/Event.

    Quotation proves provenance, not semantics. Extraction owns the meaning of
    kind/status and must preserve the whole choice (including negation). Never
    borrow a quote from another Event or fill a missing quote in Runtime.
    """
    from backend.runtime_v3.resolver import normalized

    def invalid(field, reason):
        fatal(reason, 'continuity_external_decision', repairable=True,
              section='continuity_beats', index=index, field=field, entity=claim.source_event_id)

    quote = normalized(claim.player_evidence)
    if not quote or quote not in normalized(resolver.player_input):
        invalid('player_evidence', 'Укажите собственную полную цитату текущего player_input, '
                'подтверждающую именно это решение. Не копируйте чужое действие/согласие; '
                'если решения нет, не утверждайте его при повторной Extraction.')
    external = resolver.protected_actor_id
    # Preserve the older quote-only guard on optional opportunities; the stricter
    # Event/decider contract applies to decisions, not every annotation kind.
    if claim.kind != 'decision' and claim.decision_actor_id != external:
        return
    if claim.decision_actor_id != external:
        invalid('decision_actor_id', 'Укажите фактического автора решения; участие игрока не доказывает решение NPC.')
    actors = {claim.actor_id, *claim.target_ids, external}
    if not event or not actors <= set(event['participants']):
        invalid('source_event_id', 'Решение должно ссылаться на принятый Event этого хода с теми же участниками.')
    if (not event.get('player_interaction') or quote != normalized(event.get('player_evidence', ''))
            or event['medium'] == 'message' and event.get('author_id') != external):
        invalid('player_evidence', 'Цитата решения должна совпадать с player_evidence связанного '
                'completed_interaction Event. Разные действия оформляются отдельными Events/beats.')
    if not player_targets_match(resolver, claim, event):
        invalid('target_ids', 'Адресат решения должен соответствовать проверенному действию Event; '
                'присутствие другого участника разговора не делает его адресатом.')
    # Descriptive evidence may quote just this choice inside a longer conversation.
    # Comparing prose (even by substring) proves neither its author nor its meaning.
    # The accepted interaction and its complete player quote above own provenance.
    if not normalized(claim.evidence) or not normalized(event['evidence']):
        invalid('evidence', 'Укажите evidence решения и связанного принятого Event.')
    if claim.status == 'open':
        invalid('status', 'Нерешённый вопрос/предложение не является завершённым решением игрока. '
                'Сохраните ожидание ответа без выдуманного decision_actor_id.')


def actor_knows_dialogue_basis(state, rows, key, actor):
    from backend.runtime_v3.kinship import knowledge_status

    row = rows[key]
    if key in state['facts']:
        return knowledge_status(state, actor, key) == 'known'
    if key in state['threads']:
        observers = state['threads'][key]['discovered_by']
        return observers is None or actor in observers
    if key in state['scheduled_events']:
        return actor in state['scheduled_events'][key]['character_ids']
    # Social state and conditions may be backed by Knowledge, including a
    # distinct fact for a closure. Do not infer awareness from World Truth.
    if 'fact_id' in row:
        required = [row['fact_id']]
        if row.get('closure_fact_id'):
            required.append(row['closure_fact_id'])
        return all(knowledge_status(state, actor, fid) == 'known' for fid in required)
    return any(item['id'] == key for field in ('goals', 'intentions', 'obligations')
               for item in state['characters'][actor][field])


def apply(resolver, raw, events):
    """Accepted transitions invalidate stale summaries, never invent endpoints.

    A linked meeting may end while its relationship thread stays developing.
    Explicit field updates remain owned by the ordinary domain handlers.
    """
    before, state = resolver.before, resolver.state
    if len(raw.records['scene_transitions']) > 8 or len(raw.records['continuity_beats']) > 8:
        resolver.warn('continuity_beats', 0, 'Превышен рекомендованный бюджет аннотаций.', code='continuity_budget')
    changed_actors, changed_threads = set(), set()
    for row in raw.records['scene_transitions']:
        try: claim = SceneTransition.model_validate(row)
        except (ValueError, TypeError):
            resolver.warn('scene_transitions', 0, 'Повреждена аннотация.', code='scene_transition_invalid'); continue
        event = events.get(claim.source_event_id)
        if not event or not resolver.supported(row) or not set(claim.actor_ids) <= set(event['participants']):
            resolver.warn('scene_transitions', 0, 'Нет связанного Event.', code='scene_transition_evidence'); continue
        if any(tid not in state['threads'] or not set(claim.actor_ids) & set(state['threads'][tid]['character_ids']) for tid in claim.thread_ids):
            resolver.warn('scene_transitions', 0, 'Нет связанной линии.', code='scene_transition_thread'); continue
        changed_actors.update(claim.actor_ids)
        changed_threads.update(claim.thread_ids)
        event['scene_transition'] = dict(phase=claim.phase, actor_ids=claim.actor_ids, thread_ids=claim.thread_ids)
    # Structural movement evidence also invalidates an unchanged location-bound
    # situation, even if Extraction omitted the redundant transition annotation.
    changed_actors.update(r['actor_id'] for r in resolver.history.movements)
    changed_actors.update(set(before['camera']['present_character_ids']) ^ set(state['camera']['present_character_ids']))
    for cid in changed_actors:
        if cid in before['characters'] and state['characters'][cid]['situation'] == before['characters'][cid]['situation']:
            state['characters'][cid]['situation'] = ''
    for tid in changed_threads:
        old = before['threads'].get(tid)
        if old and state['threads'][tid]['state'] == old['state']:
            state['threads'][tid]['state'] = ''
    for row in raw.records['thread_changes']:
        if not isinstance(row, dict): continue
        if not isinstance(row.get('id'), str): continue
        old, new = before['threads'].get(row['id']), state['threads'].get(row['id'])
        if old and new and old['status'] == 'resolved' and new['status'] != 'resolved':
            event = events.get(row.get('source_event_id'))
            if not event or event['id'] == old.get('source_event_id') or not set(event['participants']) & set(new['character_ids']):
                reject('thread_reopen_requires_event')
        if new and isinstance(row.get('source_event_id'), str) and row['source_event_id'] in events:
            new['source_event_id'] = events[row['source_event_id']]['id']
    rows = bases(state)
    prior = {beat_key(r): r for r in (resolver.continuity_decision or {}).get('recent_beats', [])}
    external = resolver.protected_actor_id
    accepted_beats = {}
    for index, row in enumerate(raw.records['continuity_beats']):
        try: claim = ContinuityBeat.model_validate(row)
        except (ValueError, TypeError):
            if (isinstance(row, dict) and external is not None
                    and (row.get('decision_actor_id') == external
                         or row.get('kind') == 'decision' and row.get('actor_id') == external)):
                fatal('Повреждена аннотация действия игрока; проверьте типы и источник решения.',
                      'continuity_external_decision', repairable=resolver.mode != 'background',
                      section='continuity_beats', index=index)
            resolver.warn('continuity_beats', index, 'Повреждена аннотация.', code='continuity_beat_invalid'); continue
        player_owned = external is not None and external in (claim.actor_id, claim.decision_actor_id)
        player_dialogue = (claim.actor_id == external and claim.decision_actor_id != external
                           and claim.kind in ('question', 'proposal', 'information'))
        event = events.get(claim.source_event_id)
        if player_owned and (resolver.mode == 'background' or not player_dialogue):
            if resolver.mode == 'background':
                reject('continuity_external_decision', section='continuity_beats', index=index,
                       field='player_evidence', entity=claim.source_event_id)
            validate_player_decision(resolver, claim, event, index)
        actors = {claim.actor_id, *claim.target_ids}
        if claim.decision_actor_id is not None:
            actors.add(claim.decision_actor_id)
        if not event or not actors.issubset(event['participants']):
            resolver.warn('continuity_beats', index, 'Нет принятого Event с указанными участниками.', code='continuity_beat_evidence'); continue
        if any(key not in rows for key in claim.basis_ids):
            resolver.warn('continuity_beats', index, 'Неизвестное основание аннотации.', code='continuity_basis_invalid'); continue
        if player_dialogue and not dialogue_evidence_matches(resolver, claim, event):
            resolver.warn('continuity_beats', index, 'Источник не подтверждает эту реплику игрока.',
                          code='continuity_player_interaction_unconfirmed')
            continue
        decider = claim.decision_actor_id
        if decider is None and claim.kind == 'decision':
            decider = claim.actor_id
        npc_decides = decider is not None and decider != external
        if npc_decides and not npc_decision_matches(claim, event, decider):
            resolver.warn('continuity_beats', index, 'Event не подтверждает решение указанного NPC.',
                          code='continuity_npc_response_unconfirmed')
            continue
        if player_dialogue or npc_decides:
            speakers = {claim.actor_id}
            if npc_decides:
                speakers.add(decider)
            if any(not actor_knows_dialogue_basis(state, rows, key, actor)
                   for actor in speakers for key in claim.basis_ids):
                resolver.warn('continuity_beats', index, 'Основание реплики недоступно участнику.',
                              code='continuity_basis_unavailable')
                continue
        elif any(key in state['facts'] and state['knowledge'].get(claim.actor_id+':'+key, {}).get('status') != 'known'
                 for key in claim.basis_ids):
            reject('continuity_unknown_fact')
        value = claim.model_dump()
        if npc_decides or external is not None and decider == external:
            # Same source ownership as NPC receipts: annotation prose cannot add
            # a foreign quotation to History. Keep the separately validated,
            # mandatory player_evidence; never synthesize or replace it here.
            value['evidence'] = event['evidence']
        value.update(source_event_id=event['id'], basis_digest=fingerprint(rows, claim.basis_ids))
        key = (event['id'], beat_key(value), value['decision_actor_id'])
        if key in accepted_beats:
            if accepted_beats[key] != value:
                fatal('Противоречащие аннотации одного решения в одном Event.',
                      'continuity_beat_conflict', repairable=True, section='continuity_beats', index=index)
            resolver.warn('continuity_beats', index, 'Повторная аннотация этого Event.', code='continuity_duplicate')
            continue
        old = prior.get(beat_key(value))
        if old and old['basis_digest'] == value['basis_digest'] and old['status'] in ('resolved', 'rejected') and claim.status == 'open':
            resolver.warn('continuity_beats', index, 'Повторная аннотация.', code='continuity_repeated_beat'); continue
        event.setdefault('continuity', []).append(value)
        accepted_beats[key] = value
        prior[beat_key(value)] = value


def filter_choices(resolver, choices):
    """Semantic identity is explicitly extracted, not inferred from prose."""
    rows = bases(resolver.state)
    recent = list((resolver.continuity_decision or {}).get('recent_beats', []))
    recent += [r for e in resolver.history.events for r in e.get('continuity', [])]
    blocked = {(r['kind'], tuple(sorted(r['basis_ids']))) for r in recent
               if r['status'] in ('resolved', 'rejected') and r['basis_digest'] == fingerprint(rows, r['basis_ids'])}
    seen, result = set(), []
    for choice in choices:
        ids, kind = choice.get('basis_ids'), choice.get('kind')
        key = None
        if ids:
            if not isinstance(ids, list) or any(not isinstance(k, str) or k not in rows for k in ids):
                resolver.warn('choices', 0, 'Неизвестное основание варианта.', code='choice_basis_invalid'); continue
            if kind not in ('question', 'proposal', 'information', 'decision', 'opportunity'):
                resolver.warn('choices', 0, 'Некорректный смысл варианта.', code='choice_kind_invalid'); continue
            key = (kind, tuple(sorted(ids)))
            if key in blocked: continue
            if any(rows[k].get('status') in ('resolved', 'cancelled', 'completed', 'failed', 'expired', 'closed') for k in ids): continue
        # Exact duplicates are harmless to remove even for legacy choices.
        key = (choice.get('interaction_channel'), key or (choice['action'].strip(), choice.get('speech', '').strip()))
        if key in seen: continue
        seen.add(key)
        result.append({k: choice[k] for k in ('action', 'speech', 'interaction_channel') if k in choice})
    return result


def turn_signal(resolver):
    before, after = resolver.before, resolver.state
    progress = []
    for section in ('knowledge', 'relationships', 'threads', 'scheduled_events', 'roles', 'residences', 'conditions', 'objective_relations'):
        if before[section] != after[section]: progress.append(section)
    if any(before['characters'].get(cid, {}).get(field) != row[field] for cid, row in after['characters'].items()
           for field in ('goals', 'intentions', 'obligations', 'life_status')): progress.append('character_lifecycle')
    if any(e.get('scene_transition') or e.get('continuity') or e.get('scene_action', {}).get('phase') in ('start', 'redirect', 'end', 'refuse', 'offer', 'accept', 'answer') for e in resolver.history.events):
        progress.append('interaction')
    if scene_signature(before) != scene_signature(after): progress.append('scene')
    pending = (resolver.continuity_decision or {}).get('pending_response_ids', [])
    # Only accepted, explicitly linked responses count. Legacy unlinked actions
    # cannot identify which question was answered, even when input was supplied.
    answered = {e['scene_action'].get('response_event_id') for e in resolver.history.events
                if e.get('scene_action', {}).get('response') == 'player_supplied'}
    answered.update(r.get('response_event_id') for r in resolver.history.state_changes
                    if r.get('kind') == 'natural_compression')
    return dict(scene=scene_signature(after), progress=progress,
                answered_response_ids=[eid for eid in pending if eid in answered])
