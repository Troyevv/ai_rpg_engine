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
    source=snapshot.get('campaign',{}).get('initial_world',{})
    if source.get('version')=='world-authoring-1':
        from backend.services.world_authoring import Document
        from backend.services.world_authoring_pipeline import compiled_hash
        document=source['source_document']
        labels={**SECTIONS, 'world':'Описание мира','feelings':'Направленные чувства',
                'events':'События предыстории','commitments':'Обязательства','opening':'Начальная сцена','uncertainties':'Неоднозначности'}
        return dict(values=document,sections={k:labels.get(k,k) for k in document if k!='version'},
            schema=Document.model_json_schema(),references=[{'id':r['key'],'name':r['name']} for k in ('characters','locations','organizations') for r in document[k]],
            contract='world-authoring-1',compiled_conflict=compiled_hash(snapshot)!=source.get('compiled_hash'))
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


def patch(state,section,value,*,ack=False):
    snapshot=normalize(state).snapshot
    source=snapshot.get('campaign',{}).get('initial_world',{})
    if source.get('version')=='world-authoring-1':
        from backend.services.world_authoring import Document
        from backend.services.world_authoring_compiler import compile_document
        from backend.services.world_authoring_pipeline import compiled_hash, mark_author_changes
        if section not in Document.model_fields or section=='version':raise ValueError('author/section: неизвестный раздел')
        if compiled_hash(snapshot)!=source.get('compiled_hash') and not ack:
            raise ValueError('author/conflict: есть ручные правки скомпилированного мира. Подтвердите их замену перед повторной компиляцией.')
        document=deepcopy(source['source_document']);document[section]=value
        document=mark_author_changes(source['source_document'],document)
        result=compile_document(document,source.get('id_map'),snapshot['campaign'].get('creation'))
        result.snapshot['campaign']['initial_world']={**source,'source_document':document,'id_map':result.id_map,
            'compiled_hash':compiled_hash(result.snapshot),'diagnostics':result.diagnostics}
        return result.snapshot
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
