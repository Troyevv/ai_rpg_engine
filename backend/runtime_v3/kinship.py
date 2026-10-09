"""Read-only bounded kinship. Authorization is applied BEFORE graph traversal.

The API never returns raw relation facts, provenance, hidden counts or timelines.
Knowing a former phase does not grant knowledge of a later closure/name/death.
"""
from collections import deque
from backend.runtime_v3.life import FAMILY, PARENTAGE


def knowledge_status(state, observer, fact_id):
    return state['knowledge'].get(f'{observer}:{fact_id}', {}).get('status','unknown') if fact_id else 'unknown'


def visible_relations(state, observer):
    rows = []
    if observer not in state['characters']: return rows
    for r in state.get('objective_relations', {}).values():
        certainty = knowledge_status(state,observer,r.get('fact_id'))
        if certainty == 'unknown': continue
        closure = knowledge_status(state,observer,r.get('closure_fact_id')) == 'known'
        # A known death only closes a known partnership, never reveals a secret one.
        death_known = (r['kind'] in ('spouse','partner','engaged') and any(
            state['characters'][cid].get('life_status') == 'dead' and
            knowledge_status(state,observer,state['characters'][cid].get('life_fact_id')) == 'known'
            for cid in (r['source_id'],r['target_id'])))
        closed = r['status'] == 'closed' and (closure or death_known)
        rows.append(dict(id=r['id'],kind=r['kind'],source_id=r['source_id'],target_id=r['target_id'],
                         certainty=certainty,status='closed' if closed else 'active',
                         outcome=r['outcome'] if closed else '',
                         since=r['since'],since_date=r['since_date'],
                         until=r['until'] if closed else None,until_date=r['until_date'] if closed else None))
    return rows


def visible_name(state, cid, observer, fallback):
    c = state['characters'][cid]
    history = c.get('name_history', [])
    if not history: return c.get('display_name') or fallback
    name = history[0]['previous']
    for phase in history:
        if cid == observer or knowledge_status(state,observer,phase['fact_id']) == 'known': name=phase['current']
    return name


def genealogy(snapshot, root_id=None, *, depth=3, limit=100):
    if type(depth) is not int or not 0 <= depth <= 8 or type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError('Глубина родословной: 0–8, число персонажей: 1–200.')
    s = snapshot['world_state']; observer=s['camera']['controlled_actor_id']
    empty = dict(nodes=[],edges=[],kinship=[],truncated=False)
    if observer not in s['characters']: return empty
    edges = [r for r in visible_relations(s,observer) if r['kind'] in FAMILY]
    known_ids = {observer} | {r[k] for r in edges for k in ('source_id','target_id')}
    root = root_id or observer
    # Unknown and nonexistent IDs have exactly the same response.
    if root not in known_ids: return empty
    adjacency = {}
    for r in edges:
        a,b=r['source_id'],r['target_id']
        adjacency.setdefault(a,set()).add(b);adjacency.setdefault(b,set()).add(a)
    visited, queue, truncated = {root}, deque([(root,0)]), False
    while queue:
        cid, level = queue.popleft()
        if level == depth: continue
        for other in sorted(adjacency.get(cid,())):
            if other in visited: continue
            if len(visited) == limit:
                truncated=True; continue
            visited.add(other); queue.append((other,level+1))
    edges = [r for r in edges if r['source_id'] in visited and r['target_id'] in visited]
    cards = {c['id']:c['name'] for c in snapshot.get('character_cards',[])}
    nodes=[]
    for cid in sorted(visited):
        c=s['characters'][cid]
        nodes.append(dict(id=cid,name=visible_name(s,cid,observer,cards.get(cid,cid)),
            life_status=c.get('life_status','unknown') if cid==observer or knowledge_status(s,observer,c.get('life_fact_id'))=='known' else 'unknown'))
    # Derive only from authorized, known parentage; suspected links stay uncertain.
    parents={}
    for r in edges:
        # Ended adoption stays in historical edges, not current derived legal kinship.
        # Biological ancestry persists independently of a closed contact/status phase.
        if r['kind'] in PARENTAGE and r['certainty']=='known' and (r['kind']=='parent' or r['status']=='active'):
            parents.setdefault((r['target_id'],r['kind']),set()).add(r['source_id'])
    kinship=[]
    for cid in sorted(visited):
        for kind in sorted(PARENTAGE):
            seen, todo = set(), deque((p,1) for p in sorted(parents.get((cid,kind),())))
            while todo:
                parent,generation=todo.popleft()
                if parent in seen: continue
                seen.add(parent)
                kinship.append(dict(source_id=parent,target_id=cid,kind=kind if generation==1 else 'ancestor',
                                    lineage=kind,generations=generation))
                kinship.append(dict(source_id=cid,target_id=parent,kind='child' if generation==1 else 'descendant',
                                    lineage=kind,generations=generation))
                if generation<depth:
                    todo.extend((p,generation+1) for p in sorted(parents.get((parent,kind),())))
        for other in sorted(c for c in visited if c>cid):
            for kind in sorted(PARENTAGE):
                a,b=parents.get((cid,kind),set()),parents.get((other,kind),set())
                if not a.intersection(b): continue
                complete = all(knowledge_status(s,observer,s['characters'][c].get('parentage_complete_fact_id'))=='known' for c in (cid,other))
                relation = 'half_sibling' if kind=='parent' and complete and a!=b else 'sibling'
                kinship.append(dict(source_id=cid,target_id=other,kind=relation,lineage=kind))
    return dict(nodes=nodes,edges=edges,kinship=kinship,truncated=truncated)
