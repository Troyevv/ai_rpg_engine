"""Canonical motivation transitions; Extraction owns meaning, Runtime owns identity.

No text classifier or clock expiry. Legacy string lists remain a migration/manual
edit boundary. Typed partial updates never remove omitted records.
"""
from copy import deepcopy
from backend.runtime_v3.models import Motivation, identity
from backend.services.player_agency import supported_player_field, normalized

FIELDS = ('goals', 'intentions', 'obligations')
OPEN = ('active', 'blocked')
TERMINAL = ('completed', 'cancelled', 'failed', 'superseded', 'expired')
DEPENDENCIES = ('characters', 'roles', 'organizations')
MAX_UPDATES = 24


def actionable(record):
    return isinstance(record, str) or record['status'] == 'active' and not record.get('review_required')


def active_texts(records):
    return [r if isinstance(r, str) else r['text'] for r in records if actionable(r)]


def replace_active(records, texts, actor, field, sequence):
    """Explicit UI edit; unlike Extraction, the user supplied the entire list."""
    result = deepcopy(records)
    for entry in result:
        if entry['status'] == 'active' and entry['text'] not in texts:
            entry.update(status='cancelled', source_sequence=sequence, revision=entry.get('revision', 0)+1,
                         evidence='player_edit')
    existing = {r['text'] for r in result if r['status'] == 'active'}
    for text in texts:
        if text not in existing:
            result.append(Motivation(id=identity(field, actor, sequence, text, len(result)), text=text,
                                     source_sequence=sequence).model_dump())
            existing.add(text)
    return result


def record_change(resolver, cid, field, before, after, kind='motivation_transition'):
    from backend.runtime_v3.calendar import current_time
    row = after or before
    resolver.history.state_changes.append(dict(
        id=identity(kind,cid,field,row['id'],row.get('revision',0),resolver.turn_id),
        kind=kind, entity=cid, field=field, before=deepcopy(before), after=deepcopy(after),
        turn_id=resolver.turn_id, minute=resolver.state['meta']['world_time'],
        date=current_time(resolver.state)['date'], player_observed=resolver.observed,
        source_ids=[row['source_event_id']] if row.get('source_event_id') else []))


def dependency_signature(state, dependencies):
    parts=[]; reasons=[]
    for section, ids in sorted(dependencies.items()):
        for rid in ids:
            item=state[section].get(rid, {})
            status=item.get('life_status') if section=='characters' else item.get('status')
            parts.append((section,rid,status))
            if not item or status in ('dead','closed'):
                reasons.append(section+':'+rid+':'+str(status or 'missing'))
    return (identity('dependencies',parts) if parts else ''), reasons


