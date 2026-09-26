"""Small intra-turn location timeline, separate from the final camera snapshot."""
from backend.services.world_delta_errors import StructuralDeltaError, SecondaryDeltaError
from backend.services.timeline import current_time

TEMPORAL_CONTRACT = '''scene — КОНЕЧНОЕ состояние камеры, не состав участников всего хода. Event.minute — абсолютная минута события внутри [время before, время after], order — порядок внутри минуты (по умолчанию 0). Event.location — место события; можно опустить, если оно однозначно по участникам. При одинаковых minute/order события проверяются ДО transitions. Для иного порядка укажи различные order. transitions: actor_id, minute, order, to_location, evidence. Создавай их только для входа/выхода/смены места, не для жестов. Исходное место берёт Runtime из текущей позиции. from_location — необязательная подсказка для неизвестного места/появления NPC; обычно ОПУСКАЙ, не копируй из памяти. Участники и свидетели Event должны находиться в месте события В МОМЕНТ события. Кто пришёл позже или ушёл раньше — не свидетель. characters.location — конечное место конкретного персонажа: вне final present_ids оно может отличаться от scene.location. Ушедший сохраняет полученное ранее Knowledge. Любое изменение известного места требует transition; не подменяй его одним characters.location. Если chronology содержит transitions, явно указывай minute событий. Новый значимый NPC тоже входит через transition. Не создавай события между людьми, которые не пересекались. Старый prompt о свидетелях только final scene.present_ids заменяется этим temporal контрактом.'''


def redundant_origin(before, actor_id, origin, destination, hint, evidence, narrative, user_text):
    """Conservative direct-movement grammar, not semantic location aliasing.

    Correct only a named actor's single explicit Russian movement clause. A
    mentioned asserted origin, compound route, unknown grammar or ambiguous
    quote stays structural. Event-time/final checks still run after correction.
    """
    import re
    from state_updates import normalized_evidence
    def forms(label):
        label=normalized_evidence(label)
        variants={label}
        # Only simple one-word location labels; no stemming, synonyms or fuzzy
        # matching. Multiword labels require their literal canonical spelling.
        if re.fullmatch('[а-яё]+',label):
            if label.endswith('а'):variants.add(label[:-1]+('и' if label[-2:-1] in 'гкхжчшщ' else 'ы'))
            elif label.endswith('я'):variants.add(label[:-1]+'и')
            elif label[-1] not in 'аеёиоуыэюяьй':variants.add(label+'а')
        return '|'.join(re.escape(v) for v in sorted(variants,key=len,reverse=True))
    sources=normalized_evidence(narrative)+' '+normalized_evidence(user_text)
    if re.search(r'(?<!\w)(?:'+forms(hint)+r')(?!\w)',sources):return False
    character=next((c for c in before['characters'] if c['id']==actor_id),None)
    if not character:return False
    name=re.escape(normalized_evidence(character['name']))
    # Full sentence: no intervening route or another actor's departure can
    # accidentally prove this movement. Quotes must already match current turn.
    pattern=(r'(?:'+name+r') (?:выходит|вышел|вышла|переходит|перешёл|перешла) из (?:'
             +forms(origin)+r') в (?:'+forms(destination)+r')[.!]?')
    return any(re.fullmatch(pattern,clause.strip()) for clause in re.split(r'(?<=[.!?])\s+',normalized_evidence(evidence)))


