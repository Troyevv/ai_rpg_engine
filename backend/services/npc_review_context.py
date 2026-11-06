"""Bounded, observer-owned context for a single existing NPC's field proposal.

Narrative's GM-only blocks are deliberately not reused wholesale. We reuse its
POV turn projection and the domain visibility predicates before ranking/bounding.
"""
from copy import deepcopy
import json
from backend.runtime_v3.context import visible_views
from backend.runtime_v3.personality import project_card
from backend.runtime_v3.appearance import project_card as appearance_card
from backend.runtime_v3.kinship import visible_relations
from backend.runtime_v3.residence import visible_social_state
from backend.runtime_v3.remote import authored_record_visible
from backend.runtime_v3.lifecycle import active_texts
from backend.runtime_v3.calendar import current_time


def visible_card(snapshot, cid, observer):
    state = snapshot['world_state']
    card = next(c for c in snapshot['character_cards'] if c['id'] == cid)
    return appearance_card(project_card(card, state['characters'][cid], state=state, observer=observer), state, observer)


def context(snapshot, cid, record, turns, history):
    state = snapshot['world_state']
    observer = state['camera'].get('pov_actor_id') or state['camera']['controlled_actor_id']
    actor = state['characters'][cid]
    known = {k['fact_id']: k['status'] for k in state['knowledge'].values()
             if k['actor_id'] == observer and k['status'] in ('known', 'suspected')}
    # Public classification is not player perception. Only the observer's current
    # Knowledge authorizes facts; neither another NPC's knowledge nor GM truth does.
    def witnessed(event):
        return (observer is not None and observer in event.get('witnesses', [])
                and not event.get('remote_interaction_id')
                and not any(state['facts'].get(fid, {}).get('visibility') == 'secret' and fid not in known
                            for fid in event.get('fact_ids', [])))
    events = [e for e in history.get('events', []) if cid in e.get('participants', []) and witnessed(e)]
    events = [dict(id=e['id'], turn_id=e.get('turn_id'), text=e['text'][:1600],
                   fact_ids=[fid for fid in e.get('fact_ids', []) if fid in known]) for e in events][-16:]
    fact_ids = {fid for e in events for fid in e['fact_ids']}
    facts = [dict(id=fid, status=status, text=state['facts'][fid]['text'][:1200])
             for fid, status in known.items() if fid in state['facts'] and
             (cid in state['facts'][fid]['character_ids'] or fid in fact_ids)][:24]
    owned_sequences = {t['sequence'] for t in turns if t.get('kind') != 'background' and
        observer is not None and (t.get('pov_actor_id') or snapshot.get('campaign',{}).get('protagonist_id')) == observer}
    source_events = {e.get('id'): e for e in history.get('events', [])}
    def perceived(m):
        if not authored_record_visible(state, m, observer): return False
        source = m.get('source_event_id')
        if source in state.get('remote_events', {}): return True
        if source: return witnessed(source_events.get(source, {}))
        # Initial/manual motivations have no private remote source. Ordinary
        # sourced records require their actual witnessed event, not GM summaries.
        sequence = m.get('source_sequence')
        return sequence in owned_sequences if sequence is not None else record['created_turn']-1 in owned_sequences
    def attribute_visible(key):
        for change in reversed(history.get('state_changes', [])):
            after = change.get('upserts', {}).get('characters', {}).get(cid)
            before = change.get('before_characters', {}).get(cid) or {}
            if after is not None and before.get(key) != after.get(key):
                return change.get('player_observed') is True and change.get('turn_id', 0)-1 in owned_sequences
            if change.get('entity') == cid and change.get('kind') in ('npc_review_attributes','birth_date_established','life_changes'):
                before, after = change.get('before') or {}, change.get('after') or {}
                if before.get(key) != after.get(key):
                    return (change.get('evidence') == 'Явная правка в редакторе проверки NPC.' and observer in record['audience_ids']) or change.get('turn_id',0)-1 in owned_sequences
        return record['created_turn']-1 in owned_sequences and actor[key] == record.get('character_baseline',{}).get(key)
    attributes = {k: deepcopy(actor[k]) for k in ('biological_sex','birth_date','life_status',
        'developmental_stage','reproductive_capability','capabilities','identity_components') if attribute_visible(k)}
    if cid in state['camera']['present_character_ids']:
        attributes.update({k:actor[k] for k in ('physical_state','emotion','situation') if attribute_visible(k)})
    for key in ('goals','intentions','obligations'):
        attributes[key] = active_texts([m for m in actor[key] if perceived(m)])[:12]
    # Direct feelings of other people are not the observer's knowledge. Keep the
    # observer's own outgoing relationship; social links use Knowledge projections.
    relationships = [deepcopy(r) for r in state['relationships'].values()
                     if r['source_id'] == observer and r['target_id'] == cid][:8]
    related_turns = {e.get('turn_id') for e in events} | {record['created_turn']}
    # Use the Narrative POV gate and accepted physical reconciliation, never raw
    # background prose or communication transcripts from other participants.
    safe_snapshot = dict(snapshot, world_state=dict(state, camera=dict(state['camera'], pov_actor_id=observer)))
    views = visible_views(safe_snapshot, turns, 'turn') if observer is not None else []
    def participated(view):
        try: changes=json.loads(view.get('changes_json') or '{}')
        except (TypeError,ValueError): return False
        return cid in changes.get('state_patch',{}).get('camera',{}).get('present_character_ids',[])
    relevant = [v for v in views if v.get('sequence', -1) + 1 in related_turns or participated(v)]
    introduction = [v for v in relevant if v.get('sequence', -1) + 1 == record['created_turn']]
    selected = introduction[:1] + [v for v in relevant if v not in introduction][-4:]
    prose = [dict(sequence=v['sequence'], player_input=v.get('user_text','')[:800],
                  narrative=v.get('assistant_text','')[:4000]) for v in selected]
    card = visible_card(snapshot, cid, observer)
    # Explicit sizes are local context limits, never limits on stored prose.
    card['fields'] = {k:v[:2000] for k,v in card['fields'].items()}
    social = visible_social_state(state, observer, {cid})
    return dict(observer_id=observer, time=current_time(state), character=attributes,
                current_card=card, facts=facts, events=events, witnessed_narrative=prose,
                relationships=relationships, social_relations=[r for r in visible_relations(state, observer)
                    if cid in (r['source_id'],r['target_id'])][:24],
                **{k:v[:16] for k,v in social.items()})


