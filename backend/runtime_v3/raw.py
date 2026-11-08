"""Tolerant input envelope. Optional records are validated independently downstream."""
from dataclasses import dataclass
from copy import deepcopy
from functools import lru_cache
import json
from backend.runtime_v3.models import TemporalValue, fatal
from backend.services.relation_dimensions import RELATION_DIMENSIONS

SECTIONS = ('secret_disclosures','group_request_changes','group_response_changes','remote_events','call_lifecycle_changes','physical_projections','scene_transitions','continuity_beats','scene_actions','narrative_developments','consequences','locations','promotions','events','facts','knowledge_gained','character_changes',
            'relationship_changes','movements','thread_changes','scheduled_event_changes',
            'life_changes','condition_changes','social_relation_changes',
            'location_changes','organization_changes','residence_changes','role_changes',
            'development_evidence','personality_deltas','value_deltas',
            'reproductive_events','naming_decisions','births','appearance_deltas','possession_deltas')


OPTIONAL_SECTIONS = frozenset(('physical_projections','scene_transitions','continuity_beats','scene_actions','narrative_developments','consequences'))

@dataclass
class RawTurnResult:
    final_scene: dict
    records: dict
    choices: list
    warnings: list
    player_agency: dict | None = None

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
        for field in set(payload['final_scene']) - input_fields()['final_scene']:
            warnings.append(dict(section='final_scene', path='final_scene.'+field,
                                 code='raw_unknown_field', action='ignore_field'))
        for key, value in payload.items():
            if key in ('diagnostic', 'diagnostics'):
                warnings.append(dict(section=key, path=key, code='raw_feedback_ignored',
                                     action='ignore_field'))
                continue  # Input-only feedback is never executable world data.
            if key not in (*SECTIONS, 'final_scene', 'choices', 'metadata', 'player_agency'):
                if value not in (None, '', [], {}):
                    fatal('неизвестное непустое поле Extraction', 'raw_unknown_field', repairable=True,
                          section=key, path=key, severity='recoverable', action='extraction_repair')
                warnings.append(dict(section=key, path=key, code='raw_unknown_field', action='ignore_empty'))
        for section in SECTIONS:
            values = payload.get(section, [])
            if not isinstance(values, list):
                if section not in OPTIONAL_SECTIONS and values not in (None, '', {}):
                    fatal('повреждена существенная секция Extraction', 'raw_section_invalid', repairable=True, section=section, path=section, action='extraction_repair', severity='recoverable')
                warnings.append(dict(section=section, code='optional_section_invalid', action='drop_section', reason='ожидался список'))
                values = []
            if section == 'births' and len(values) > 24:
                fatal('Превышен лимит исходов рождения.', 'birth_budget', repairable=True, section=section, path=section)
            if section == 'knowledge_gained' and len(values) > 64:
                fatal('Превышен лимит изменений Knowledge.', 'knowledge_budget', repairable=True, section=section, path=section)
            if section in ('development_evidence','personality_deltas','value_deltas','appearance_deltas','possession_deltas') and len(values) > 24:
                fatal('Превышен лимит изменений домена.', 'development_budget', repairable=True, section=section, path=section)
            records[section] = deepcopy(values)
            for index, item in enumerate(records[section]):
                if isinstance(item, dict):
                    for field in set(item) - input_fields().get(section, set()):
                        path=f'{section}[{index}].{field}'
                        legacy_metadata=section=='movements' and field in ('id','from_location','to_location','scene_id','minute')
                        if section in ('life_changes','condition_changes','movements') and not legacy_metadata and item[field] not in (None,'',[],{}):
                            fatal('Неизвестное поле существенного изменения.', 'raw_unknown_field', repairable=True, section=section, path=path)
                        warnings.append(dict(section=section,index=index,path=path,code='raw_unknown_field',action='ignore_field'))
                    if section == 'promotions':
                        from backend.services.npc_review import promotion_card
                        promotion_card(item)
                    if not isinstance(item.get('evidence', ''), str):
                        warnings.append(dict(section=section, path=section+'.evidence', code='evidence_metadata_invalid', action='drop_field'))
                        item['evidence']=''
                    item.setdefault('evidence', '')
                elif section not in OPTIONAL_SECTIONS and item not in (None, [], {}):
                    fatal('Повреждена запись существенной секции.', 'raw_record_invalid', repairable=True, section=section, action='extraction_repair')
        choices = payload.get('choices', [])
        if not isinstance(choices, list):
            choices = []
        choices = [c for c in choices if isinstance(c, dict) and isinstance(c.get('action'),str) and isinstance(c.get('speech',''),str)][:6]
        return cls(deepcopy(payload['final_scene']), records, choices, warnings, deepcopy(payload.get('player_agency')))


