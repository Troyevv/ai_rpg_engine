"""Transient canonical forms for the existing author draft, never another store."""
from copy import deepcopy
from backend.runtime_v3.models import WorldStateV3
from backend.services.initial_world_v2 import normalize, validate_initial_history, _check


SECTIONS = {
    'characters':'Персонажи и личности', 'objective_relations':'Семейные связи',
    'relationships':'Социальные отношения', 'organizations':'Организации',
    'locations':'Локации', 'residences':'Места проживания', 'roles':'Занятия и роли',
    'facts':'Факты и секреты', 'knowledge':'Знания персонажей',
    'scheduled_events':'Обязательства и запланированные события',
    'possessions':'Имущество', 'contacts':'Контакты', 'conditions':'Состояния',
    'pregnancies':'Беременности', 'reproductive_events':'События жизненного цикла',
    'threads':'Предпосылки', 'camera':'Начальная сцена',
    'calendar':'Календарь', 'world_time':'Начальное время', 'initial_history':'Предыстория',
}


def view(state):
    snapshot=normalize(state).snapshot;world=snapshot['world_state']
    schema=WorldStateV3.model_json_schema()
    meta=schema['$defs'][schema['properties']['meta']['$ref'].split('/')[-1]]
    properties={k:schema['properties'][k] for k in SECTIONS if k in schema['properties']}
    properties.update({k:meta['properties'][k] for k in ('calendar','world_time')})
    # History has its own canonical portable-history validator at the boundary.
    properties['initial_history']={'type':'object','additionalProperties':{'type':'array','items':{'type':'object'}}}
    values={k:world[k] for k in SECTIONS if k in world}
    values.update({k:world['meta'][k] for k in ('calendar','world_time')})
    values['initial_history']=snapshot.get('initial_history',{})
    references=[{'id':r['id'],'name':r.get('display_name',r.get('name',r.get('text','')))}
                for kind in ('characters','locations','organizations','facts') for r in world[kind].values()]
    return dict(values=values,sections=SECTIONS,schema={'type':'object','properties':properties,'$defs':schema['$defs']},references=references)


def patch(state,section,value):
    if section not in SECTIONS:raise ValueError('author/section: неизвестный раздел')
    snapshot=deepcopy(normalize(state).snapshot)
    if section=='initial_history':snapshot[section]=value;validate_initial_history(snapshot)
    elif section in ('calendar','world_time'):snapshot['world_state']['meta'][section]=value
    else:snapshot['world_state'][section]=value
    snapshot['world_state']=_check(WorldStateV3,snapshot['world_state'],'world_state').model_dump()
    # Character cards are a projection, not a competing identity/name registry.
    if section=='characters':
        cards={c['id']:c for c in snapshot.get('character_cards',[])}
        snapshot['character_cards']=[{**cards.get(cid,{'id':cid,'fields':{}}),'name':actor['display_name']}
                                     for cid,actor in value.items()]
    return normalize(snapshot).snapshot
