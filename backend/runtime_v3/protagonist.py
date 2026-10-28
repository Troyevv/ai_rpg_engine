"""One transactional role/control boundary; Character identities never move or copy."""
from copy import deepcopy
from typing import Protocol
from backend.runtime_v3.models import assert_world_state_v3_invariants, WorldHistoryV3
from backend.runtime_v3.life import capabilities
from backend.runtime_v3.calendar import current_time
from backend.runtime_v3.milestones import stable_id


class DeathPolicy(Protocol):
    def permits_autonomous_death(self, state: dict, actor_id: str) -> bool: ...


class ConservativeDeathPolicy:
    def permits_autonomous_death(self, state, actor_id):
        return actor_id not in {state['meta'].get('current_protagonist_id'), state['camera']['controlled_actor_id']}


def initialize(snapshot):
    """Read migration only. Historical JSON and old control choices are immutable."""
    state = snapshot['world_state']; meta = state['meta']; camera = state['camera']
    if not meta.get('current_protagonist_id'):
        main = snapshot.get('campaign', {}).get('protagonist_id') or next(
            (c['id'] for c in snapshot.get('character_cards', []) if c.get('is_player')), None)
        if main in state['characters']:
            meta['current_protagonist_id'] = main
            meta['protagonist_periods'] = [dict(actor_id=main,since=meta['world_time'],until=None,operation_id='legacy')]
    reconcile(state)
    return snapshot


def reconcile(state):
    """Death requires explicit succession; incapacity never changes the role."""
    meta = state['meta']; camera = state['camera']; main = meta.get('current_protagonist_id')
    if main and state['characters'][main]['life_status'] == 'dead':
        meta['protagonist_required'] = True
        for period in meta.get('protagonist_periods', []):
            if period['until'] is None: period['until'] = meta['world_time']
    actor = camera.get('controlled_actor_id')
    if actor and (meta.get('protagonist_required') or state['characters'][actor]['life_status']=='dead'):
        camera.update(controlled_actor_id=None,mode='observer',subject_id=camera.get('subject_id') or actor,
                      pov_actor_id=camera.get('pov_actor_id') or actor)


def transition(snapshot, operation, actor_id, operation_id, *, pov_actor_id=None):
    """Pure validated change; persistence/history commit is owned by the caller."""
    result = initialize(deepcopy(snapshot)); state = result['world_state']; meta = state['meta']
    if operation not in ('permanent','temporary','observe','resume'):
        raise ValueError('Неизвестная операция управления.')
    if operation == 'resume': actor_id = meta.get('current_protagonist_id')
    if actor_id not in state['characters']: raise ValueError('Выбери существующего персонажа.')
    actor = state['characters'][actor_id]
    if actor['life_status'] == 'dead': raise ValueError('Умершим персонажем нельзя управлять или выбрать его новым ГГ.')
    if meta.get('protagonist_required') and operation != 'permanent':
        raise ValueError('После смерти главного героя выбери нового главного героя.')
    if operation in ('temporary','resume') and not capabilities(state,actor_id)['can_act']:
        raise ValueError('Персонаж сейчас не способен действовать. Доступно наблюдение.')
    pov = actor_id if pov_actor_id is None else pov_actor_id
    if pov not in state['characters']: raise ValueError('Неизвестный персонаж POV.')
    prior = meta.get('current_protagonist_id'); batch = WorldHistoryV3()
    if operation == 'permanent' and (actor_id != prior or meta.get('protagonist_required')):
        for period in meta['protagonist_periods']:
            if period['until'] is None: period['until'] = meta['world_time']
        meta['protagonist_periods'].append(dict(actor_id=actor_id,since=meta['world_time'],until=None,operation_id=operation_id))
        meta.update(current_protagonist_id=actor_id,protagonist_required=False)
        change = dict(id=stable_id('transition',operation_id),kind='protagonist_transition',entity=actor_id,
            before=dict(actor_id=prior),after=dict(actor_id=actor_id),minute=meta['world_time'],
            date=current_time(state)['date'],turn_id=meta['turn_id'],player_observed=True,
            evidence='Подтверждённая смена главного героя.',source='explicit_confirmation')
        batch.state_changes.append(change)
    lid = actor['location_id']
    present = [cid for cid,c in state['characters'].items() if c['location_id']==lid and c['life_status']!='dead'] if lid else [actor_id]
    controlled = actor_id if operation != 'observe' and capabilities(state,actor_id)['can_act'] else None
    state['meta']['interaction_focus'] = 'physical'
    before_camera=deepcopy(state['camera'])
    state['camera'].update(location_id=lid,present_character_ids=present,controlled_actor_id=controlled,
        subject_id=actor_id,pov_actor_id=pov,mode='actor' if controlled else 'observer',
        situation=actor['situation'],remote_interactions=[],observed_character_ids=[])
    batch.state_changes.append(dict(kind='control_transition',entity=actor_id,before=before_camera,
        after=deepcopy(state['camera']),operation=operation,operation_id=operation_id,turn_id=meta['turn_id']))
    result['world_state'] = assert_world_state_v3_invariants(state)
    return result,batch.to_dict()