def apply_changes(resolver, item, cid, index, events):
    from backend.runtime_v3.resolver import normalized as quote_normalized
    actor = resolver.state['characters'][cid]
    controlled = cid == resolver.protected_actor_id
    for field in FIELDS:
        changes=item.get(field+'_updates', [])
        if not isinstance(changes,list):
            resolver.warn('character_changes',index,'Ожидался список lifecycle.',field,cid); continue
        if len(changes)>MAX_UPDATES:
            resolver.warn('character_changes',index,'Лимит 24 lifecycle updates.',field,cid,code='motivation_budget')
        for change in changes[:MAX_UPDATES]:
            resolver.motivation_update_count = getattr(resolver,'motivation_update_count',0)+1
            if resolver.motivation_update_count>MAX_UPDATES:
                resolver.warn('character_changes',index,'Общий лимит 24 lifecycle updates.',field,cid,code='motivation_budget')
                return
            def reject(reason,code='motivation_invalid'):
                resolver.warn('character_changes',index,reason,field,cid,code=code)
            if not isinstance(change, dict) or not resolver.supported(change):
                reject('Нет evidence lifecycle.'); continue
            if controlled and resolver.mode=='background':
                reject('Фоновая симуляция не меняет мотивацию EXTERNAL.', 'motivation_agency'); continue
            old = next((r for r in actor[field] if r['id'] == change.get('id')), None)
            status = change.get('status', 'active')
            if status not in (*OPEN,*TERMINAL):
                reject('Неизвестный статус.'); continue
            if old and old['status'] in TERMINAL:
                # Replay is a no-op; reopening requires a NEW explicit motivation.
                if status != old['status']: reject('Закрытая запись не переоткрывается.', 'motivation_terminal')
                continue
            if 'expected_revision' in change and (type(change['expected_revision']) is not int or change['expected_revision'] != (old or {}).get('revision',0)):
                reject('Устаревшая версия мотивации.', 'motivation_conflict'); continue
            event=None;remote=None
            if change.get('source_event_id') is not None:
                event=events.get(change['source_event_id']) if isinstance(change['source_event_id'],str) else None
                remote=getattr(resolver,'remote_semantic_sources',{}).get(change['source_event_id']) if isinstance(change['source_event_id'],str) else None
                if remote and remote['sender_id']==cid:
                    event=dict(id=remote['id'],participants=[cid])
                if not event or cid not in event['participants']:
                    reject('Источник не является принятым событием персонажа.'); continue
            if remote and old and status!=old['status'] and old.get('source_event_id')==remote['id']:
                reject('Старая реплика не подтверждает новое состояние намерения.', 'motivation_remote_replay'); continue
            quote=quote_normalized(change['evidence'])
            if status in ('completed','failed','expired','blocked') and quote not in quote_normalized(resolver.narrative):
                reject('Ввод с планом действия не доказывает его выполнение.', 'motivation_completion_source'); continue
            player_quote=change.get('player_evidence','')
            explicit=(change.get('player_assertion')=='explicit_choice' and isinstance(player_quote,str)
                and bool(quote_normalized(player_quote)) and (quote_normalized(player_quote) in quote_normalized(resolver.player_input) or remote is not None and remote['sender_id']==cid and quote_normalized(player_quote) in quote_normalized(remote['content'])))
            if controlled and status in ('cancelled','superseded') and not explicit:
                reject('Отказ/замена EXTERNAL требует явного решения игрока.', 'motivation_agency'); continue
            dependencies=change.get('dependencies',(old or {}).get('dependencies',{}))
            if (not isinstance(dependencies,dict) or set(dependencies)-set(DEPENDENCIES)
                or any(not isinstance(ids,list) or len(ids)>8 or any(not isinstance(rid,str) or rid not in resolver.state[section] for rid in ids)
                       for section,ids in dependencies.items())):
                reject('Некорректные semantic dependencies.'); continue
            if old:
                if change.get('text',old['text']) != old['text']:
                    reject('Текст существующей записи нельзя переписать; используй superseded и новую запись.'); continue
                if status=='active' and old['status']=='blocked' and change.get('assertion')!='unblocked':
                    reject('Возобновление требует semantic assertion unblocked.'); continue
                if status=='active' and old.get('review_required') and change.get('assertion') not in ('still_active','unblocked'):
                    reject('Переоценка требует явного semantic assertion still_active/unblocked.'); continue
                before=deepcopy(old)
                signature,_=dependency_signature(resolver.state,dependencies)
                proposed=dict(old,status=status,evidence=change['evidence'],source_sequence=resolver.turn_id-1,
                    source_event_id=event['id'] if event else None,dependencies=deepcopy(dependencies),
                    review_required=[],reviewed_signature=signature if status!='active' or change.get('assertion') in ('still_active','unblocked') else old.get('reviewed_signature',''))
                # An unchanged active record may attach links or acknowledge review;
                # merely restating it must not create a revision/history each turn.
                if status==old['status'] and dependencies==old.get('dependencies',{}) and not old.get('review_required'):
                    continue
                proposed['revision']=old.get('revision',0)+1
                old.update(proposed)
                record_change(resolver,cid,field,before,old)
            else:
                if change.get('id'):
                    reject('Неизвестный motivation ID.'); continue
                text = change.get('text')
                if not isinstance(text, str) or not text.strip() or len(text)>4000 or status!='active':
                    reject('Новая запись требует непустой текст и active.'); continue
                if controlled and not explicit and not supported_player_field(field,[text],[],resolver.player_input,[change['evidence']]):
                    reject('Новая мотивация не задана игроком.', 'motivation_agency'); continue
                values = dict(id=identity(field,cid,resolver.turn_id,text), text=text, evidence=change['evidence'],
                    source_sequence=resolver.turn_id-1, source_event_id=event['id'] if event else None,dependencies=dependencies)
                if type(change.get('due_minute')) is int and change['due_minute'] >= 0: values['due_minute'] = change['due_minute']
                if not any(r['id']==values['id'] or r['status'] in OPEN and normalized(r['text'])==normalized(text) for r in actor[field]):
                    entry=Motivation(**values).model_dump();actor[field].append(entry)
                    record_change(resolver,cid,field,None,entry)


