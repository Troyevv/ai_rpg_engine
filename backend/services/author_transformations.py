"""Leaf-level audit map for the deterministic author compiler.

Paths use local record keys on the source side and canonical IDs on the target
side. List positions are explicit. Metadata and non-executable history retain
separate destinations instead of pretending to be Runtime fields.
"""
from backend.services import world_authoring as a
from backend.runtime_v3.models import identity


def leaves(value, path=''):
    if isinstance(value, dict) and value:
        for key, child in value.items():
            yield from leaves(child, path+'/'+str(key).replace('~','~0').replace('/','~1'))
    elif isinstance(value, list) and value:
        for i, child in enumerate(value):
            yield from leaves(child, path+'/'+str(i))
    else:
        yield path, value


def expand(doc, ids, coarse, snapshot):
    """Every source leaf has a destination or explicit metadata disposition."""
    from backend.services.world_authoring_compiler import CARD_FIELDS
    result=[]
    lookup={r['source']:r for r in coarse}
    aliases=dict(source='source_id', target='target_id', actor='actor_id', owner='owner_id',
        holder='holder_id', character='character_id', location='location_id', parent='parent_id',
        organization='organization_id', participants='character_ids', facts='fact_ids',
        fact='fact_id', event='source_event_id', levels='dimensions', secret='visibility')
    for section in a.Sections.model_fields:
        for index,row in enumerate(getattr(doc,section)):
            rid=ids[section+'/'+row.key];base=section+'/'+row.key
            for suffix,value in leaves(row.model_dump()):
                parts=suffix.strip('/').split('/');field=parts[0]
                entry=dict(lookup[base+'/'+field]);entry['source']=base+suffix
                if field not in row.field_origins and len(parts)>1:
                    nested=getattr(row,field)
                    if isinstance(nested,list) and parts[1].isdigit():
                        child=nested[int(parts[1])]
                        if isinstance(child,a.Record):
                            entry['origin']=child.field_origins.get(parts[2],child.origin) if len(parts)>2 else child.origin
                root=entry['target'];tail='/'.join(parts[1:])
                target=root+'/'+aliases.get(field,field)+(('/'+tail) if tail else '')
                if field in ('origin','field_origins'):
                    target='source_document/'+section+'/'+str(index)+suffix;entry['method']='provenance'
                elif field=='key':
                    target='id_map/'+section+'/'+row.key;entry['method']='stable_identity'
                elif section=='characters':
                    if field in CARD_FIELDS:
                        target=f'character_cards/{index}/fields/{CARD_FIELDS[field]}'
                        if field=='appearance':target=root+'/appearance/legacy_text'
                        elif field in ('personality','communication','habits','strengths','weaknesses','fears'):
                            target=root+'/personality/items/'+('traits' if field=='personality' else field)+'/text'
                    elif field=='name':target=root+'/display_name'
                    elif field=='aliases':target=f'character_cards/{index}/aliases'+(('/'+tail) if tail else '')
                    elif field=='name_changes':
                        records=snapshot['initial_history']['legacy']
                        start=next((i for i,r in enumerate(records) if r.get('kind')=='identity_change' and r.get('actor_id')==rid),None)
                        target='initial_history/legacy' if start is None or not tail else 'initial_history/legacy/'+str(start+int(parts[1]))+('/'+ '/'.join(parts[2:]) if len(parts)>2 else '')
                        entry['method']='historical_precision_preserved'
                    elif field in ('goals','intentions','obligations') and len(parts)>2:
                        if parts[2]=='key':target=root+'/'+field+'/'+parts[1]+'/id';entry['method']='stable_identity'
                        elif parts[2] in ('origin','field_origins'):target='source_document/'+section+'/'+str(index)+suffix;entry['method']='provenance'
                elif section=='source_notes':
                    if field in ('capability','text'):target=root+'/text';entry['method']='descriptive_only'
                    elif field=='requires_execution':target='source_document/'+section+'/'+str(index)+suffix;entry['method']='execution_gate'
                elif section=='organizations':
                    if field=='description':target=root+'/context'
                    elif field=='locations':target=root+'/location_ids'+(('/'+tail) if tail else '')
                    elif field=='parent':
                        target=('world_state/facts/'+identity('organization_parent',rid,ids['organizations/'+value])+'/claim/value') if value else root
                        entry['method']='structural_fact' if value else 'absent'
                elif section=='objective_relations' and field=='time_description':target=root+'/evidence'
                elif section=='events':
                    root='initial_history/events/'+str(index)
                    target=root+'/'+{'key':'id','facts':'fact_ids'}.get(field,field)+(('/'+tail) if tail else '')
                    if field in ('origin','field_origins'):target='source_document/'+section+'/'+str(index)+suffix
                elif section=='knowledge':
                    if not row.current:
                        candidates=[i for i,r in enumerate(snapshot['initial_history']['legacy']) if r.get('kind')=='prior_knowledge' and r['actor_id']==ids['characters/'+row.actor] and r['fact_id']==ids['facts/'+row.fact]]
                        occurrence=sum(not r.current and r.actor==row.actor and r.fact==row.fact for r in doc.knowledge[:index])
                        k=candidates[occurrence]
                        root='initial_history/legacy/'+str(k)
                    target=root+'/'+aliases.get(field,field)+(('/'+tail) if tail else '')
                    if field=='time_description':target=root+'/evidence';entry['method']='append_evidence'
                    if field in ('current','key','origin','field_origins'):target='source_document/'+section+'/'+str(index)+suffix;entry['method']='routing_or_provenance'
                elif section=='possessions' and field=='description':
                    target='world_state/facts/'+identity('possession_description',rid)+'/text' if value else root
                    entry['method']='linked_descriptive_fact' if value else 'absent'
                elif section=='pregnancies':
                    aliases_preg=dict(gestational_actor='gestational_actor_id',parents='parent_ids',
                        conception_earliest_date='earliest_minute',conception_latest_date='latest_minute')
                    if field in aliases_preg:
                        target=root+'/'+aliases_preg[field]+(('/'+tail) if tail else '')
                        entry['method']='calendar_interval' if field.startswith('conception') else 'reference'
                    elif field=='impregnating_actor':target='world_state/reproductive_events/'+identity('author_conception',rid)+'/impregnating_actor_id'
                    elif field in ('fact','count_fact'):target=root+'/'+field+'_id';entry['method']='fact_reference_or_generated_default'
                    elif field=='description':
                        event_index=next(i for i,r in enumerate(snapshot['initial_history']['events']) if r['id']==identity('author_conception',rid))
                        target='initial_history/events/'+str(event_index)+'/text'
                    elif field=='due':
                        target='world_state/scheduled_events/'+rid+('/evidence' if tail=='description' else '/due_minute')
                        entry['method']='calendar_explicit_boundary'
                    elif field=='children' and len(parts)>2:
                        if parts[2]=='sex_fact':target=root+'/sex_fact_ids/'+identity('author_unborn',rid,row.children[int(parts[1])].key);entry['method']='fact_reference_or_generated_default'
                        elif parts[2]=='key':target=root+'/children/'+parts[1]+'/id';entry['method']='stable_identity'
                        elif parts[2] in ('origin','field_origins'):target='source_document/'+section+'/'+str(index)+suffix;entry['method']='provenance'
                elif section=='commitments' and field=='time':
                    if len(parts)>1:
                        target=root+('/evidence' if parts[1]=='description' else '/temporal/'+{'clock':'time','period':'day_period'}.get(parts[1],parts[1]))
                    entry['method']='calendar_precision_preserved'
                if section=='feelings' and field=='levels' and value=='unknown':entry['method']='unknown_omitted'
                entry['target']=target
                result.append(entry)
    for section in ('world','opening'):
        for suffix,value in leaves(getattr(doc,section).model_dump()):
            bits=suffix.strip('/').split('/');field=bits[0]
            target='campaign/campaign'+suffix
            if section=='opening':
                target='world_state/camera/'+dict(controlled='controlled_actor_id',pov='pov_actor_id',location='location_id',present='present_character_ids').get(field,field)
                if len(bits)>1:target+='/'+'/'.join(bits[1:])
                if field=='protagonist':target='world_state/meta/current_protagonist_id'
                elif field=='calendar':target='world_state/meta/calendar/profile'+suffix[len('/calendar'):]
                elif field=='time':
                    target={'date':'world_state/meta/calendar/start_date','weekday':'world_state/meta/calendar/start_weekday','clock':'world_state/meta/world_time'}.get(bits[1] if len(bits)>1 else '', 'source_document/opening'+suffix)
            result.append(dict(source=section+suffix,target=target,method='copy' if section=='world' else 'calendar_or_reference',origin='unknown'))
    result.append(dict(source='version',target='source_document/version',method='contract',origin='unknown'))
    for suffix,value in leaves(doc.uncertainties):
        result.append(dict(source='uncertainties'+suffix,target='diagnostics'+suffix,method='semantic_warning',origin='unknown'))
    return result
