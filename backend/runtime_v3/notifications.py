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
    """Append provenance-bound receipts in the same transaction as the variant.

    Secret notices contain references only. Thread observations retain the
    witnessed revision in History, so a later unseen update cannot rewrite it.
    """
    from copy import deepcopy
    from backend.runtime_v3.models import identity
    from backend.runtime_v3.secrets import first_confirmations, visible_fact_ids
    from backend.runtime_v3.reproduction import known_birth
    records = history.setdefault('state_changes', [])
    sources = {e.get('id'): e for e in history.get('events', [])}
    witnesses = [r for r in records if r.get('kind') == 'thread_witness']
    records[:] = [r for r in records if r.get('kind') != 'thread_witness']
    observations = {}
    for witness in witnesses:
        actor = witness['actor_id']; tid = witness['thread_id']
        source = sources.get(witness['source_event_id'], {})
        thread = after['threads'].get(tid)
        if not thread or actor not in source.get('witnesses', []): continue
        if actor not in (thread.get('discovered_by') or []): continue
        view = dict(after, camera=dict(after['camera'], controlled_actor_id=actor))
        if not set(source.get('fact_ids', [])) <= visible_fact_ids(view): continue
        if any(not known_birth(after, cid, actor) for cid in thread['character_ids']): continue
        value = {k:deepcopy(thread[k]) for k in ('id','description','character_ids','status','state','relevance')}
        value['source_event_id'] = source['id']
        observations[(actor, tid)] = dict(kind='thread_observation',
            id=identity('thread_observation',commit_id,actor,tid), actor_id=actor,
            thread_id=tid, value=value, source_fact_ids=list(source.get('fact_ids', [])))
    records.extend(observations.values())
    actor = after['camera']['controlled_actor_id']
    if not actor or actor != before['camera']['controlled_actor_id']: return
    for event in first_confirmations(before, after, history):
        records.append(dict(kind='story_notice', id=identity('notice', commit_id, event['id']),
            actor_id=actor, notice_kind='secret_' + event['kind'], fact_id=event['fact_id'],
            source_event_id=event['source_event_id'], turn_id=after['meta']['turn_id']))
    for (observer, tid), observation in observations.items():
        if observer != actor or tid in before['threads']: continue
        records.append(dict(kind='story_notice', id=identity('notice', commit_id, 'thread', tid),
            actor_id=actor, notice_kind='thread_new', thread_id=tid,
            observation_id=observation['id'], turn_id=after['meta']['turn_id']))


def visible_threads(state, records):
    """Last witnessed revisions, derived from the active History, not latest omniscience."""
    from copy import deepcopy
    from backend.runtime_v3.secrets import visible_fact_ids
    from backend.runtime_v3.reproduction import known_birth
    actor = state['camera']['controlled_actor_id']
    allowed = visible_fact_ids(state)
    observed = {r['thread_id']:r for r in records
                if r.get('kind') == 'thread_observation' and r.get('actor_id') == actor}
    result = {}
    for tid, canonical in state['threads'].items():
        if canonical.get('discovered_by') is None:
            thread = deepcopy(canonical)  # Preserve author/legacy behavior.
        else:
            observation = observed.get(tid)
            if not observation or not set(observation.get('source_fact_ids', [])) <= allowed: continue
            thread = deepcopy(observation['value'])
        if any(not known_birth(state, cid, actor) for cid in thread['character_ids']): continue
        thread.pop('discovered_by', None)
        result[tid] = thread
    return result


def story_notifications(state, records, *, secrets=None, threads=None):
    """Resolve references against today's safe projection, never stored secret prose."""
    from backend.runtime_v3.secrets import projection, visible_fact_ids
    actor = state['camera']['controlled_actor_id']
    secrets = projection(state) if secrets is None else secrets
    known = {r['fact_id']: r for rows in [secrets['world'], *secrets['personal'].values()]
             for r in rows if r['status'] == 'known'}
    allowed = visible_fact_ids(state)
    observations = {r['id']:r for r in records if r.get('kind') == 'thread_observation'}
    threads = visible_threads(state, records) if threads is None else threads
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
            observation = observations.get(event.get('observation_id'))
            if not observation or observation['actor_id'] != actor: continue
            if event.get('thread_id') not in threads: continue
            if not set(observation.get('source_fact_ids', [])) <= allowed: continue
            item.update(text=observation['value']['description'], thread_id=event['thread_id'])
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
        WHERE json_extract(c.value, '$.kind') IN ('story_notice','thread_observation')
        ORDER BY h.rowid, CAST(c.key AS INTEGER)""", (head,)).fetchall()
    return [json.loads(r[0]) for r in rows]
