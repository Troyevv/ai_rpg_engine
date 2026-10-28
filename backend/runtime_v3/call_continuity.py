"""Evidence adapters for a call turn in the existing History/Resolver pipeline.

No second transcript or clock: sources are immutable History turns; projections
reference accepted Events; lifecycle uses the same Remote command implementation.
"""
from backend.runtime_v3.models import identity, fatal
from backend.runtime_v3.remote import active_call, participants


def sources(state, history, narrative, player_input, turn_id):
    call = active_call(state, state['camera']['controlled_actor_id'])
    if not call or call['status'] != 'answered' or state['meta']['interaction_focus'] != 'call':
        return {}
    actor = state['camera']['controlled_actor_id']
    rows = [r for r in (history or {}).get('turns', []) if r.get('call_id') == call['id'] and r.get('controlled_actor_id') == actor]
    # Whole sources, never truncated quotes. A bounded overflow is explicit.
    if sum(len(r.get('narrative','')) + len(r.get('player_input','')) for r in rows) > 100000:
        fatal('История активного звонка превышает бюджет доказательств.', 'call_evidence_budget')
    rows = rows + [dict(id=identity('record',turn_id,narrative,True), narrative=narrative,
        player_input=player_input, game_time_before=state['meta']['world_time'])]
    result = {}
    for row in rows:
        for role, field in (('player','player_input'),('narrative','narrative')):
            content = row.get(field,'')
            if not content: continue
            sid = row['id'] + ':' + role
            result[sid] = dict(id=sid,call_id=call['id'],role=role,actor_id=actor if role=='player' else None,
                content=content,world_time=row['game_time_before'])
    return result


def commitment_sources(resolver, item):
    """Validate semantic proposal/assent against exact, author-bound History."""
    proofs = item.get('call_evidence')
    if not isinstance(proofs,list) or not 1 <= len(proofs) <= 8: return []
    call = active_call(resolver.before,resolver.protected_actor_id)
    if not call or call['status']!='answered': return []
    result=[]
    for proof in proofs:
        if not isinstance(proof,dict): return []
        source=resolver.call_sources.get(proof.get('source_id'))
        actor=proof.get('actor_id');quote=proof.get('quote')
        if (not source or source['call_id']!=call['id'] or actor not in participants(call)
            or not isinstance(quote,str) or not quote.strip() or quote not in source['content']
            or proof.get('assertion') not in ('proposal','assent','cancellation','outcome')): return []
        if actor==resolver.protected_actor_id:
            if source['role']!='player' or source['actor_id']!=actor or quote!=source['content']: return []
        elif source['role']!='narrative': return []
        result.append(dict(id=source['id'], sender_id=actor, content=quote,
            world_time=source['world_time'], assertion=proof['assertion']))
    if item.get('assertion') in ('agreed','rescheduled'):
        actors=set(item.get('character_ids',resolver.before['scheduled_events'].get(item.get('id'),{}).get('character_ids',[])))
        if not actors or not actors <= {r['sender_id'] for r in result if r['assertion'] in ('proposal','assent')}: return []
        if not any(r['assertion']=='proposal' for r in result) or not any(r['assertion']=='assent' for r in result): return []
        old=resolver.before['scheduled_events'].get(item.get('id'),{})
        if item.get('assertion')=='rescheduled':
            previous={p['source_id'] for p in old.get('call_evidence',[])}
            if not actors <= {r['sender_id'] for r in result if r['id'] not in previous}: return []
    if item.get('assertion')=='cancelled':
        decision=item.get('decision_actor_id',resolver.protected_actor_id)
        if not any(r['sender_id']==decision and r['assertion']=='cancellation' for r in result): return []
    return result


def apply_lifecycle(resolver, raw):
    from backend.runtime_v3.remote import apply
    if len(raw.records['call_lifecycle_changes']) > 1:
        fatal('Несколько отбоев одного хода.', 'call_end_duplicate',repairable=True)
    for item in raw.records['call_lifecycle_changes']:
        call=active_call(resolver.state,resolver.protected_actor_id)
        if (not isinstance(item,dict) or not call or call['status']!='answered'
            or item.get('call_id')!=call['id'] or item.get('actor_id') not in participants(call)
            or item.get('assertion')!='completed_end' or not resolver.supported(item)
            or item['evidence'] not in resolver.narrative):
            fatal('Не подтверждён фактический отбой звонка.', 'call_end_unsupported',repairable=True)
        actor=item['actor_id']
        if actor==resolver.protected_actor_id and (not isinstance(item.get('player_evidence'),str)
            or not item['player_evidence'].strip() or item['player_evidence'] not in resolver.player_input):
            fatal('Нет команды игрока на отбой.', 'call_end_agency',repairable=True)
        snapshot,batch=apply({'world_state':resolver.state},dict(action='end',event_id=call['id'],
            operation_id=identity('call_end',call['id'],resolver.turn_id,item['evidence'])),
            actor_id=actor,autonomous=actor!=resolver.protected_actor_id)
        resolver.state.clear();resolver.state.update(snapshot['world_state'])
        resolver.state['camera']['remote_interactions']=[]
        for section,values in batch.items():
            for value in values:
                value.update(narrative_evidence=item['evidence'],acting_character_id=actor)
            getattr(resolver.history,section).extend(values)


