"""Synchronize final live positions without editing historical contexts."""
def apply_locations(state, movement_plan, sequence, kind=None):
    """Publish validated final positions to live scenes; event snapshots stay immutable."""
    from backend.services.world import identity
    from backend.services.timeline import current_time
    world=state['world'];now=current_time(state)
    if kind is not None:
        meta=state['scene_meta'];participants=list(movement_plan['final_present'])
        prior=world['scenes'].get(state.get('camera',{}).get('scene_id'))
        same=prior and not prior.get('historical') and prior['location']==meta['location'] and set(prior['participants'])==set(participants)
        sid=prior['id'] if same else identity('scene',sequence,meta['location'],sorted(participants))
        final=world['scenes'].setdefault(sid,dict(id=sid,start_minute=now,event_ids=[]))
        final.update(participants=participants,location=meta['location'],end_minute=now,text=state['scene'],status='active')
        state['camera']={'scene_id':sid,'mode':'observer' if kind=='background' else 'actor','scope':state.get('camera',{}).get('scope','world')}
        if kind=='background':state['controlled_actor_id']=None
    else:
        final=world['scenes'][state['camera']['scene_id']]
    for cid in sorted(movement_plan.get('spatial_actors',movement_plan['involved'])):
        location=movement_plan['positions'][cid]
        if location is None:continue
        point=world['characters'][cid]
        if cid in final['participants']:
            scene=final
        else:
            scene=next((s for s in world['scenes'].values() if not s.get('historical') and s['id']!=final['id'] and s['location']==location and cid in s['participants']),None)
            if scene is None:
                sid=identity('scene','departed',sequence,location)
                scene=world['scenes'].setdefault(sid,dict(id=sid,participants=[],location=location,start_minute=now,end_minute=now,text=point.get('situation',''),status='active',event_ids=[]))
            if cid not in scene['participants']:scene['participants'].append(cid)
        for other in world['scenes'].values():
            if not other.get('historical') and other['id']!=scene['id'] and cid in other['participants']:
                other['participants'].remove(cid)
                if not other['participants']:other['status']='ended'
        point.update(location=location,scene_id=scene['id'])
        if cid in movement_plan['involved']:
            scene['status']='active';scene['end_minute']=now
            point['minute']=now
    return final['id']
