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
            or item.get('assertion')!='completed_end' or not resolver.supported(item)):
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


def repair_candidates(raw, accepted_events=()):
    """Guard critical claims and already validated Events, not optional hints."""
    result={section:[row for row in raw.records[section] if isinstance(row,dict)]
        for section in ('scheduled_event_changes','call_lifecycle_changes')}
    result['events']=[dict(id=e['local_id'],evidence=e['evidence']) for e in accepted_events
        if e.get('interaction_channel')=='physical' and e.get('local_id')]
    return result


def validate_repair(previous, raw):
    for section,rows in previous.items():
        key='call_id' if section=='call_lifecycle_changes' else 'id'
        for row in rows:
            if not any(isinstance(other,dict) and ((row.get(key) is not None and other.get(key)==row[key])
                or (row.get('evidence') and other.get('evidence')==row['evidence']))
                for other in raw.records[section]):
                fatal('Исправление удалило подтверждённое последствие телефонного хода.',
                    'call_repair_omission',repairable=False,section=section)


def reconcile(resolver, reason, quote=None):
    """Presentation audit, not another canonical state or a prose classifier."""
    audit=getattr(resolver,'physical_reconciliation',None)
    if audit is None:
        audit={'reasons':[], 'excluded_spans':[]}
        resolver.physical_reconciliation=audit
    if reason not in audit['reasons']:audit['reasons'].append(reason)
    if isinstance(quote,str) and quote.strip() and quote in resolver.narrative and quote not in audit['excluded_spans']:
        audit['excluded_spans'].append(quote)


def prepare_scene(resolver, raw):
    """Sanitize the optional call summary; final_scene still owns membership."""
    if resolver.before['meta']['interaction_focus']!='call':return
    scene=raw.final_scene;before=resolver.before['camera']
    if not isinstance(scene.get('situation',before['situation']),str):
        scene['situation']=before['situation']
        resolver.warn('final_scene',0,'Некорректное необязательное описание заменено предыдущим.',code='call_situation_retained')

def evidence_span(narrative, evidence):
    """Find the already validated quote with harmless whitespace/quote variations."""
    import re
    if not isinstance(evidence,str) or not evidence.strip():return ''
    parts=[]
    for part in evidence.split():
        parts.append(''.join('[\"«»“”„]' if char in '\"«»“”„' else re.escape(char) for char in part))
    match=re.search(r'\s+'.join(parts),narrative)
    return match.group() if match else ''


