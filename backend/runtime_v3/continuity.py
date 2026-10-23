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
from backend.runtime_v3.commitments import commitment_ready


class ContinuityBeat(StrictModel):
    source_event_id: str
    actor_id: str
    target_ids: list[str] = Field(default_factory=list, max_length=8)
    basis_ids: list[str] = Field(min_length=1, max_length=4)
    kind: Literal['question', 'proposal', 'information', 'decision', 'opportunity']
    status: Literal['open', 'resolved', 'rejected']
    evidence: str
    decision_actor_id: str | None = None
    player_evidence: str = ''


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


def reject(code):
    fatal('Нарушена непрерывность повествования.', code, repairable=False)


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
    for event in state['scheduled_events'].values():
        due = scheduled_boundary(state, event)
        if not commitment_ready(state, event) or due is None: continue
        relevant = bool(set(event['character_ids']) & actors or event.get('interrupts') or
                        event.get('location_id') and event['location_id'] == state['camera']['location_id'])
        if relevant and due <= now+limit:
            limit = max(0, due-now)
            boundaries = [event['id']]
    return dict(max_minutes=limit, boundary_ids=boundaries)


def recorded(messages):
    for message in messages:
        if message['content'].startswith('Director / GM-only\n'):
            return deepcopy(json.loads(message['content'].split('\n', 1)[1]).get('continuity', {}))
    return {}


def validate_temporal_boundaries(resolver, elapsed):
    """Ordinary-turn guard, independent of Extraction's compression claim.

    Future boundaries may be reached, never crossed. Already due plans and
    pending responses must be addressed by accepted canonical changes before
    time advances. Validate after domain handlers, before returning a patch.
    Time Skip has a Runtime-owned target; background/LTA own their clock outside
    this ordinary-turn path. Never repair only elapsed time under unchanged prose.
    """
    if resolver.mode == 'background' or resolver.runtime_time_skip or not elapsed:
        return
    state = resolver.before
    actors = set(state['camera']['present_character_ids'])
    actors.add(state['camera']['controlled_actor_id'])
    actors.update(r['actor_id'] for r in state['camera'].get('remote_interactions', []))
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
    boundary = compression_limit(dict(state, scheduled_events=boundaries), actors, elapsed)
    if elapsed > boundary['max_minutes']:
        fatal('Обычный ход пересекает временную границу договорённости.',
              'ordinary_temporal_boundary', repairable=False)
    pending = set((resolver.continuity_decision or {}).get('pending_response_ids', []))
    answered = set(turn_signal(resolver)['answered_response_ids'])
    if pending - answered:
        fatal('Обычный ход пропускает неразрешённую возможность ответа.',
              'ordinary_response_boundary', repairable=False)


def validate_compression(resolver, scene, elapsed):
    if 'compression' not in scene or resolver.mode == 'background' or resolver.runtime_time_skip: return
    try: claim = Compression.model_validate(scene['compression'])
    except (ValueError, TypeError): reject('compression_invalid')
    permit = resolver.continuity_decision or {}
    limit = min(permit.get('compression', {}).get('max_minutes', 0),
                compression_limit(resolver.before, set(resolver.before['camera']['present_character_ids']))['max_minutes'])
    if not 0 < elapsed <= limit or not resolver.supported(claim.model_dump()): reject('compression_boundary')
    pending = permit.get('pending_response_ids', [])
    if pending:
        from backend.runtime_v3.resolver import normalized
        if len(pending) != 1 or claim.response_event_id not in pending or not normalized(claim.player_evidence) or normalized(claim.player_evidence) not in normalized(resolver.player_input):
            reject('compression_response_required')
    resolver.history.state_changes.append(dict(kind='natural_compression', minutes=elapsed,
        routine=claim.kind, evidence=claim.evidence, turn_id=resolver.turn_id,
        response_event_id=claim.response_event_id if pending else None))


def apply(resolver, raw, events):
    """Accepted transitions invalidate stale summaries, never invent endpoints.

    A linked meeting may end while its relationship thread stays developing.
    Explicit field updates remain owned by the ordinary domain handlers.
    """
    before, state = resolver.before, resolver.state
    if len(raw.records['scene_transitions']) > 8 or len(raw.records['continuity_beats']) > 8:
        reject('continuity_budget')
    changed_actors, changed_threads = set(), set()
    for row in raw.records['scene_transitions']:
        try: claim = SceneTransition.model_validate(row)
        except (ValueError, TypeError): reject('scene_transition_invalid')
        event = events.get(claim.source_event_id)
        if not event or not resolver.supported(row) or not set(claim.actor_ids) <= set(event['participants']):
            reject('scene_transition_evidence')
        for tid in claim.thread_ids:
            thread = state['threads'].get(tid)
            if not thread or not set(claim.actor_ids) & set(thread['character_ids']): reject('scene_transition_thread')
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
    for row in raw.records['continuity_beats']:
        try: claim = ContinuityBeat.model_validate(row)
        except (ValueError, TypeError): reject('continuity_beat_invalid')
        event = events.get(claim.source_event_id)
        if not event or not resolver.supported(row) or not {claim.actor_id, *claim.target_ids} <= set(event['participants']):
            reject('continuity_beat_evidence')
        if any(key not in rows for key in claim.basis_ids): reject('continuity_basis_invalid')
        if claim.actor_id == resolver.protected_actor_id or claim.decision_actor_id == resolver.protected_actor_id:
            from backend.runtime_v3.resolver import normalized
            if resolver.mode == 'background' or not normalized(claim.player_evidence) or normalized(claim.player_evidence) not in normalized(resolver.player_input):
                reject('continuity_external_decision')
        # Fact-based assertions must respect the speaking actor's own knowledge.
        for key in claim.basis_ids:
            if key in state['facts'] and state['knowledge'].get(claim.actor_id+':'+key, {}).get('status') != 'known':
                reject('continuity_unknown_fact')
        value = claim.model_dump()
        value.update(source_event_id=event['id'], basis_digest=fingerprint(rows, claim.basis_ids))
        old = prior.get(beat_key(value))
        if old and old['basis_digest'] == value['basis_digest'] and old['status'] in ('resolved', 'rejected') and claim.status == 'open':
            reject('continuity_repeated_beat')
        event.setdefault('continuity', []).append(value)
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
        key = key or (choice['action'].strip(), choice.get('speech', '').strip())
        if key in seen: continue
        seen.add(key)
        result.append({k: choice[k] for k in ('action', 'speech') if k in choice})
    return result


def turn_signal(resolver):
    before, after = resolver.before, resolver.state
    progress = []
    for section in ('knowledge', 'relationships', 'threads', 'scheduled_events', 'roles', 'residences', 'conditions', 'objective_relations'):
        if before[section] != after[section]: progress.append(section)
    if any(before['characters'].get(cid, {}).get(field) != row[field] for cid, row in after['characters'].items()
           for field in ('goals', 'intentions', 'obligations', 'life_status')): progress.append('character_lifecycle')
    if any(e.get('scene_transition') or e.get('continuity') or e.get('scene_action', {}).get('phase') in ('start', 'redirect', 'end', 'refuse', 'offer') for e in resolver.history.events):
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