def profile_state(snapshot, cid):
    """Opaque CAS signatures + existing POV-safe display; never expose raw sources."""
    from backend.runtime_v3.models import identity
    from backend.runtime_v3.personality import CARD_FIELDS
    observer = snapshot['world_state']['camera']['controlled_actor_id']
    actor = snapshot['world_state']['characters'][cid]
    card = visible_card(snapshot, cid, observer)
    result = {}
    personality = actor.get('personality') or {}
    fields = {item['field'] for item in personality.get('items', {}).values()}
    for field, label in CARD_FIELDS.items():
        if field in fields or personality.get('applied'):
            result[label] = dict(text=card['fields'].get(label, ''), revision=identity('review_profile', field, personality))
    appearance = actor['appearance']
    if any(appearance.get(k) for k in ('items','legacy_text','applied')):
        result['Внешность'] = dict(text=card['fields'].get('Внешность',''),revision=identity('review_profile','appearance',appearance))
    return result


def validate_profiles(snapshot, cid, fields, acknowledgements):
    conflicts = [field for field, current in profile_state(snapshot, cid).items()
                 if field in fields and fields[field] != current['text'] and acknowledgements.get(field) != current['revision']]
    if conflicts:
        raise ValueError('Канонический профиль отличается: '+', '.join(conflicts)+'. Сравни тексты и явно сохрани актуальный профиль.')