def repair_candidates(raw):
    """Do not let a repair hide a rejected consequence by omitting it."""
    return {section:[row for row in raw.records[section] if isinstance(row,dict)
            and (section!='events' or row.get('interaction_channel')=='physical')]
        for section in ('events','scheduled_event_changes','call_lifecycle_changes')}


def validate_repair(previous, raw):
    current=repair_candidates(raw)
    for section,rows in previous.items():
        key='call_id' if section=='call_lifecycle_changes' else 'id'
        for row in rows:
            if not any((row.get(key) is not None and other.get(key)==row[key])
                or (row.get('evidence') and other.get('evidence')==row['evidence'])
                for other in current[section]):
                fatal('Исправление удалило последствие телефонного хода.',
                    'call_repair_omission',repairable=False,section=section)


def project_physical(resolver, raw):
    call=active_call(resolver.before,resolver.protected_actor_id)
    if not call or resolver.before['meta']['interaction_focus']!='call': return
    events=[e for e in resolver.history.events if e.get('interaction_channel')=='physical'
        and resolver.protected_actor_id in e.get('witnesses',[])]
    projections=raw.records['physical_projections']
    by_id={e['local_id']:e for e in events}
    seen=set()
    spans=[]
    for row in projections:
        if not isinstance(row,dict): fatal('Некорректная физическая проекция.', 'physical_projection_invalid',repairable=True)
        event=by_id.get(row.get('event_id'));text=row.get('text')
        if (not event or event['local_id'] in seen or not isinstance(text,str) or not text.strip()
            or text not in resolver.narrative or event['evidence'] not in text):
            fatal('Физический фрагмент требует принятого Event и точного narrative evidence.', 'physical_projection_invalid',repairable=True)
        seen.add(event['local_id']);event['physical_text']=text
        start=resolver.narrative.index(text);end=start+len(text)
        if any(start < right and left < end for left,right in spans):
            fatal('Физические фрагменты пересекаются.', 'physical_projection_overlap',repairable=True)
        spans.append((start,end))
    if seen!=set(by_id):
        fatal('Физическое событие осталось без художественного продолжения.', 'physical_projection_missing',repairable=True,event_ids=sorted(set(by_id)-seen))
    from backend.runtime_v3.surfaces import physical_scene
    if not events and physical_scene(resolver.before)!=physical_scene(resolver.state):
        fatal('Изменение физической сцены требует наблюдаемых событий.', 'physical_event_missing',repairable=True)
    if events:
        # Source order is verifiable even if the provider supplied a wrong order.
        events.sort(key=lambda e:resolver.narrative.index(e['physical_text']))
        previous_minute=resolver.before['meta']['world_time']
        for order,event in enumerate(events):
            event['order']=order
            minute=event.get('minute',resolver.state['meta']['world_time'])
            if not previous_minute <= minute <= resolver.state['meta']['world_time']:
                fatal('Время физического события вне хода.', 'physical_event_time',repairable=True)
            event['minute']=minute
            previous_minute=minute
            from backend.runtime_v3.calendar import current_time
            event['calendar_date']=current_time(resolver.state,minute)['date']
        physical=[dict(c,interaction_channel='physical') for c in raw.choices if c.get('interaction_channel')=='physical' and not c.get('device_control')]
        from backend.runtime_v3.life import capabilities
        if capabilities(resolver.state,resolver.protected_actor_id)['can_act'] and not physical:
            fatal('Изменившаяся физическая сцена требует актуальных вариантов.', 'physical_choices_missing',repairable=True)
    elif projections:
        fatal('Нет физических событий для проекции.', 'physical_projection_invalid',repairable=True)


CONTRACT = '''Call continuity: one world and one clock. Keep final_scene.situation about the physical scene, not a summary of the conversation. During calls autonomous nearby events can occur. Extract meaningful observed physical events with interaction_channel=physical, witnesses including the observer, and exact evidence. For EACH such event supply physical_projections {event_id: local event ID, text: exact complete literary passage from completed_narrative containing its evidence}. Exclude remote dialogue and conversation details from that passage. Do not project unchanged scenery. Never invent a physical event for a card. Supply choices tagged interaction_channel=physical for the resulting physical situation if it changed; call choices are separately tagged call. Base physical suggestions on final_scene and accepted consequences, not the last remote reply. Do not freeze elapsed_minutes during calls or advance time for displaying projections. A completed hang-up in completed_narrative requires call_lifecycle_changes {call_id: existing active_call, actor_id: actual initiator, assertion: completed_end, evidence: exact quote}. Goodbye, intention, silence or a proposed hang-up are NOT completed_end. EXTERNAL hang-up additionally needs player_evidence from actual input. For voice agreements use scheduled_event_changes with call_evidence [{source_id from call_sources, actor_id, quote, assertion: proposal|assent|cancellation|outcome}]. Both proposal and explicit assent are necessary, including player-origin proposal plus NPC assent, or NPC proposal plus player assent across turns. Preserve exact full player wording, player_source_id, player_evidence, player_assertion=explicit_choice. call_time_source_id references the original proposal; temporal is relative to that source's canonical time. Reuse existing commitment ID for reschedule/cancel. Narrator prose cannot prove a player decision. No agreement from an unaccepted proposal.'''
