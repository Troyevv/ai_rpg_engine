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


def personal_relations(state):
    """Disposable canonical directory for dossier identity, never actor knowledge.

    Explicit allowlist excludes facts, evidence and provenance. Nothing is stored
    back into WorldState; legacy saves acquire this view on every read.
    """
    fields = ('id', 'kind', 'source_id', 'target_id', 'status', 'outcome',
              'since', 'since_date', 'until', 'until_date')
    return [{key: row.get(key) for key in fields}
            for row in state.get('objective_relations', {}).values()
            if row['kind'] in ('spouse', 'partner', 'engaged')]
