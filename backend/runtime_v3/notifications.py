"""Only observed canonical before/after diffs may reach live notifications."""
POSITIVE={'trust','affection','respect','attraction'}


def notifications(state, history):
    turn=state['meta']['turn_id']; result=[]
    grouped={}
    for change in history.get('relationship_changes',[]):
        if not isinstance(change,dict) or change.get('turn_id')!=turn or change.get('player_observed') is not True:continue
        key=change.get('entity')
        if key not in grouped:grouped[key]=dict(change)
        else:grouped[key]['after']=change.get('after')
    for key,c in grouped.items():
        old,new=c.get('before'),c.get('after')
        if not isinstance(old,dict) or not isinstance(new,dict):continue
        deltas={d:v-old['dimensions'][d] for d,v in new['dimensions'].items() if d in old.get('dimensions',{}) and v!=old['dimensions'][d]}
        if not deltas:continue
        signs={1 if (v>0)==(d in POSITIVE) else -1 for d,v in deltas.items()}
        result.append(dict(id=f'{turn}:relationship:{key}',kind='relationship',source_id=new['source_id'],target_id=new['target_id'],deltas=deltas,
                           direction='mixed' if len(signs)>1 else 'up' if 1 in signs else 'down'))
    controlled=state['camera']['controlled_actor_id']
    for change in history.get('state_changes',[]):
        if not isinstance(change,dict) or change.get('turn_id')!=turn or change.get('player_observed') is not True:continue
        old=change.get('before_characters',{}).get(controlled)
        current=change.get('upserts',{}).get('characters',{}).get(controlled)
        if not old or not current:continue
        for field in ('goals','intentions','obligations'):
            previous={r['id']:r for r in old[field]}
            for r in current[field]:
                prior=previous.get(r['id'])
                completed=prior and prior['status']=='active' and r['status']=='completed'
                created=not prior and field=='obligations' and r['status']=='active'
                if completed or created:
                    result.append(dict(id=f'{turn}:{r["id"]}',kind='lifecycle',field=field,status=r['status'],text=r['text']))
    return result


def record_story_changes(before, after, history, commit_id):
    """References only, atomically appended to the existing branch History DAG.

    Not an outbox or a second Knowledge store. Failed transactions publish nothing.
    Each accepted variant has its own identity, including identical regeneration.
    """
    from backend.runtime_v3.models import identity
    from backend.runtime_v3.secrets import first_confirmations
    actor = after['camera']['controlled_actor_id']
    if not actor or actor != before['camera']['controlled_actor_id']:
        return
    records = history.setdefault('state_changes', [])
    for event in first_confirmations(before, after, history):
        records.append(dict(kind='story_notice', id=identity('notice', commit_id, event['id']),
            actor_id=actor, notice_kind='secret_' + event['kind'], fact_id=event['fact_id'],
            source_event_id=event['source_event_id'], turn_id=after['meta']['turn_id']))
    sources = {e.get('id'): e for e in history.get('events', [])}
    for tid, thread in after['threads'].items():
        if tid in before['threads'] or actor not in (thread.get('discovered_by') or []):
            continue
        source = sources.get(thread.get('source_event_id'), {})
        if actor not in source.get('witnesses', []):
            continue
        records.append(dict(kind='story_notice', id=identity('notice', commit_id, 'thread', tid),
            actor_id=actor, notice_kind='thread_new', thread_id=tid,
            source_event_id=source['id'], source_fact_ids=list(source.get('fact_ids', [])),
            turn_id=after['meta']['turn_id']))


def story_notifications(state, records):
    """Resolve references against today's safe projection, never stored secret prose."""
    from backend.runtime_v3.secrets import projection, visible_fact_ids
    actor = state['camera']['controlled_actor_id']
    secrets = projection(state)
    known = {r['fact_id']: r for rows in [secrets['world'], *secrets['personal'].values()]
             for r in rows if r['status'] == 'known'}
    allowed = visible_fact_ids(state)
    result = []
    for event in records:
        if event.get('kind') != 'story_notice' or event.get('actor_id') != actor:
            continue
        item = dict(id=event['id'], kind=event['notice_kind'], turn_id=event['turn_id'])
        if event.get('fact_id'):
            row = known.get(event['fact_id'])
            if row is None:
                belief = state['knowledge'].get(str(actor)+':'+event['fact_id'], {})
                status = belief.get('status')
                if status not in ('outdated', 'refuted', 'superseded'): continue
                # A receipt proves past acquisition, not permission to republish
                # objective truth after retirement. Keep a safe history marker.
                label = {'outdated':'устарело', 'refuted':'опровергнуто', 'superseded':'пересмотрено'}[status]
                item.update(text='Прежнее знание тайны '+label+'.', available=False)
                result.append(item)
                continue
            subjects = [cid for cid, rows in secrets['personal'].items() if any(r['id'] == row['id'] for r in rows)]
            item.update(text=row['text'], slot_id=row['id'], character_ids=subjects)
        else:
            thread = state['threads'].get(event.get('thread_id'))
            if not thread or actor not in (thread.get('discovered_by') or []): continue
            from backend.runtime_v3.reproduction import known_birth
            if any(not known_birth(state, cid, actor) for cid in thread['character_ids'] + thread['stakes_for']): continue
            if not set(event.get('source_fact_ids', [])) <= allowed: continue
            item.update(text=thread['description'], thread_id=thread['id'])
        result.append(item)
    return result


def read_story_receipts(db, head):
    """Complete active history, independent of the bounded narrative context tail."""
    import json
    if not head: return []
    rows = db.execute("""WITH RECURSIVE lineage(id) AS (
        SELECT ? UNION SELECT h.parent_id FROM world_history_v3 h
        JOIN lineage l ON h.id=l.id WHERE h.parent_id IS NOT NULL)
        SELECT c.value FROM lineage l JOIN world_history_v3 h ON h.id=l.id,
        json_each(h.payload_json, '$.state_changes') c
        WHERE json_extract(c.value, '$.kind')='story_notice'
        ORDER BY h.rowid, CAST(c.key AS INTEGER)""", (head,)).fetchall()
    return [json.loads(r[0]) for r in rows]