def repair_revision_warnings(previous, current):
    """Audit revised proposals, never adjudicate which Extraction is true.

    A rejected attempt has no canonical outcomes, even if individual records
    passed validation before a later failure. Committed before/History remain
    protected by domain handlers and the existing transaction boundary.
    Full old/new responses and their provenance live in the request log.
    """
    if previous is None: return []
    sections = ['final_scene'] + [name for name in SECTIONS if name not in OPTIONAL_SECTIONS]
    warnings = [dict(type='extraction_revision', section=section, code='extraction_revised',
                 action='use_revised_extraction',
                 reason='Изменён предварительный результат Extraction; различие JSON не доказывает правильность интерпретации.')
            for section in sections
            if (previous.final_scene if section == 'final_scene' else previous.records[section]) !=
               (current.final_scene if section == 'final_scene' else current.records[section])]
    if previous.player_agency != current.player_agency:
        warnings.append(dict(type='extraction_revision', section='player_agency', code='extraction_revised',
                             action='use_revised_extraction', reason='Пересмотрена проверка действий игрока.'))
    return warnings


def extraction_schema():
    def obj(properties, required=()):
        return dict(type='object', properties=properties, required=list(required), additionalProperties=False)
    string = {'type':'string'}
    strings = {'type':'array','items':string}
    evidence = dict(type='string', description='Точная цитата completed_narrative или player_input. Не выдумывай источник.')
    def record(props, required=()):
        return obj(dict(props, evidence=evidence), required)
    definitions = {
        'locations':record(dict(id=string,name=string,description=string,parent_id=string,kind=string,aliases=strings), ('id','name','evidence')),
        'promotions':record(dict(id=string,name=string,fields={'type':'object','additionalProperties':string}), ('id','name','fields','evidence')),
        'facts':record(dict(id=string,text=string,claim=obj(dict(subject_id=string,predicate=string,value=string,scope=string),('subject_id','predicate','value')),visibility={'enum':['public','secret']},story_secret={'type':'boolean'},secret_subject_ids=strings,secret_keeper_ids=strings,secret_biography_ids=strings,secret_existence={'enum':['hidden','discoverable']},character_ids=strings), ('id','text','evidence')),
        'events':record(dict(id=string,text=string,advance_candidate_ids=dict(type='array',items=string,maxItems=3,description='Only for Long-term Advance: selected cause IDs whose outcome this event establishes.'),participants=strings,witnesses=strings,fact_ids=strings,
            author_id=string, actor_id=string, target_ids=strings, player_action_id=string, player_evidence=string, player_assertion={'enum':['completed_interaction']},
            medium={'enum':['observation','conversation','message','testimony','discovery','action']},
            location_id=string,minute={'type':'integer','minimum':0},order={'type':'integer','minimum':0}), ('id','text','evidence')),
        'knowledge_gained':record(dict(actor_id=string,fact_id=string,status={'enum':['known','suspected','unknown','outdated','refuted','superseded']},
            expected_revision={'type':'integer','minimum':0},supersedes=dict(type='array',items=string,maxItems=16),
            source_event_id=dict(type='string',description='Event ЭТОГО extraction: actor_id входит в witnesses, fact_id входит в fact_ids, medium observation/conversation/message/testimony/discovery. Для подтверждённого раскрытия согласуй Event.fact_ids; не теряй приобретение при пропущенной ссылке.')),
            ('actor_id','fact_id','source_event_id','evidence')),
        'character_changes':record(dict(id=string,source_event_id=string,birth_date=string,situation=string,physical_state=string,emotion=string,goals=strings,intentions=strings,obligations=strings,
            emotion_assertion={'enum':['explicit_internal_state'], 'description':'Только явно выраженное внутреннее состояние controlled actor из player_input, не жест/поведение. Runtime проверяет источник, LLM — семантику.'},
            player_evidence=obj(dict(emotion=string,goals=strings,intentions=strings,obligations=strings))), ('id',)),
        'relationship_changes':record(dict(source_id=string,target_id=string,context=string,
            source_event_ids=dict(type='array',items=string,minItems=1,maxItems=8,uniqueItems=True),
            assertion={'enum':['grounded_feelings']},rationale=string,
            player_evidence=string,player_assertion={'enum':['explicit_directed_feelings']},
            dimensions=obj({d:{'type':'number','minimum':-100,'maximum':100} for d in RELATION_DIMENSIONS})), ('source_id','target_id','evidence')),
        'movements':record(dict(player_evidence=string,player_assertion={'enum':['explicit_choice','involuntary']},source_event_id=string,actor_id=string,to_location_id=string,from_location_id={'type':['string','null']},assertion={'enum':['completed_arrival']},actor_evidence=string,destination_evidence=string,order={'type':'integer','minimum':0}), ('actor_id','to_location_id','evidence')),
        'thread_changes':record(dict(id=string,description=string,character_ids=strings,status={'enum':['active','developing','dormant','resolved','paused']},state=string,relevance={'type':'number','minimum':0,'maximum':1}), ('id','evidence')),
        'scheduled_event_changes':record(dict(id=string,description=string,character_ids=strings,due_minute={'type':'integer','minimum':0},temporal=TemporalValue.model_json_schema(),status={'enum':['pending','resolved','cancelled']},condition=string,type=string), ('id','evidence')),
    }
    from backend.runtime_v3.remote_models import SecretDisclosure
    definitions['secret_disclosures'] = record(dict(source_event_id=string, **SecretDisclosure.model_json_schema()['properties']), ('source_event_id','fact_id','assertion','evidence'))
    from backend.runtime_v3.narrative_policy_models import NarrativeDevelopment, ConsequenceClaim, FavorablePath
    from backend.runtime_v3.initiative import SceneAction
    from backend.runtime_v3.continuity import ContinuityBeat, SceneTransition, Compression, DueBirthAssessment
    definitions['continuity_beats'] = ContinuityBeat.model_json_schema()
    definitions['scene_transitions'] = SceneTransition.model_json_schema()
    definitions['thread_changes']['properties']['source_event_id'] = dict(type='string', description='Event этого ответа, через который свидетели узнали о новой линии. Участие в character_ids/stakes_for не означает осведомлённость. Без источника новая линия остаётся скрытой.')
    definitions['scene_actions'] = SceneAction.model_json_schema()
    definitions['narrative_developments'] = NarrativeDevelopment.model_json_schema()
    definitions['consequences'] = ConsequenceClaim.model_json_schema()
    definitions['thread_changes']['properties'].update(resolution={'enum':['favorable','negative','open']}, stakes_for=strings, favorable_path=FavorablePath.model_json_schema(), player_evidence=string, player_assertion={'enum':['explicit_choice']})
    definitions['development_evidence'] = record(dict(id=string, actor_id=string, source_event_id=string,
        source_kind={'enum':['event','milestone']}, meaning=string, kind={'enum':['behavior','experience','turning_point']},
        player_evidence=string, player_assertion={'enum':['completed_voluntary_behavior']},
        assertion={'enum':['completed']}), ('id','actor_id','source_event_id','meaning','kind','assertion','evidence'))
    definitions['personality_deltas'] = record(dict(actor_id=string,
        evidence_ids=strings, rationale=string, developmental_fit={'enum':['established_capability']},
        operations={'type':'array','maxItems':3,'items':obj(dict(
            item_id=string, field={'enum':['traits','communication','habits','strengths','weaknesses','fears','preferences','temperament']},
            operation={'enum':['establish','refine','retire']}, text=string,
            expected_text={'type':['string','null']}, expected_revision={'type':'integer','minimum':0}),
            ('item_id','field','operation','expected_text','expected_revision'))}),
        ('actor_id','evidence_ids','rationale','developmental_fit','operations','evidence'))
    definitions['value_deltas'] = record(dict(actor_id=string,item_id=string,
        operation={'enum':['establish','refine','retire']},text=string,
        expected_revision={'type':'integer','minimum':0},expected_text={'type':['string','null']},
        basis={'enum':['explicit_statement','sustained_behavior']},evidence_ids=strings,source_event_id=string,
        player_evidence=string,player_assertion={'enum':['explicit_value']},rationale=string),
        ('actor_id','item_id','operation','expected_revision','expected_text','basis','evidence','rationale'))
    agency = dict(assertion={'enum':['established']}, player_evidence=string,
                  player_assertion={'enum':['explicit_choice']}, decision_actor_id=string)
    definitions['location_changes'] = record(dict(id=string, assertion={'enum':['established']},
        parent_id={'type':['string','null']}, kind=string, aliases=strings), ('id','assertion','evidence'))
    phase = dict(id=string, **agency, actor_id=string, fact_id=string, closure_fact_id=string,
        status={'enum':['active','closed']}, outcome=string, context=string,
        transition={'enum':['voluntary','external']}, replaces=strings)
    definitions['residence_changes'] = record(dict(phase, location_id=string), ('id','assertion','evidence'))
    definitions['role_changes'] = record(dict(phase, kind=string, title=string, organization_id=string, field=string), ('id','assertion','evidence'))
    definitions['role_changes']['properties']['significance'] = {'enum':['major','routine']}
    definitions['organization_changes'] = record(dict(id=string, assertion={'enum':['established']},
        name=string, kind=string, aliases=strings, location_ids=strings, status={'enum':['active','closed','unknown']},
        context=string, fact_id=string, closure_fact_id=string), ('id','assertion','evidence'))
    caps = obj({key:{'type':'boolean'} for key in ('conscious','can_perceive','can_act','can_speak','can_move')})
    definitions['life_changes'] = record(dict(id=string, **agency,
        life_status={'enum':['alive','dead','missing','unknown']}, display_name=string,
        developmental_stage={'enum':['unknown','infant','child','adolescent','adult']},
        capabilities=caps, fact_id=string, parentage_complete_fact_id=string), ('id','assertion','evidence'))
    definitions['condition_changes'] = record(dict(id=string, **agency, actor_id=string,
        description=string, effects=caps, duration={'enum':['temporary','persistent','unknown']},
        status={'enum':['active','resolved','cancelled','unknown_outcome']}, fact_id=string), ('id','assertion','evidence'))
    from backend.runtime_v3.models import ObjectiveRelation
    kinds = list(ObjectiveRelation.model_fields['kind'].annotation.__args__) + ['child']
    definitions['social_relation_changes'] = record(dict(id=string, **agency, kind={'enum':kinds},
        source_id=string,target_id=string,status={'enum':['active','closed']},context=string,
        outcome={'enum':['ended','divorced','widowed','superseded','revoked']},fact_id=string,closure_fact_id=string),
        ('id','assertion','evidence'))
    for field in ('goals', 'intentions', 'obligations'):
        definitions['character_changes']['properties'][field+'_updates'] = dict(type='array', items=record(dict(
            id=string, text=string, status={'enum':['active','completed','cancelled','failed','superseded','expired','blocked']},
            expected_revision={'type':'integer','minimum':0}, source_event_id=string,
            player_evidence=string, player_assertion={'enum':['explicit_choice']},
            assertion={'enum':['completed','abandoned','superseded','impossible','unblocked','still_active','established']},
            dependencies=obj({key:dict(type='array',items=string,maxItems=8) for key in ('characters','roles','organizations')}),
            due_minute={'type':'integer','minimum':0}), ('status','evidence')))
    scheduled = definitions['scheduled_event_changes']
    from backend.runtime_v3.commitments import ASSERTIONS
    scheduled['required'].append('assertion')
    scheduled['properties'].update(assertion={'enum':list(ASSERTIONS)},
        decision_actor_id=string, player_evidence=string, player_assertion={'enum':['explicit_choice']},
        depends_on=dict(type='array', items=string, maxItems=16),
        end_temporal=deepcopy(scheduled['properties']['temporal']))
    definitions['scheduled_event_changes']['properties']['location_id'] = string
    definitions['scheduled_event_changes']['properties']['interrupts'] = {'type':'boolean', 'description':'Только установленное событие, требующее восприятия или участия controlled actor.'}
    for section in ('life_changes','condition_changes','social_relation_changes','residence_changes','role_changes','organization_changes','character_changes','scheduled_event_changes'):
        definitions[section]['properties'].update(source_event_id=string, source_process_id=string)
    from backend.runtime_v3.reproduction import ServiceClaim, NameClaim, BirthClaim
    for section, model in (('reproductive_events', ServiceClaim), ('naming_decisions', NameClaim), ('births', BirthClaim)):
        def wire_schema(node):
            if isinstance(node,dict): return {k:wire_schema(v) for k,v in node.items() if k not in ('title','default')}
            if isinstance(node,list): return [wire_schema(v) for v in node]
            return node
        definitions[section] = wire_schema(model.model_json_schema())
        # Pydantic refs are root-relative; this schema is embedded in an array
        # inside RawTurnResult. Inline the small nested disclosure model here.
        nested = definitions[section].pop('$defs', {})
        def inline_models(node):
            if isinstance(node, dict):
                ref = node.get('$ref', '').removeprefix('#/$defs/')
                if ref in nested: return inline_models(nested[ref])
                return {k:inline_models(v) for k,v in node.items()}
            if isinstance(node, list): return [inline_models(v) for v in node]
            return node
        definitions[section] = inline_models(definitions[section])
    definitions['life_changes']['properties'].update(
        reproductive_capability={'enum':['can_become_pregnant','can_impregnate','neither','unknown']},
        identity_components={'type':'object','additionalProperties':string})
    from backend.runtime_v3.appearance import AppearanceDelta
    definitions['appearance_deltas'] = wire_schema(AppearanceDelta.model_json_schema())
    from backend.runtime_v3.remote_models import ExtractedRemoteEvent
    remote_schema = ExtractedRemoteEvent.model_json_schema()
    contact_schema = remote_schema.pop('$defs')['EstablishedContact']
    remote_schema['properties']['established_contact'] = {'anyOf':[contact_schema, {'type':'null'}]}
    definitions['remote_events'] = remote_schema
    from backend.runtime_v3.remote_models import GroupResponseChange, GroupRequestChange
    definitions['group_request_changes'] = GroupRequestChange.model_json_schema()
    definitions['group_response_changes'] = GroupResponseChange.model_json_schema()
    from backend.runtime_v3.possessions import PossessionDelta
    definitions['possession_deltas'] = wire_schema(PossessionDelta.model_json_schema())
    for section in ('social_relation_changes','role_changes','residence_changes'):
        definitions[section]['properties']['consequence_outcome'] = {'enum':['loss','constructive']}
    for section in ('life_changes','condition_changes','social_relation_changes','residence_changes','role_changes'):
        definitions[section]['required'].remove('assertion')
    movement = definitions['movements']
    movement['description'] = ('Only arrivals actually completed in completed_narrative; future_intent and departure alone are NOT movements. '
        'Keep departure Event and END absence without inventing an endpoint. Preserve confirmed route legs/order.')
    movement['properties']['to_location_id'] = dict(string, description='ID from canonical locations or validated locations[] in THIS response, reached in this Narrative; never null or merely planned.')
    movement['properties']['destination_evidence'] = dict(string, description='Evidence of completed arrival, not a destination named in a plan/promise. Exit evidence alone is insufficient.')
    from backend.services.world import CARD_FIELDS
    definitions['promotions']['properties']['fields']=obj({key:string for key in CARD_FIELDS},CARD_FIELDS)
    from backend.runtime_v3.npc_identity import initial_schema
    definitions['promotions']['properties']['character'] = initial_schema()
    definitions['promotions']['required'].append('character')
    from backend.services.player_agency import PLAYER_SOURCE_DESCRIPTION
    for field in ('emotion','goals','intentions','obligations'):
        definitions['character_changes']['properties'][field]=dict(definitions['character_changes']['properties'][field],description=PLAYER_SOURCE_DESCRIPTION)
    definitions['relationship_changes']['properties']['dimensions']['description']='Закрытый набор: '+', '.join(RELATION_DIMENSIONS)+'. Не добавляй ключи; иной смысл — в context.'
    definitions['events']['dependentRequired'] = {
        'player_action_id': ['actor_id', 'target_ids', 'player_evidence'],
        'player_assertion': ['player_action_id'],
    }
    from backend.runtime_v3.player_actions import PlayerAgencyReview
    agency_schema = PlayerAgencyReview.model_json_schema()
    agency_defs = agency_schema.pop('$defs')
    agency_schema['properties']['actions']['items'] = agency_defs['PlayerAction']
    agency_schema['properties']['narrative_audit'] = dict(
        anyOf=[dict(type='array', items=agency_defs['NarrativeAgencyItem']), dict(type='null')], default=None)
    schema = obj(dict(player_agency=agency_schema, metadata={'type':'object','additionalProperties':True},final_scene=obj(dict(location_id={'type':['string','null']},present_character_ids=strings,observed_character_ids=strings,
        remote_interactions={'type':'array','items':record(dict(actor_id=string,
            channel={'enum':['message','phone','video','radio','other']}), ('actor_id','channel','evidence')),
            'description':'Только продолжающееся в конце хода активное удалённое взаимодействие. Старое сообщение, план позвонить и упоминание не подходят. Повторно подтверди каждый ход; отсутствие/[] завершает взаимодействие.'},
        due_birth_assessments=dict(type='array', items=DueBirthAssessment.model_json_schema(), maxItems=24),
        compression=Compression.model_json_schema(),situation=string,situation_evidence=evidence,elapsed_minutes={'type':'integer','minimum':0,'maximum':10080}), ('location_id','present_character_ids')),
        choices={'type':'array','items':obj(dict(action=string,speech=string,basis_ids=strings,kind={'enum':['question','proposal','information','decision','opportunity']}),('action','speech'))}, **{key:{'type':'array','items':value} for key,value in definitions.items()}), ('final_scene',))
    schema['description'] = ('RawTurnResult: только наблюдения и подтверждённые изменения. Не создавай StatePatch. '
        'Final scene — конечный состав сцены, не доказательство прибытия: смена установленного положения требует movements/source_event_id принятого Event. observed — видимые вне сцены. '
        'Не копируй scene_id, last_event_id. Не придумывай время Event. '
        'Dimensions — закрытый набор; непредставимый смысл сохраняй в context.')
    def optional_evidence(node):
        if isinstance(node, dict):
            if isinstance(node.get('required'), list):
                node['required'] = [k for k in node['required'] if k != 'evidence']
            for value in node.values(): optional_evidence(value)
        elif isinstance(node, list):
            for value in node: optional_evidence(value)
    optional_evidence(schema)
    return schema