def validate_timeline(before, after, delta, narrative, user_text, since=None):
    from state_updates import normalized_evidence
    world=before['world'];actors=world['characters']
    start=current_time(before) if since is None else since
    end=current_time(after)
    initial=world['scenes'][before['camera']['scene_id']]
    final=after['world']['scenes'][after['camera']['scene_id']]
    # Before record_scene, scene_meta is authoritative for the final camera.
    final_meta=after.get('scene_meta')
    final_location=final_meta['location'] if final_meta else final['location']
    final_present=set(final_meta['present_ids'] if final_meta else final['participants'])
    positions={cid:c.get('location') for cid,c in actors.items()}
    initial_present=set(initial['participants'])
    def fail(message,code,section=None,index=None,field=None,entity=None):
        path={k:v for k,v in dict(section=section,index=index,field=field,entity=entity).items() if v is not None}
        raise StructuralDeltaError('World Delta: '+message,code,**path)
    def refs(ids,section,index):
        if not set(ids)<=set(actors):fail('неизвестный персонаж','unknown_character',section,index)
    # Legacy imported worlds may have no initial spatial information at all.
    # Bootstrap a stationary initial scene only; never combine known snapshots.
    bootstrap=(initial.get('location') in (None,'','Не указано') and all(positions[cid] is None for cid in initial_present))
    if bootstrap and not delta['transitions']:
        for cid in final_present:
            if positions.get(cid) not in (None,'',final_location):
                fail('начальная сцена противоречит известному месту','character_location_inconsistent',entity=cid)
            positions[cid]=final_location
        initial_present=set(final_present)
    for cid in initial_present:
        if positions[cid] is None:positions[cid]=initial.get('location')
    involved=set(initial_present)
    actor=before.get('controlled_actor_id')
    # Observed route: initial/final camera locations plus explicit POV movements.
    observed={initial.get('location'),final_location}
    observed.update(t['to_location'] for t in delta['transitions'] if t['actor_id']==actor)
    sources=[normalized_evidence(narrative),normalized_evidence(user_text)]
    operations=[];movement_keys=set();warnings=[]
    for i,t in enumerate(delta['transitions']):
        refs([t['actor_id']],'transitions',i)
        key=(t['minute'],t['order'],t['actor_id'])
        if key in movement_keys:fail('неоднозначный порядок перемещений','temporal_order_invalid','transitions',i)
        movement_keys.add(key)
        if not start<=t['minute']<=end:fail('перемещение вне интервала хода','temporal_order_invalid','transitions',i)
        if not any(normalized_evidence(t['evidence']) in s for s in sources):
            raise SecondaryDeltaError('transitions',i,'Нет подтверждённой цитаты текущего хода',entity=t['actor_id'],cause_field='evidence',code='evidence_unsupported')
        operations.append((t['minute'],t['order'],1,i,t))
    for i,e in enumerate(delta['events']):
        refs(e['participants']+e['witnesses'],'events',i)
        if delta['transitions'] and 'minute' not in e:
            fail('при перемещениях у события нужна minute','temporal_order_invalid','events',i,'minute',e['id'])
        minute=e.get('minute',end)
        if not start<=minute<=end:fail('событие вне подтверждаемого интервала сцены','invalid_time','events',i,'minute',e['id'])
        operations.append((minute,e['order'],0,i,e))
    snapshots={}
    for minute,order,kind,index,item in sorted(operations,key=lambda v:v[:4]):
        if kind:
            cid=item['actor_id'];source=positions[cid];destination=item['to_location']
            hint=item.get('from_location')
            if source==destination:
                fail('перемещение не меняет место','transition_location_invalid','transitions',index,'to_location',cid)
            if source is not None and hint is not None and hint!=source:
                if not redundant_origin(before,cid,source,destination,hint,item['evidence'],narrative,user_text):
                    fail('исходное место перемещения не совпадает с текущим','transition_location_invalid','transitions',index,'from_location',cid)
                warnings.append(dict(type='sanitized_delta',code='transition_from_location_corrected',section='transitions',
                    index=index,field='from_location',entity=cid,reason='Использовано каноническое исходное место Runtime.',
                    message='Избыточная подсказка from_location исправлена.',canonical_origin=source,action='correct_field'))
            # Unknown origins stay unknown. A sourced arrival establishes only
            # the destination; a hint never rewrites earlier event membership.
            if source not in observed and destination not in observed and cid not in involved:
                fail('перемещение не связано с наблюдаемым ходом','transition_invalid','transitions',index,entity=cid)
            positions[cid]=destination;involved.add(cid)
        else:
            ids=item['participants']+item['witnesses']
            locations={positions[cid] for cid in (item['participants'] or item['witnesses'])}
            location=item.get('location')
            if location is None:
                if len(locations)==1:location=next(iter(locations))
                elif not ids:location=initial.get('location') or final_location
            if not location or location not in observed:
                fail('место события не подтверждено наблюдаемым ходом','event_participant_not_present','events',index,entity=item['id'])
            if any(positions[cid]!=location for cid in item['participants']):
                fail('участник отсутствовал в момент события','event_participant_not_present','events',index,'participants',item['id'])
            if any(positions[cid]!=location for cid in item['witnesses']):
                fail('свидетель отсутствовал в момент события','event_witness_not_present','events',index,'witnesses',item['id'])
            # A known location alone does not authorize remote edits: the event
            # must have an exact current-turn source before it grants involvement.
            if any(normalized_evidence(item['evidence']) in s for s in sources):
                involved.update(ids)
            snapshots[item['id']]={'minute':minute,'order':order,'location':location,
                'participants':sorted(cid for cid,pos in positions.items() if pos==location)}
    for cid in final_present:
        refs([cid],'scene',None)
        if positions[cid]!=final_location:
            fail('конечное место участника не совпадает со сценой','character_location_inconsistent','scene',field='present_ids',entity=cid)
    for i,c in enumerate(delta['characters']):
        refs([c['id']],'characters',i)
        if c['id'] not in involved and c['id'] not in final_present:
            fail('персонаж не участвовал в текущем ходе','character_not_involved','characters',i,entity=c['id'])
        if 'location' in c and c['location']!=positions[c['id']]:
            fail('конечное место персонажа противоречит хронологии','character_location_inconsistent','characters',i,'location',c['id'])
    return {'positions':positions,'involved':involved|final_present,'events':snapshots,'warnings':warnings}


def apply_locations(state, temporal, sequence):
    """Publish validated final positions to live scenes; event snapshots stay immutable."""
    from backend.services.world import identity
    from backend.services.timeline import current_time
    world=state['world'];now=current_time(state)
    final=world['scenes'][state['camera']['scene_id']]
    for cid in sorted(temporal['involved']):
        location=temporal['positions'][cid]
        if location is None:continue
        point=world['characters'][cid]
        if cid in final['participants']:
            scene=final
        else:
            scene=next((s for s in world['scenes'].values() if not s.get('historical') and s['id']!=final['id'] and s['location']==location and cid in s['participants']),None)
            if scene is None:
                sid=identity('scene','departed',sequence,location)
                scene=world['scenes'].setdefault(sid,dict(id=sid,participants=[],location=location,start_minute=now,end_minute=now,text=point.get('situation',''),status='active',event_ids=[]))
            if cid not in scene['participants']:scene['participants'].append(cid)
        for other in world['scenes'].values():
            if not other.get('historical') and other['id']!=scene['id'] and cid in other['participants']:
                other['participants'].remove(cid)
                if not other['participants']:other['status']='ended'
        scene['status']='active';scene['end_minute']=now
        point.update(location=location,scene_id=scene['id'],minute=now)
