"""Synchronize final live positions without editing historical contexts."""
def apply_locations(state, movement_plan, sequence):
    """Publish validated final positions to live scenes; event snapshots stay immutable."""
    from backend.services.world import identity
    from backend.services.timeline import current_time
    world=state['world'];now=current_time(state)
    final=world['scenes'][state['camera']['scene_id']]
    for cid in sorted(movement_plan['involved']):
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
        scene['status']='active';scene['end_minute']=now
        point.update(location=location,scene_id=scene['id'],minute=now)
