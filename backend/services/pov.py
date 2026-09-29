"""Role and visibility policy independent of HTTP and the protagonist marker."""

import json


def protagonist(state):
    return state.get('protagonist_id') or next((c['id'] for c in state.get('characters',[]) if c.get('is_player')),None)


def controlled(state):
    return state['controlled_actor_id'] if 'controlled_actor_id' in state else protagonist(state)


def visible(turn,actor,main):
    # Legacy ordinary scenes were written with the original protagonist's POV.
    audience=json.loads(turn.get('audience_json') or '[]')
    if audience:
        return actor in audience
    return turn.get('kind')!='background' and actor==(turn.get('pov_actor_id') or main)


def actor_view(turn,actor,main):
    """Other viewpoints expose only explicitly attributed knowledge, not private prose."""
    if turn.get('kind')!='background' and actor==(turn.get('pov_actor_id') or main):
        return turn
    changes=json.loads(turn.get('changes_json') or '{}')
    facts=[f['text'] for f in changes.get('facts',[]) if actor in f.get('known_by',[])]
    delta=changes.get('world_delta',{})
    patch=changes.get('state_patch',{}).get('upserts',{})
    for k in patch.get('knowledge',{}).values():
        fact=patch.get('facts',{}).get(k['fact_id'])
        if fact and k['actor_id']==actor and k['status']!='unknown':facts.append(k['status']+': '+fact['text'])
    newfacts={f['id']:f['text'] for f in delta.get('facts',[])}
    for k in delta.get('knowledge',[]):
        if k['actor_id']==actor and k['status']!='unknown' and k['fact_id'] in newfacts:
            facts.append(k['status']+': '+newfacts[k['fact_id']])
    return {**turn,'user_text':'','assistant_text':'Доступные персонажу факты:\n'+'\n'.join(facts)}