@lru_cache(maxsize=1)
def input_fields():
    """Producer fields plus the conditional phone/LTA extensions of this schema."""
    fields={key:set(value['items'].get('properties',{})) for key,value in extraction_schema()['properties'].items()
            if key in SECTIONS}
    fields['events'].add('interaction_channel')
    fields['scheduled_event_changes'].update(('remote_source_ids','remote_time_source_id','player_source_id','call_time_source_id','call_evidence'))
    fields['call_lifecycle_changes']={'call_id','actor_id','assertion','evidence','player_evidence'}
    fields['physical_projections']={'event_id','text','evidence'}
    fields['final_scene']=set(extraction_schema()['properties']['final_scene']['properties'])
    return fields


def prompt_schema(*, relationship_evidence=True, reproduction=True, births=True, favorable_paths=True, communication=None, groups=True, voice=False, elapsed_required=False, historical=True, player_agency_required=False, agency_audit_required=True, consequence_first=False, grounded_choices=False, explicit_departures=False):
    """Model-facing projection of canonical types, with focused field guidance."""
    from collections import Counter
    def structural(node):
        if isinstance(node, dict):
            result = {k:structural(v) for k,v in node.items() if (k != 'title' or not isinstance(v,str)) and k != 'default' and (k != 'description' or not isinstance(v, str))}
            # Lossless JSON Schema reductions keep new optional domains inside
            # existing model limits; runtime validation is unchanged.
            if result.get('type') == 'string' and (isinstance(result.get('const'), str) or
                    isinstance(result.get('enum'), list) and all(isinstance(v, str) for v in result['enum'])):
                result.pop('type')
            choices = result.get('anyOf')
            if isinstance(choices, list) and choices and all(isinstance(c, dict) and set(c) == {'type'} and isinstance(c['type'], str) for c in choices):
                result.pop('anyOf')
                result['type'] = list(dict.fromkeys(c['type'] for c in choices))
            # Nullable enums have an equivalent enum union, without duplicating
            # an anyOf wrapper and a null schema at every optional discriminator.
            choices = result.get('anyOf')
            if isinstance(choices,list) and choices and all(
                    isinstance(c,dict) and (set(c)=={'enum'} or c=={'type':'null'}) for c in choices):
                result.pop('anyOf')
                result['enum']=[v for c in choices for v in (c['enum'] if 'enum' in c else [None])]
            if result.get('required') == []: result.pop('required')
            return result
        if isinstance(node, list): return [structural(v) for v in node]
        return node
    # Keep properties named "description"; remove only JSON Schema annotations.
    schema = structural(extraction_schema())
    # New generation requires provenance; legacy raw/saved payloads remain readable.
    schema['properties']['movements']['items']['required'] += ['assertion', 'source_event_id']
    if explicit_departures:
        movement = schema['properties']['movements']['items']
        movement['properties']['assertion'] = {'enum': ['completed_arrival', 'departure']}
        movement['properties']['to_location_id'] = {'type': ['string', 'null']}
        movement['description'] = 'Arrival: reached endpoint. Departure: null endpoint, known from_location_id, accepted departure Event at origin; same order. END absence alone changes no geography.'
    if grounded_choices:
        choice = schema['properties']['choices']['items']
        choice['properties']['grounding'] = {'type':'object', 'additionalProperties':False,
            'properties':{'fact_ids':{'type':'array','items':{'type':'string'}},
                          'scene_evidence':{'type':'array','items':{'type':'string'}}},
            'required':['fact_ids','scene_evidence']}
        choice['required'].append('grounding')
    if player_agency_required:
        if not consequence_first:
            schema['required'].append('player_agency')
        agency = schema['properties']['player_agency']
        if agency_audit_required:
            if not consequence_first:
                agency['required'].append('narrative_audit')
            agency['properties']['narrative_audit'] = agency['properties']['narrative_audit']['anyOf'][0]
            action = agency['properties']['actions']['items']
            action['required'].append('target_mode')
            action['properties']['player_evidence']['description'] = 'Exact current input quote, once.'
            action['properties']['target_ids']['description'] = 'Intended canonical targets, not witnesses; noncanonical objects=[].'
            action['properties']['narrative_target_ids']['description'] = 'Actual targets; partial=subset, deferred may be [].'
            action['properties']['target_mode']['description'] = 'interaction=contact; reference=observe/mention, no delivery.'
            agency['properties']['narrative_audit']['description'] = ('Optional findings; incidental_detail/uncertain grant no canonical authority.' if consequence_first else 'Significant controlled acts across WHOLE prose, even outside Events.')
            event = schema['properties']['events']['items']
            event['dependentRequired']['player_action_id'] = ['actor_id', 'target_ids']
            event['properties']['player_action_id']['description'] = 'Reviewed action ID; quote inherited. NPC reply stays separate.'
            event['properties']['target_ids']['description'] = 'Own achieved targets: subset of action actual targets; union covers them.'
        else:
            agency['properties'].pop('narrative_audit')
    else:
        schema['properties'].pop('player_agency')
        schema['properties']['events']['items'].pop('dependentRequired', None)
        for field in ('actor_id', 'target_ids', 'player_action_id'):
            schema['properties']['events']['items']['properties'].pop(field)
    if elapsed_required:
        schema['properties']['final_scene']['required'].append('elapsed_minutes')
    if not relationship_evidence:
        for field in ('source_event_ids', 'assertion', 'rationale'):
            schema['properties']['relationship_changes']['items']['properties'].pop(field)
    if not historical:
        remote = schema['properties']['remote_events']['items']['properties']
        remote.pop('artifact_id', None)
        remote.pop('reader_id', None)
        remote['channel']['enum'] = ['TEXT_MESSAGE', 'VOICE_CALL']
    if not groups:
        schema['properties'].pop('group_request_changes', None)
        schema['properties'].pop('group_response_changes', None)
    if communication is False:
        schema['properties'].pop('remote_events')
    if communication:
        schema['properties']['events']['items']['properties']['interaction_channel']={'enum':['physical','call']}
        props=schema['properties']['scheduled_event_changes']['items']['properties']
        props['remote_source_ids']={'type':'array','items':{'type':'string'},'maxItems':8}
        props['remote_time_source_id']={'type':'string'}
        props['player_source_id']={'type':'string'}
        schema['properties']['choices']['items']['properties']['device_control']={'enum':['answer','decline','ignore','end']}
    if voice:
        schema['properties']['call_lifecycle_changes']={'type':'array','maxItems':1,'items':{'type':'object','properties':{'call_id':{'type':'string'},'actor_id':{'type':'string'},'assertion':{'enum':['completed_end']},'evidence':{'type':'string'},'player_evidence':{'type':'string'}},'required':['call_id','actor_id','assertion']}}
        schema['properties']['physical_projections']={'type':'array','items':{'type':'object','properties':{'event_id':{'type':'string'},'text':{'type':'string'}},'required':['event_id','text']}}
        props=schema['properties']['scheduled_event_changes']['items']['properties']
        props['call_time_source_id']={'type':'string'}
        props['call_evidence']={'type':'array','maxItems':8,'items':{'type':'object','properties':{'source_id':{'type':'string'},'actor_id':{'type':'string'},'quote':{'type':'string'},'assertion':{'enum':['proposal','assent','cancellation','outcome']}},'required':['source_id','actor_id','quote','assertion']}}
        schema['properties']['choices']['items']['properties']['interaction_channel']={'enum':['physical','call']}
    if not favorable_paths:
        for key in ('favorable_path','resolution','stakes_for'):
            schema['properties']['thread_changes']['items']['properties'].pop(key,None)
    if not reproduction:
        for field in ('reproductive_events','naming_decisions','births'):
            schema['properties'].pop(field)
    if not births: schema['properties'].pop('births',None)
    if not reproduction or not births:
        schema['properties']['final_scene']['properties'].pop('due_birth_assessments', None)
    if agency_audit_required:
        schema['properties']['events']['items']['properties']['minute']['description'] = 'Known absolute world minute; otherwise OMIT. Sequence uses order.'
        # Preserve only high-risk birth-source annotations, not all domain prose.
        def birth_guidance(node):
            if isinstance(node, dict):
                props = node.get('properties', {})
                if 'basis' in props and 'source_actor_id' in props:
                    props['basis']['description'] = 'announcement=spoken disclosure; observation=direct perception of the child, not hearing a speaker.'
                    props['source_actor_id']['description'] = 'Actual canonical speaker, null for a genuinely unknown speaker; never substitute a listener.'
                for child in node.values(): birth_guidance(child)
            elif isinstance(node, list):
                for child in node: birth_guidance(child)
        birth_guidance(schema['properties'].get('births', {}))
        schema['properties'] = {**{k:v for k,v in schema['properties'].items() if k != 'final_scene'},
                                'final_scene': schema['properties']['final_scene']}
    counts = Counter()

    def key(node):
        return json.dumps(node, ensure_ascii=False, sort_keys=True, separators=(',', ':'))

    def count(node):
        if isinstance(node, dict):
            if set(node) & {'type', 'enum', 'const', 'anyOf'} and len(key(node)) > 13:
                counts[key(node)] += 1
            for value in node.values(): count(value)
        elif isinstance(node, list):
            for value in node: count(value)
    count(schema)
    shared = {value: ('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'[index] if index<52 else 's'+str(index)) for index, value in enumerate(sorted((k for k, n in counts.items() if n > 1 and n*(len(k)-13)>len(k)+25),key=lambda k:(-counts[k],k)))}

    if agency_audit_required:
        def name_records(node, hint='Record'):
            if isinstance(node, dict):
                value = key(node)
                if value in shared and 'properties' in node:
                    name = ''.join(part.capitalize() for part in hint.split('_'))
                    if name not in shared.values(): shared[value] = name
                for field, child in node.get('properties', {}).items(): name_records(child, field)
                if 'items' in node: name_records(node['items'], hint)
                for child in node.get('anyOf', []): name_records(child, hint)
            elif isinstance(node, list):
                for child in node: name_records(child, hint)
        name_records(schema)

    def compact(node, root=False):
        if isinstance(node, dict):
            if not root and key(node) in shared: return {'$ref':'#'+shared[key(node)]}
            return {name:compact(value) for name, value in node.items()}
        if isinstance(node, list): return [compact(value) for value in node]
        return node
    result = compact(schema)
    result['$defs'] = {name:dict(compact(json.loads(value), root=True), **{'$anchor':name}) for value, name in shared.items()}
    # Counting before factoring can leave definitions referenced only once:
    # their original occurrences now live inside another shared definition.
    # Inline those wrappers losslessly rather than paying for an anchor + ref.
    while True:
        refs = Counter()
        def references(node):
            if isinstance(node, dict):
                if '$ref' in node: refs[node['$ref']] += 1
                for child in node.values(): references(child)
            elif isinstance(node, list):
                for child in node: references(child)
        references(result)
        single = {name for name in result['$defs'] if refs['#'+name] == 1}
        if not single: break
        def inline(node):
            if isinstance(node, dict):
                name = node.get('$ref', '').removeprefix('#')
                if set(node) == {'$ref'} and name in single:
                    return inline({k:v for k,v in result['$defs'][name].items() if k != '$anchor'})
                return {k:inline(v) for k,v in node.items()}
            if isinstance(node, list): return [inline(v) for v in node]
            return node
        expanded = inline(result)
        expanded['$defs'] = {k:v for k,v in expanded['$defs'].items() if k not in single}
        result = expanded
    return result


