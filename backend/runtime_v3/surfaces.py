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
        physical = sorted([e for e in (history or {}).get('events', []) if e.get('interaction_channel')=='physical' and result['actor_id'] in e.get('witnesses',[])], key=lambda e:(e.get('turn_id',0),e.get('order',0)))
        result['physical_events'] = [{k:e[k] for k in ('id','source_record_id','turn_id','order','minute','physical_text','witnesses')} for e in physical if e.get('physical_text')]
        # Preserve accepted legacy cards without fabricating new projection provenance.
        result['physical_text'] = '\n\n'.join(e.get('physical_text',e['text']) for e in physical)
        text = job.get('narrative', '')
        for event in physical:
            # An accepted exact excerpt is a span, never a phrase classifier.
            excerpt=event.get('physical_excerpt',event.get('physical_text',event.get('evidence')))
            if excerpt and excerpt in text:
                text = text.replace(excerpt, '', 1)
        audits=[t['physical_reconciliation'] for t in (history or {}).get('turns',[]) if t.get('physical_reconciliation')]
        for audit in audits:
            for span in audit.get('excluded_spans',[]):text=text.replace(span,'')
        if audits:result['physical_reconciliation']=True
        result['call_text'] = text.strip()
    return result


def reconciled_view(turn):
    """Context/memory read the accepted presentation; original prose stays in History."""
    route=turn.get('presentation',{})
    if not route.get('physical_reconciliation'):return turn
    return {**turn,'assistant_text':route.get('call_text','')+'\n'+route.get('physical_text','')+
        '\n[Runtime: unconfirmed physical claims in this turn were rejected. Continue from canonical WorldState; do not replay discarded prose.]'}


def physical_scene(state):
    """Choice applicability, excluding phone focus, remote Knowledge and clock.

    This is a disposable comparison of existing snapshots, not another scene or
    choice store. Structural presence/location/life changes invalidate suggestions.
    """
    camera=state.get('camera',{})
    present=set(camera.get('present_character_ids',[]))
    return dict(camera={k:camera.get(k) for k in ('controlled_actor_id','pov_actor_id','location_id')},
        present=sorted(present),
        characters={cid:{k:state['characters'][cid].get(k) for k in ('location_id','life_status')}
                    for cid in present if cid in state.get('characters',{})},
        conditions={key:row for key,row in state.get('conditions',{}).items()
                    if row.get('actor_id') in present},
        possessions={key:row for key,row in state.get('possessions',{}).items()
                    if row.get('holder_id') in present or row.get('location_id')==camera.get('location_id')})


def physical_choice_source(turns, state, after_for=None):
    """Latest physical source in the active History lineage, never latest job."""
    actor=state.get('camera',{}).get('controlled_actor_id')
    if not actor:return None
    for turn in reversed(turns):
        presentation=turn['presentation']
        mixed=bool(presentation.get('physical_text'))
        if mixed and (presentation.get('actor_id')!=actor or not presentation.get('physical_events')):
            return None  # Legacy/other actor projection has no applicable choices.
        if not mixed and (presentation['surface']!='physical' or turn['kind'] not in ('start','turn','pov')):
            continue
        after=(after_for(turn['id']) if after_for else json.loads(turn['after_json'])).get('world_state',{})
        camera=after.get('camera',{})
        if (camera.get('pov_actor_id') or camera.get('controlled_actor_id'))!=actor:
            return None
        if physical_scene(after)!=physical_scene(state):return None
        return dict(turn_id=turn['id'],variant_id=turn['active_variant_id'])
    return None


def visible_changes(changes, state, actor):
    """Read-only diagnostics summary must not preload unread phone consequences."""
    from copy import deepcopy
    from backend.runtime_v3.models import identity
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
    from backend.runtime_v3.remote_models import HISTORICAL_CHANNELS
    for event in upserts.get('remote_events', {}).values():
        if event.get('channel') in HISTORICAL_CHANNELS:
            event.pop('content', None)
    # Facts acquired from correspondence are available only through Knowledge;
    # diagnostic patches must not expose another actor's private read.
    private_facts = {identity('communicated_text', e['id']) for e in state.get('remote_events', {}).values()
                     if e['channel'] in HISTORICAL_CHANNELS and actor != e['sender_id'] and actor not in e['read_by']}
    if 'facts' in upserts:
        upserts['facts'] = {k:v for k,v in upserts['facts'].items() if k not in private_facts}
    if 'scheduled_events' in upserts:
        upserts['scheduled_events']={k:v for k,v in upserts['scheduled_events'].items() if commitment_visible(state,v,actor)}
    for c in upserts.get('characters',{}).values():
        for key in ('goals','intentions','obligations'):
            if key in c:c[key]=[v for v in c[key] if authored_record_visible(state,v,actor)]
    return result
