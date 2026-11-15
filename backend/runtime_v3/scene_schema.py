"""Structural projection of existing domain contracts for Extraction/6 only.

No state/authority checks live here. Ordinary, background, LTA and targeted repair
all use the resulting schema; recorded v1–v5 projections remain unchanged.
"""
from copy import deepcopy
from backend.runtime_v3.models import Fact, SignificantPossession

NONBLANK = dict(type='string', minLength=1, pattern=r'\S')


def project_structure(schema, *, movement_type='MovementStep', interaction_type='InteractionStep'):
    props, defs = schema['properties'], schema['$defs']
    # Reuse canonical fields/types (including Claim bounds and secrecy fields).
    # Identity/evidence are compiler-owned for an inline perception Fact.
    fact = Fact.model_json_schema()
    defs.update(fact.pop('$defs', {}))
    fact['properties'].pop('origin_remote_event_id')
    fact['properties']['evidence'] = dict(type='string')
    # One shared closed field set; required identity differs for a top-level
    # Fact and an inline assertion whose identity is compiler-owned.
    fact.pop('required', None)
    fact['properties']['id'] = dict(type=['string', 'null'])
    defs['FactFields'] = fact
    props['facts']['items'] = dict(allOf=[{'$ref': '#/$defs/FactFields'}],
        required=['id', 'text'], properties=dict(id=dict(type='string')))
    defs['PerceivedFact'] = dict(allOf=[{'$ref': '#/$defs/FactFields'}],
        required=['text'], properties=dict(id=dict(type=['string','null'],minLength=1), text=deepcopy(NONBLANK)))
    claim = defs['PerceivedClaim']
    claim['properties']['fact'] = {'anyOf': [{'$ref': '#/$defs/PerceivedFact'}, {'type': 'null'}]}
    claim['properties']['fact_id'] = dict(type=['string', 'null'], minLength=1)
    claim['properties']['perceived_by']['uniqueItems'] = True
    claim['properties']['expected_revisions']['additionalProperties']['minimum'] = 0
    claim['oneOf'] = [
        dict(required=['fact'], properties=dict(fact=dict(type='object'), fact_id=dict(type='null'))),
        dict(required=['fact_id'], properties=dict(fact_id=dict(type='string'), fact=dict(type='null'))),
    ]
    claim['allOf'] = [dict(
        **{'if': dict(properties=dict(assertion=dict(const='rumor')), required=['assertion'])},
        then=dict(properties=dict(status=dict(const='suspected'))))]

    chronology = props['chronology_claims']['items']
    chronology.update({
        'if': dict(properties=dict(kind=dict(const='event_elapsed'))),
        'then': dict(required=['event_id', 'elapsed_days'], properties=dict(
            event_id=deepcopy(NONBLANK), elapsed_days=dict(type='integer', minimum=0),
            date=dict(type='null'), weekday=dict(type='null'))),
        'else': dict(properties=dict(event_id=dict(type='null'), elapsed_days=dict(type='null')),
            anyOf=[dict(required=[key], properties={key: deepcopy(NONBLANK)}) for key in ('date', 'weekday')]),
    })
    if movement_type in ('GroupMovementStep', 'MovementV8'):
        defs[movement_type]['properties']['actor_ids']['uniqueItems'] = True
    defs[movement_type]['allOf'] = [
        dict(**{'if': dict(properties=dict(assertion=dict(enum=['departure', 'local_exit'])))},
             then=dict(properties=dict(endpoint=dict(type='null')))),
        dict(**{'if': dict(properties=dict(assertion=dict(const='completed_arrival')))},
             then=dict(required=['endpoint'], properties=dict(endpoint=deepcopy(NONBLANK)))),
    ]
    defs[interaction_type].update({
        'if': dict(properties=dict(outcome=dict(enum=['deferred', 'not_performed']))),
        'then': dict(properties=dict(target_ids=dict(maxItems=0))),
    })

    # State-independent shapes of declared domain consequences. Optional
    # narrative annotations in OPTIONAL_SECTIONS keep their isolation policy;
    # state-dependent acceptance remains with the existing domain owners.
    if 'naming_decisions' in props:
        naming = props['naming_decisions']['items']
        naming.update({
            'if': dict(properties=dict(status=dict(enum=['proposed', 'agreed']))),
            'then': dict(properties=dict(components=dict(maxProperties=8,
                propertyNames=deepcopy(NONBLANK),
                additionalProperties=dict(NONBLANK, maxLength=200))),
                anyOf=[dict(required=['components'], properties=dict(components=dict(minProperties=1))),
                    dict(required=['delegated_to'], properties=dict(status=dict(const='proposed'),
                        delegated_to=deepcopy(NONBLANK)))]),
        })
    possession = props['possession_deltas']['items']
    possession['properties']['updates']['minProperties'] = 1
    possession['properties']['updates']['properties'] = {
        'status': SignificantPossession.model_json_schema()['properties']['status']}
    possession['allOf'] = [dict(
        **{'if': dict(properties=dict(operation=dict(const='relocate')))},
        then=dict(properties=dict(updates=dict(required=['location_id'], propertyNames=dict(enum=['location_id'])))))]
    possession.update({
        'if': dict(properties=dict(operation=dict(const='introduce'))),
        'then': dict(required=['name', 'kind'], properties={key: dict(type='string') for key in ('name', 'kind')}),
        'else': dict(properties={key: dict(type='null') for key in ('name', 'kind')}),
    })
    from backend.runtime_v3.appearance import KINDS
    appearance = props['appearance_deltas']['items']
    appearance['allOf'] = [dict(
        **{'if': dict(properties=dict(category=dict(const=category)))},
        then=dict(properties=dict(kind=dict(enum=sorted(kinds))))) for category, kinds in KINDS.items()]
    appearance['allOf'].append(dict(
        **{'if': dict(properties=dict(operation=dict(const='remove')))},
        then=dict(properties=dict(text=dict(const='')))))
    appearance['allOf'].append(dict(
        **{'if': dict(properties=dict(operation=dict(enum=['establish','update']), category={'not': {'const': 'condition'}}))},
        then=dict(required=['text'], properties=dict(text=deepcopy(NONBLANK)))))
    appearance['allOf'].append(dict(
        **{'if': dict(properties=dict(category=dict(const='condition')))},
        then=dict(required=['condition_id'], properties=dict(condition_id=deepcopy(NONBLANK))),
        **{'else': dict(properties=dict(condition_id=dict(type='null')))}))
