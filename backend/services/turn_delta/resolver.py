"""Single final-state resolver: Before → movements → final camera snapshot."""
from collections import defaultdict
from backend.services.timeline import current_time
from .references import require


def resolve_final_state(before, after, delta, since=None):
    world=before['world'];actors=world['characters']
    initial=world['scenes'][before['camera']['scene_id']]
    final=after.get('scene_meta') or dict(location=after['world']['scenes'][after['camera']['scene_id']]['location'],present_ids=after['world']['scenes'][after['camera']['scene_id']]['participants'])
    present=set(final['present_ids'])
    require(present<=set(actors),'неизвестный персонаж','unknown_character',section='scene')
    positions={cid:c.get('location') for cid,c in actors.items()}
    involved=set(initial['participants'])|present|{p['id'] for p in delta['promotions']}
    for e in delta['events']:involved.update(e['participants']+e['witnesses'])
    groups=defaultdict(list);derivations=[]
    start=current_time(before) if since is None else since
    for i,m in enumerate(delta['transitions']):
        if 'minute' in m:require(start<=m['minute']<=current_time(after),'перемещение вне интервала хода','temporal_order_invalid',section='transitions',index=i)
        groups[m['actor_id']].append((i,m));involved.add(m['actor_id'])
    for cid,moves in groups.items():
        if len(moves)>1:
            # Relative order is authoritative. Legacy complete minute/order
            # metadata is supported only when it determines the entire route.
            if all('order' in m for _,m in moves) and len({m['order'] for _,m in moves})==len(moves):
                moves.sort(key=lambda pair:pair[1]['order'])
            elif all('minute' in m for _,m in moves) and len({(m['minute'],m.get('order',0)) for _,m in moves})==len(moves):
                moves.sort(key=lambda pair:(pair[1]['minute'],pair[1].get('order',0)))
            elif cid in present:
                # No uniquely ordered route, but the final snapshot resolves the
                # endpoint. Do not invent intermediate origins from array order.
                continue
            elif len({m['to_location'] for _,m in moves})==1:
                moves=moves[:1]
            else:require(False,'неоднозначный порядок перемещений','temporal_order_invalid',section='transitions',entity=cid)
        for index,m in moves:
            derivations.append(dict(section='transitions',index=index,entity=cid,code='movement_derived',
                origin=positions[cid],destination=m['to_location']))
            positions[cid]=m['to_location']
    for cid in sorted(present):
        if positions[cid]!=final['location']:
            derivations.append(dict(section='scene',entity=cid,code='final_location_derived_from_scene',
                origin=positions[cid],destination=final['location']))
        positions[cid]=final['location']
    for i,c in enumerate(delta['characters']):
        require(c['id'] in involved,'персонаж не участвовал в текущем ходе','character_not_involved',section='characters',index=i)
    return dict(positions=positions,involved=involved,derivations=derivations,
                final_location=final['location'],final_present=sorted(present))
