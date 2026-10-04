"""Tolerant input envelope. Optional records are validated independently downstream."""
from dataclasses import dataclass
from copy import deepcopy
import json
from backend.runtime_v3.models import fatal
from backend.services.relation_dimensions import RELATION_DIMENSIONS

SECTIONS = ('locations','promotions','events','facts','knowledge_gained','character_changes',
            'relationship_changes','movements','thread_changes','scheduled_event_changes')


@dataclass
class RawTurnResult:
    final_scene: dict
    records: dict
    choices: list
    warnings: list

    @classmethod
    def parse(cls, payload):
        if isinstance(payload, str):
            text = payload.strip()
            if text.startswith('```') and text.endswith('```') and '\n' in text:
                text = text.split('\n', 1)[1].rsplit('```', 1)[0]
            try:
                payload = json.loads(text)
            except (ValueError, TypeError):
                fatal('некорректный JSON extraction', 'raw_root_invalid', repairable=True)
        if not isinstance(payload, dict) or not isinstance(payload.get('final_scene'), dict):
            fatal('ожидается объект RawTurnResult с final_scene', 'raw_root_invalid', repairable=True)
        warnings, records = [], {}
        for section in SECTIONS:
            values = payload.get(section, [])
            if not isinstance(values, list):
                warnings.append(dict(section=section, code='optional_section_invalid', action='drop_section', reason='ожидался список'))
                values = []
            records[section] = deepcopy(values)
        choices = payload.get('choices', [])
        if not isinstance(choices, list):
            choices = []
        choices = [c for c in choices if isinstance(c, dict) and isinstance(c.get('action'),str) and isinstance(c.get('speech',''),str)][:6]
        return cls(deepcopy(payload['final_scene']), records, choices, warnings)


def extraction_schema():
    def obj(properties, required=()):
        return dict(type='object', properties=properties, required=list(required), additionalProperties=False)
    string = {'type':'string'}
    strings = {'type':'array','items':string}
    evidence = dict(type='string', description='Точная цитата completed_narrative или player_input. Не выдумывай источник.')
    def record(props, required=()):
        return obj(dict(props, evidence=evidence), required)
    definitions = {
        'locations':record(dict(id=string,name=string,description=string), ('id','name','evidence')),
        'promotions':record(dict(id=string,name=string,fields={'type':'object','additionalProperties':string}), ('id','name','fields','evidence')),
        'facts':record(dict(id=string,text=string,visibility={'enum':['public','secret']},character_ids=strings), ('id','text','evidence')),
        'events':record(dict(id=string,text=string,participants=strings,witnesses=strings,fact_ids=strings,
            medium={'enum':['observation','conversation','message','testimony','discovery','action']},
            location_id=string,minute={'type':'integer','minimum':0},order={'type':'integer','minimum':0}), ('id','text','evidence')),
        'knowledge_gained':record(dict(actor_id=string,fact_id=string,status={'enum':['known','suspected','unknown']},
            source_event_id=dict(type='string',description='Event ЭТОГО extraction: actor_id входит в witnesses, fact_id входит в fact_ids, medium observation/conversation/message/testimony/discovery. Иначе запись опустить.')),
            ('actor_id','fact_id','source_event_id','evidence')),
        'character_changes':record(dict(id=string,situation=string,physical_state=string,emotion=string,goals=strings,intentions=strings,obligations=strings,
            player_evidence=obj(dict(emotion=string,goals=strings,intentions=strings,obligations=strings))), ('id',)),
        'relationship_changes':record(dict(source_id=string,target_id=string,context=string,
            dimensions=obj({d:{'type':'number','minimum':-100,'maximum':100} for d in RELATION_DIMENSIONS})), ('source_id','target_id','evidence')),
        'movements':record(dict(actor_id=string,to_location_id=string,order={'type':'integer','minimum':0}), ('actor_id','to_location_id','evidence')),
        'thread_changes':record(dict(id=string,description=string,character_ids=strings,status={'enum':['active','developing','dormant','resolved','paused']},state=string,relevance={'type':'number','minimum':0,'maximum':1}), ('id','evidence')),
        'scheduled_event_changes':record(dict(id=string,description=string,character_ids=strings,due_minute={'type':'integer','minimum':0},status={'enum':['pending','resolved','cancelled']},condition=string,type=string), ('id','evidence')),
    }
    for field in ('goals', 'intentions', 'obligations'):
        definitions['character_changes']['properties'][field+'_updates'] = dict(type='array', items=record(dict(
            id=string, text=string, status={'enum':['active','completed','cancelled','failed','superseded']},
            due_minute={'type':'integer','minimum':0}), ('status','evidence')))
    definitions['scheduled_event_changes']['properties']['location_id'] = string
    definitions['scheduled_event_changes']['properties']['interrupts'] = {'type':'boolean', 'description':'Только установленное событие, требующее восприятия или участия controlled actor.'}
    from backend.services.world import CARD_FIELDS
    definitions['promotions']['properties']['fields']=obj({key:string for key in CARD_FIELDS},CARD_FIELDS)
    from backend.services.player_agency import PLAYER_SOURCE_DESCRIPTION
    for field in ('emotion','goals','intentions','obligations'):
        definitions['character_changes']['properties'][field]=dict(definitions['character_changes']['properties'][field],description=PLAYER_SOURCE_DESCRIPTION)
    definitions['relationship_changes']['properties']['dimensions']['description']='Закрытый набор: '+', '.join(RELATION_DIMENSIONS)+'. Не добавляй ключи; иной смысл — в context.'
    schema = obj(dict(final_scene=obj(dict(location_id={'type':['string','null']},present_character_ids=strings,
        situation=string,situation_evidence=evidence,elapsed_minutes={'type':'integer','minimum':0,'maximum':10080}), ('location_id','present_character_ids')),
        choices={'type':'array','items':obj(dict(action=string,speech=string),('action','speech'))}, **{key:{'type':'array','items':value} for key,value in definitions.items()}), ('final_scene',))
    schema['description'] = ('RawTurnResult: только наблюдения и подтверждённые изменения. Не создавай StatePatch. '
        'Final scene задаёт конечное положение участников; movements нужны только для остальных. '
        'Не копируй from_location, scene_id, last_event_id. Не придумывай время Event. '
        'Dimensions — закрытый набор; непредставимый смысл сохраняй в context.')
    return schema