def queue_invalidations(resolver):
    """Linear pass over explicit links; zero semantic calls, no text matching.

    Pending review suppresses actionability, not desire/agency. Extraction examines
    only the relevant bounded slice, and acknowledges a signature once resolved.
    """
    for cid, actor in resolver.state['characters'].items():
        for field in ('goals','intentions'):
            for row in actor[field]:
                if row['status'] not in OPEN or not row.get('dependencies'): continue
                signature,reasons=dependency_signature(resolver.state,row['dependencies'])
                if signature==row.get('reviewed_signature') or reasons==row.get('review_required'): continue
                if reasons:
                    before=deepcopy(row);row['review_required']=reasons
                    row['revision']+=1
                    record_change(resolver,cid,field,before,row,'motivation_review')


def invalidate_dead_motivations(resolver, dead_ids):
    """Lifecycle owner consumes canonical death idempotently; retain every record."""
    for cid in sorted(dead_ids):
        actor = resolver.state['characters'][cid]
        for field in FIELDS:
            for row in actor[field]:
                if row['status'] not in OPEN: continue
                before = deepcopy(row)
                row.update(status='cancelled', evidence='canonical:actor_dead', source_sequence=resolver.turn_id-1,
                           revision=row.get('revision',0)+1,review_required=[])
                record_change(resolver,cid,field,before,row,'death_invalidation')


def context_records(records, *, evaluation=False, turn=0):
    """Stable bounded batches rotate for long-lived actors; reviews get priority."""
    rows=[r for r in records if isinstance(r,str) or r['status'] in OPEN] if evaluation else [r for r in records if actionable(r)]
    if not rows: return []
    if evaluation:
        pending=[r for r in rows if isinstance(r,dict) and r.get('review_required')]
        ordinary=[r for r in rows if r not in pending]
        offset=(turn*4)%len(ordinary) if ordinary else 0
        review_offset=(turn*4)%len(pending) if pending else 0
        rows=pending[review_offset:]+pending[:review_offset]+ordinary[offset:]+ordinary[:offset]
    result=[];budget=1800
    for row in rows:
        record=({k:row[k] for k in ('id','text','status','revision','dependencies','review_required') if k in row} if evaluation
                else {k:row[k] for k in ('id','text','status')} ) if isinstance(row,dict) else row
        cost=len(str(record))
        if cost>budget: continue
        result.append(record);budget-=cost
        if len(result)==8: break
    return result


def salvage_metadata(state):
    """Keep old text/status/ID intact when optional #75 metadata is malformed."""
    import logging
    for actor in state.get('characters',{}).values():
        if not isinstance(actor,dict): continue
        for field in FIELDS:
            rows=actor.get(field,[])
            if not isinstance(rows,list): continue
            for row in rows:
                if not isinstance(row,dict): continue
                for key in ('revision','source_event_id','dependencies','review_required','reviewed_signature'):
                    if key not in row: continue
                    try:
                        Motivation.model_validate(dict(id='check',text='',**{key:row[key]}))
                        if key=='dependencies' and (set(row[key])-set(DEPENDENCIES) or any(len(ids)>8 for ids in row[key].values())):
                            raise ValueError('dependencies')
                    except (ValueError,TypeError):
                        logging.getLogger(__name__).warning('Ignoring malformed motivation metadata %s/%s',row.get('id'),key)
                        row.pop(key)


def historical_context(scope, history):
    """Resolved entries appear only alongside already-selected causal events."""
    selected={e.get('id') for e in scope.history_events};result=[];budget=1800
    for change in reversed((history or {}).get('state_changes',[])):
        if change.get('kind') not in ('motivation_transition','value_delta') or change.get('entity') not in scope.relevant_actor_ids:
            continue
        sources=set(change.get('source_ids',[])) | {e.get('source_event_id') for e in change.get('sources',[])}
        if not sources & selected: continue
        record={k:change.get(k) for k in ('entity','field','minute','before','after')}
        if len(str(record))>budget: continue
        result.append(record);budget-=len(str(record))
        if len(result)==3: break
    return result
