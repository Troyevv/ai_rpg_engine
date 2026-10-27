"""Read projections of the one canonical history, including conservative legacy routing."""
import json


def route(snapshot, kind, config=None):
    state = snapshot.get('world_state', {})
    camera = state.get('camera', {})
    actor = camera.get('controlled_actor_id')
    base = dict(surface='physical', actor_id=actor, call_id=None)
    if kind == 'communication':
        source = state.get('remote_events', {}).get((config or {}).get('communication', {}).get('source_event_id'), {})
        return dict(base, surface='phone', conversation_id=source.get('conversation_id'),
                    call_id=source.get('id') if source.get('channel') == 'VOICE_CALL' else None)
    if kind != 'turn' or not state: return base
    from backend.runtime_v3.remote import active_call
    call = active_call(state, actor)
    channel = (config or {}).get('interaction_channel', state.get('meta', {}).get('interaction_focus'))
    if channel == 'call' and call and call['status'] == 'answered':
        return dict(base, surface='call', call_id=call['id'])
    return base


def job_route(job):
    return route(json.loads(job.get('before_json') or '{}'), job.get('kind'),
                 json.loads(job.get('config_json') or '{}'))


def committed_route(job, history):
    result = job_route(job)
    if result['surface'] == 'call':
        # Only accepted, explicitly physical Events can cross into the story.
        # Missing legacy tags are ambiguous, never guessed from literary text.
        physical = [e for e in (history or {}).get('events', []) if e.get('interaction_channel') == 'physical']
        result['physical_text'] = '\n\n'.join(e['text'] for e in physical)
        text = job.get('narrative', '')
        for event in physical:
            # An accepted exact excerpt is a span, never a phrase classifier.
            if event.get('evidence') and event['evidence'] in text:
                text = text.replace(event['evidence'], '', 1)
        result['call_text'] = text.strip()
    return result


def visible_changes(changes, state, actor):
    """Read-only diagnostics summary must not preload unread phone consequences."""
    from copy import deepcopy
    from backend.runtime_v3.remote import commitment_visible, authored_record_visible
    result=deepcopy(changes)
    raw=result.get('raw_turn_result', {})
    records=raw.get('records', raw)
    if 'scheduled_event_changes' in records:
        records['scheduled_event_changes']=[r for r in records['scheduled_event_changes'] if commitment_visible(state,r,actor)]
    for r in records.get('character_changes', []):
        if 'intentions_updates' in r:
            r['intentions_updates']=[v for v in r['intentions_updates'] if authored_record_visible(state,v,actor)]
    upserts=result.get('state_patch',{}).get('upserts',{})
    if 'scheduled_events' in upserts:
        upserts['scheduled_events']={k:v for k,v in upserts['scheduled_events'].items() if commitment_visible(state,v,actor)}
    for c in upserts.get('characters',{}).values():
        for key in ('goals','intentions','obligations'):
            if key in c:c[key]=[v for v in c[key] if authored_record_visible(state,v,actor)]
    return result
