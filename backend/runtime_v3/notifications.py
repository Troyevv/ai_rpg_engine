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