def project_physical(resolver, raw):
    call=active_call(resolver.before,resolver.protected_actor_id)
    if not call or resolver.before['meta']['interaction_focus']!='call':return
    events=[e for e in resolver.history.events if e.get('interaction_channel')=='physical'
        and resolver.protected_actor_id in e.get('witnesses',[])]
    by_id={e['local_id']:e for e in events}
    seen=set();spans=[]
    for index,row in enumerate(raw.records['physical_projections']):
        event=by_id.get(row.get('event_id')) if isinstance(row,dict) and isinstance(row.get('event_id'),str) else None
        text=row.get('text') if isinstance(row,dict) else None
        if event is None and isinstance(text,str) and text in resolver.narrative:
            matches=[e for e in events if e['evidence'] in text]
            if len(matches)==1:event=matches[0]
        valid=bool(event and event['local_id'] not in seen and isinstance(text,str) and text.strip()
            and text in resolver.narrative and event['evidence'] in text)
        if valid:
            start=resolver.narrative.index(text);end=start+len(text)
            valid=not any(start<right and left<end for left,right in spans)
        if not valid:
            resolver.warn('physical_projections',index,'Необязательная проекция отброшена; используется принятый Event, если он есть.',code='physical_projection_dropped')
            if not event and isinstance(text,str) and text in resolver.narrative:reconcile(resolver,'projection_unconfirmed',text)
            continue
        seen.add(event['local_id']);event['physical_text']=text
        event['physical_excerpt']=text;spans.append((start,end))
    for event in events:
        if event['local_id'] not in seen:
            event['physical_text']=event['text']
            event['physical_excerpt']=evidence_span(resolver.narrative,event['evidence'])
            resolver.warn('physical_projections',0,'Использован текст принятого Event.',entity=event['id'],code='physical_projection_fallback')
    # Rejected optional claims never become facts. Keep the exact original prose
    # in the audit, exclude identifiable spans, and flag uncertainty to reader/context.
    accepted={e.get('local_id') for e in resolver.history.events}
    for item in raw.records['events']:
        if isinstance(item,dict) and item.get('interaction_channel')=='physical' and (not isinstance(item.get('id'),str) or item['id'] not in accepted):
            reconcile(resolver,'event_rejected',item.get('evidence'))
            reconcile(resolver,'event_rejected',item.get('text'))
    scene=raw.final_scene
    actor=resolver.state['characters'][resolver.protected_actor_id]
    independent_situation=actor['situation']!=resolver.scene_character_situation
    if scene.get('situation',resolver.before['camera']['situation'])!=resolver.before['camera']['situation']:
        evidence=scene.get('situation_evidence')
        if events:
            # The scene summary is derived from accepted Events, not another LLM assertion.
            resolver.state['camera']['situation']=' '.join(e['text'] for e in events)
            if not independent_situation:actor['situation']=resolver.state['camera']['situation']
        else:
            resolver.state['camera']['situation']=resolver.before['camera']['situation']
            if not independent_situation:actor['situation']=resolver.before['characters'][resolver.protected_actor_id]['situation']
            resolver.warn('final_scene',0,'Описание ситуации не подтверждает физический переход; сохранена предыдущая сцена.',code='call_situation_retained')
            if evidence or (scene.get('situation') and scene['situation'] in resolver.narrative):
                reconcile(resolver,'situation_unconfirmed')
    # Sort by an existing evidence span when possible, otherwise retain accepted order.
    events.sort(key=lambda e:resolver.narrative.find(e.get('physical_excerpt','')) if e.get('physical_excerpt') else len(resolver.narrative))
    previous=resolver.before['meta']['world_time']
    for order,event in enumerate(events):
        event['order']=order
        minute=event.get('minute',resolver.state['meta']['world_time'])
        if not previous<=minute<=resolver.state['meta']['world_time']:
            resolver.warn('events',order,'Необязательное время Event заменено временем текущего commit.',entity=event['id'],code='physical_event_time_repaired')
            minute=resolver.state['meta']['world_time']
        event['minute']=minute;previous=minute
        from backend.runtime_v3.calendar import current_time
        event['calendar_date']=current_time(resolver.state,minute)['date']
    if events and not any(c.get('interaction_channel')=='physical' and not c.get('device_control') for c in raw.choices):
        resolver.warn('choices',0,'Физические подсказки отсутствуют; доступен свободный ввод, следующий обычный ход использует текущий мир.',code='physical_choices_unavailable')


CONTRACT = '''Call continuity: one world and one clock. Keep final_scene.situation about the physical scene, not a summary of the conversation. During calls autonomous nearby events can occur. Extract meaningful observed physical events with interaction_channel=physical and witnesses including the observer. Evidence is optional provenance; it is not an arrival permit. Optionally supply physical_projections {event_id: local event ID, text: literary passage from completed_narrative containing its evidence}. Do not duplicate an Event merely to satisfy presentation: absent or invalid projections use accepted Event.text. Exclude remote dialogue and conversation details from that passage. Do not project unchanged scenery. Never invent a physical event for a card. When useful, supply choices tagged interaction_channel=physical for the resulting physical situation; missing suggestions do not invalidate a turn; call choices are separately tagged call. Base physical suggestions on final_scene and accepted consequences, not the last remote reply. Do not freeze elapsed_minutes during calls or advance time for displaying projections. A completed hang-up in completed_narrative requires call_lifecycle_changes {call_id: existing active_call, actor_id: actual initiator, assertion: completed_end}; evidence is optional NPC provenance. Goodbye, intention, silence or a proposed hang-up are NOT completed_end. EXTERNAL hang-up additionally needs player_evidence from actual input. For voice agreements use scheduled_event_changes with call_evidence [{source_id from call_sources, actor_id, quote, assertion: proposal|assent|cancellation|outcome}]. Both proposal and explicit assent are necessary, including player-origin proposal plus NPC assent, or NPC proposal plus player assent across turns. Preserve exact full player wording, player_source_id, player_evidence, player_assertion=explicit_choice. call_time_source_id references the original proposal; temporal is relative to that source's canonical time. Reuse existing commitment ID for reschedule/cancel. Narrator prose cannot prove a player decision. No agreement from an unaccepted proposal.'''
