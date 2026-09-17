"""Player-authored motivation, applied to a copy of the active save aggregate."""
from backend.services.world import normalize
from backend.services.pov import controlled


def edit_motivation(state, actor_id, short_goal, intentions):
    state = normalize(state)
    if controlled(state) != actor_id or actor_id not in state['world']['characters']:
        raise ValueError('Можно редактировать только текущего управляемого персонажа.')
    if len(short_goal) > 4000 or len(intentions) > 20 or any(not x.strip() or len(x) > 2000 for x in intentions):
        raise ValueError('Недопустимый размер цели или намерений.')
    current = state['world']['characters'][actor_id]
    current['short_goal'] = short_goal.strip()
    current['intentions'] = [x.strip() for x in intentions]
    # Keep the legacy card supplied to the GM consistent, including explicit deletion.
    card = next(c for c in state['characters'] if c['id'] == actor_id)
    card['fields']['Чего хочет'] = current['short_goal']
    card['fields']['Намерения'] = '\n\n'.join(current['intentions'])
    return state
