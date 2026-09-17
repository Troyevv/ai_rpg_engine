"""Player-authored motivation, applied to a copy of the active save aggregate."""
from backend.services.world import normalize
from backend.services.pov import controlled


def edit_motivation(state, actor_id, goals, intentions):
    state = normalize(state)
    if controlled(state) != actor_id or actor_id not in state['world']['characters']:
        raise ValueError('Можно редактировать только текущего управляемого персонажа.')
    if len(goals) > 20 or any(not x.strip() or len(x) > 4000 for x in goals) or len(intentions) > 20 or any(not x.strip() or len(x) > 2000 for x in intentions):
        raise ValueError('Недопустимый размер цели или намерений.')
    current = state['world']['characters'][actor_id]
    current['goals'] = [x.strip() for x in goals]
    current['short_goal'] = '\n\n'.join(current['goals'])
    current['intentions'] = [x.strip() for x in intentions]
    # Keep the legacy card supplied to the GM consistent, including explicit deletion.
    card = next(c for c in state['characters'] if c['id'] == actor_id)
    card['fields']['Чего хочет'] = current['short_goal']
    card['fields']['Намерения'] = '\n\n'.join(current['intentions'])
    return state
