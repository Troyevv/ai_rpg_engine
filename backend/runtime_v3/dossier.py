"""Read-only dossier details. Knowledge gates conditions, never the public family directory."""
from backend.runtime_v3.kinship import knowledge_status
from backend.runtime_v3.portraits import silhouette


def details(state, cid):
    observer = state['camera']['controlled_actor_id']
    actor = state['characters'][cid]
    rows = []
    for c in state.get('conditions', {}).values():
        if c['actor_id'] != cid:
            continue
        fid = c.get('fact_id')
        if not (knowledge_status(state, observer, fid) == 'known' or (cid == observer and not fid)):
            continue
        rows.append({**{k: c.get(k) for k in ('id', 'description', 'status', 'duration', 'since', 'until')},
                     'restrictions': [k for k, v in c['effects'].items() if v is False],
                     'evidence': c.get('evidence', '')})
    # Only explicit base restrictions for the controlled actor. Never derive an
    # NPC capability from a concealed condition (including its mere existence).
    restrictions = [k for k, v in actor.get('capabilities', {}).items() if v is False] if cid == observer else []
    return dict(sex=silhouette(state, cid), conditions=rows, restrictions=restrictions)
