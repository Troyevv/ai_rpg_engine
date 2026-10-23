"""Request-local constraints derived from accepted IDs, not new world schemas."""
from copy import deepcopy

HINTS = {
    'setting': '''Plan the complete roster of useful locations and organizations as well as
characters. Include playable rooms/workplaces and an opening location, not only a
city. The places stage can describe ONLY entities in this roster; it cannot add
new places or organizations. Include explicitly described subsidiaries even when
the author has not named them; invent suitable names without merging distinct
businesses. Use stable planning keys, existing_id for supplied
entities, and null existing_id for your creative additions.''',
    'places': '''Describe exactly the registered locations and organizations. Dictionary
keys and each record's id must equal registry IDs, not names or planning keys.
Do not add new entities. parent_id and parent_organizations use registered IDs.
Location uses description; Organization stores descriptive prose in context, not description.''',
    'ties': '''objective_relations and relationships connect only Character IDs. An employer
or organization is NOT a coworker endpoint: occupations and organizational duties
belong to the later roles stage. A symmetric objective tie (spouse, coworker,
close_friend etc.) has ONE record per pair, not both directions. Parent/adoptive
parent/guardian remain directed. Emotional relationship dictionary keys are
source_id + ':' + target_id; numeric dimensions use -100..100, NOT a 0..1
scale. Only trust, affection, attraction, irritation, fear, jealousy, respect; other
descriptions belong to context. Do not generate the controlled actor's feelings.
When assigned_pairs is present, output ONLY those unordered pairs: each may have
both directed emotional records, and any established objective phases. Parent and
adoptive_parent orientation must remain parent -> child, regardless of pair order.
An assigned pair is permission to consider a tie, NOT evidence it exists: leave
unrelated pairs absent. Preserve explicit family circumstances and chronology.
Do not infer Knowledge, consent or reciprocal feelings. Use concise context, omit
optional null/default fields and do not repeat biographies or source prose.
Never output a complete all-to-all graph or fill all dimensions just for coverage.''',
    'background': '''Preserve the precision of source chronology: "in childhood" does not
mean "in infancy" and "yesterday" does not imply an invented date or age.
Use accepted places/organizations and their business areas; do not reinvent them.
Separate facts with different knowledge holders. Adoption truth, the occurrence
of a private disclosure yesterday, and a parent's private marriage plan are distinct
facts, not one compound secret. A public biography must not contain private motives
or information whose holders are restricted. Do not add consent or future events.''',
    'knowledge': '''Knowledge dictionary keys are actor_id + ':' + fact_id. Use only accepted
Fact IDs and registry Character IDs. Never infer holders from characters mentioned
in a fact. Knowing an adoption truth does not imply knowing that someone else was
told yesterday. Kinship, marriage or shared residence do not transmit knowledge.
Apply source holder restrictions separately to each fact; unknown stays unknown.
Keep source_event_id null unless it names accepted initial History.''',
    'opening': '''world_time is absolute world minutes: its remainder modulo 1440 MUST equal
the opening clock (09:00 = 540). Calendar.start_minute anchors a day, not an offset
added to world_time. Gregorian profile.month_lengths must be empty/omitted; Python
calendar owns leap years. No invented exact date when the author only gives weekday.
Use scheduled_events only for actual outstanding commitments/circumstances, not a
script of future meetings or a duplicate of the current opening. A temporal value
uses exactly one date/weekday/day_offset and either time OR day_period, never both.
Camera presence must agree with accepted character location_id; do not move people
from accepted places to manufacture a scene.''',
    'characters': '''Generate ONLY assigned_ids, in both characters and cards. The remaining
registry is read-only reference context, not a request to regenerate those actors.
Use exact assigned IDs/names. location_id is null or an accepted locations key.
Differentiate each NPC's personal motives, voice, habits and grounded biography;
put biography in card fields. Use canonical personality.items for traits/voice/habits
and canonical NPC goals for motives. Cards use the supplied Russian field labels.
Cards are public presentation: never put secrets there; lore owns private facts and
explicit Knowledge holders. For registry tier protagonist, goals, intentions and
obligations stay empty unless explicitly supplied by the user. Moving or starting
a job is not permission to invent a goal to fit in, succeed, make friends or find
romance. Do not assign player decisions or feelings, including in card prose.
Keep source chronology at its stated precision, without inventing ages or dates.''',
}


def request_schema(stage, captured, context):
    schema=deepcopy(captured)
    registry={r['id']:r for r in context.get('registry',[])}
    fields={}
    if stage=='characters':
        from backend.services.world import CARD_FIELDS
        schema['$defs']['CharacterCard']['properties']['fields']['propertyNames']={'enum':list(CARD_FIELDS)}
        fields={k:context['assigned_ids'] for k in ('characters','cards')}
        schema['$defs']['Character']['properties']['location_id']={'enum':[None,*context['locations']]}
    elif stage=='places':
        fields={k:[eid for eid,r in registry.items() if r['kind']==kind]
                for k,kind in (('locations','location'),('organizations','organization'))}
        schema['$defs']['Location']['properties']['parent_id']={'enum':[None,*fields['locations']]}
    if stage == 'ties':
        actors=[eid for eid,r in registry.items() if r['kind']=='character']
        from backend.services.relation_dimensions import RELATION_DIMENSIONS
        schema['$defs']['Relationship']['properties']['dimensions']={
            'type':'object','additionalProperties':False,
            'properties':{key:{'type':'number','minimum':-100,'maximum':100} for key in RELATION_DIMENSIONS}}
        for name in ('ObjectiveRelation','Relationship'):
            for field in ('source_id','target_id'):
                schema['$defs'][name]['properties'][field]={'type':'string','enum':actors}
        if context.get('assigned_pairs'):
            schema['properties']['relationships']['maxProperties']=2*len(context['assigned_pairs'])
            for name in ('ObjectiveRelation','Relationship'):
                schema['$defs'][name]['anyOf'] = [
                    {'properties':{'source_id':{'const':a},'target_id':{'const':b}}}
                    for pair in context['assigned_pairs'] for a,b in (pair, pair[::-1])]
    if stage in ('background','lore'):

        from backend.runtime_v3.models import WorldHistoryV3
        schema['properties']['initial_history']['propertyNames']={'enum':list(WorldHistoryV3.__dataclass_fields__)}
    if stage=='opening':
        schema['$defs']['CalendarProfile']['allOf']=[{
            'if':{'properties':{'system':{'const':'gregorian'}}},
            'then':{'properties':{'month_lengths':{'maxItems':0}}}}]
        temporal=schema['$defs']['TemporalValue']
        temporal['oneOf']=[{'required':[basis],'properties':{
            key:({'type':'string' if key=='date' else 'integer'} if key==basis else {'type':'null'})
            for key in ('date','weekday','day_offset')}} for basis in ('date','weekday','day_offset')]
        temporal['allOf']=[{'if':{'required':['time'],'properties':{'time':{'type':'string'}}},
                           'then':{'properties':{'day_period':{'type':'null'}}}}]
    for field,ids in fields.items():
        item=schema['properties'][field]['additionalProperties']
        schema['properties'][field]={'type':'object','additionalProperties':False,
            'required':ids,'properties':{eid:{'allOf':[deepcopy(item),{'properties':{
                'id':{'const':eid},('display_name' if field=='characters' else 'name'):{'const':registry[eid]['name']}}}]}
                for eid in ids}}
    return schema