def repair_feedback(diagnostic, payload, before, previous_complete=None):
    """Retry-only context: never infer scene semantics from prose in Python."""
    if isinstance(payload, str):
        try: payload = json.loads(payload)
        except ValueError: pass  # Preserve malformed output verbatim for repair.
    # Full diagnostics remain in game_jobs; the prompt needs only repair evidence.
    rows = diagnostic if isinstance(diagnostic, list) else [diagnostic]
    details = [{key: row[key] for key in ('code', 'path', 'source_ids', 'reason', 'repair_reason', 'action', 'temporal_boundary', 'related_paths') if key in row} for row in rows]
    # Keep the legacy first-error summary, without duplicating its long reason
    # and source lists. The diagnostics array retains every complete record.
    detail = {key:details[0][key] for key in ('code','path') if key in details[0]}
    # Retain topology for referenced endpoints even if relevance omitted them.
    # The context builder removes only copies already in its canonical slice.
    referenced = set()
    def references(value):
        if isinstance(value, dict):
            for child in value.values(): references(child)
        elif isinstance(value, list):
            for child in value: references(child)
        elif isinstance(value, str) and value in before['locations']:
            referenced.add(value)
    references(payload)
    omitted = {}
    if isinstance(previous_complete, str):
        try: previous_complete = json.loads(previous_complete)
        except ValueError: previous_complete = None
    if isinstance(payload, dict) and isinstance(previous_complete, dict):
        omitted = {key:previous_complete[key] for key in ('final_scene', *SECTIONS)
                   if key not in payload and previous_complete.get(key)}
    required = ['final_scene'] + [key for key in SECTIONS if
        (isinstance(payload, dict) and payload.get(key)) or omitted.get(key)]
    return json.dumps(dict(diagnostic=detail, diagnostics=details, original_extraction=payload,
        response_required=required,
        **({'omitted_sections_from_previous_proposal':omitted} if omitted else {}),
        known_locations={lid:{k:v for k,v in before['locations'][lid].items()
                             if k in ('id','name','aliases','parent_id','kind')} for lid in sorted(referenced)},
        canonical_context='Use the supplied immutable current state/camera/locations; original_extraction — предварительный отклонённый ответ, не канон.',
        contract=(
            'narrative-authority-v1: repair INTERPRETATION, not a saved status. original_extraction — предварительный отклонённый ответ, не канон. '
            'Read the unchanged full Narrative against immutable before and current player_input; fix all diagnostics/dependencies together. '
            'Preserve confirmed Events, facts, witnesses, real sources and ALL knowledge acquisitions; repair supported links. '
            'Never remove witnesses while retaining impossible contact, substitute a speaker, invent arrival/consent or suppress confirmed learning. '
            'Recheck both agency directions across prose, including unrecorded replies/gestures/decisions. If Narrative itself violates agency/canon, '
            'return player_agency.status=violated (uncertain if unprovable), using existing reauthor/abandon; do not launder it by editing JSON. '
            'Event/action coverage: actual actor, one action ID, verified action quote, target subset/union. When the request schema permits, omit the duplicate Event quote; never overwrite an explicit conflict. Restore a genuinely performed player address '
            'as a separate Event; retain NPC reply/fact_ids/knowledge_gained. Never relabel the NPC response as player-authored. '
            'Align events/movements/final_scene/character_changes at scene granularity: future_intent/preparation is not departure; '
            'unknown destination stays unknown. future_intent/departure is not completed_arrival, even at a newly registered endpoint. Arrival needs accepted source Event/actor/endpoint/order. '
            'New locations and autonomous background movement remain valid; no automatic player Knowledge. Observed is visibility, not contact proof. '
            'This is the only automatic repair; return ONLY the full RawTurnResult matching JSON Schema. '
            'For compound input, split distinct clauses/targets into separate PlayerActions when appropriate; a shared action uses one full quote inherited by its Events. Do not invent Events. '
            'Always return final_scene, including unchanged fields, and every response_required section. Omitted sections from an earlier proposal are UNACCEPTED context to recheck, not a patch to apply. '
            'diagnostic, diagnostics, original_extraction, omitted_sections_from_previous_proposal, response_required, known_locations, canonical_context and contract are INPUT feedback keys, '
            'NOT output fields. Do not copy this feedback envelope or return a patch. '
            'Never rewrite before/History or the Narrative.'
        )), ensure_ascii=False, separators=(',', ':'))


def prune_schema_definitions(schema):
    """Drop unreachable definitions after optional wire sections were elided."""
    used=set()
    def visit(node):
        if isinstance(node,dict):
            ref=node.get('$ref','').removeprefix('#/$defs/').removeprefix('#')
            if ref and ref not in used:
                used.add(ref);visit(schema.get('$defs',{}).get(ref,{}))
            for value in node.values():visit(value)
        elif isinstance(node,list):
            for value in node:visit(value)
    visit(schema['properties'])
    schema['$defs']={key:value for key,value in schema.get('$defs',{}).items() if key in used}
    return schema
