"""One-way versioned migration. Never called from a v3 turn resolver."""
from copy import deepcopy
from dataclasses import dataclass
from backend.runtime_v3.models import (WorldStateV3, WorldHistoryV3, Character, Location,
    Fact, Knowledge, Relationship, Thread, ScheduledEvent, identity,
    assert_world_state_v3_invariants, fatal)


@dataclass
class MigrationResult:
    snapshot: dict
    history: dict
    report: list


def migrate_v2(original):
    if original.get('schema_version') == 3:
        original = deepcopy(original)
        original['world_state'] = assert_world_state_v3_invariants(original['world_state'])
        for card in original.get('character_cards',[]):
            actor = original['world_state']['characters'].get(card['id'])
            if actor is not None and actor['display_name'] is None: actor['display_name'] = card['name']
        initialize_calendar(original['world_state'])
        return MigrationResult(original, WorldHistoryV3().to_dict(), [])
    # The only legacy normalization boundary. No runtime code imports v2 apply.
    from backend.services.world import normalize
    from backend.services.timeline import current_time
    old = normalize(original)
    world = old.get('world') or {}
    if world.get('version') != 2:
        if isinstance(original.get('scene'),str) and not original.get('world') and not original.get('characters'):
            state=WorldStateV3(camera=dict(mode='observer',situation=original['scene']),characters={}).model_dump()
            history=WorldHistoryV3();history.legacy.append(deepcopy(original))
            return MigrationResult(dict(schema_version=3,world_state=state,character_cards=[],campaign={'incomplete_import':True},memory={},history_head=None),history.to_dict(),[dict(section='migration',reason='неполное древнее сохранение: текст сохранён, требуется подготовка персонажей')])
        fatal('невозможно мигрировать неполное сохранение', 'migration_invalid')
    report, locations = [], {}
    # Explicit #39 imports own stable location IDs. Legacy name-only saves keep
    # their historical deterministic identity mapping, without residence inference.
    declared = old.get('locations', [])
    structured_places = (any(k in world for k in ('residences','roles','organizations')) or
        any(isinstance(loc,dict) and any(k in loc for k in ('parent_id','kind','aliases')) for loc in declared))
    if structured_places:
        for loc in declared:
            record = dict(id=loc['id'],name=loc['name'],description=loc.get('description',loc.get('text','')),
                          **{k:deepcopy(loc[k]) for k in ('parent_id','kind','aliases') if k in loc})
            locations[loc['id']] = Location.model_validate(record).model_dump()


    def location(name):
        if not isinstance(name, str) or not name.strip() or name == 'Не указано':
            return None
        matches = [lid for lid, loc in locations.items() if name == lid or name.strip().casefold() in
                   [n.strip().casefold() for n in [loc['name'],*loc.get('aliases',[])]]]
        if len(matches) > 1: fatal('неоднозначное место при миграции: нужен canonical ID', 'migration_invalid')
        if matches: return matches[0]
        lid = identity('location', name.strip().casefold())
        locations.setdefault(lid, Location(id=lid, name=name.strip()).model_dump())
        return lid

    legacy_locations = old.get('locations', [])
    for item in legacy_locations if isinstance(legacy_locations, list) else []:
        if isinstance(item, str):
            location(item)
        elif isinstance(item, dict):
            lid = item.get('id') if structured_places else location(item.get('name') or item.get('text'))
            if lid:
                locations[lid]['description'] = item.get('description', item.get('text', ''))
    raw_scenes = world.get('scenes', {})
    scenes = {key:value for key,value in raw_scenes.items() if isinstance(value,dict) and isinstance(value.get('participants',[]),list)} if isinstance(raw_scenes,dict) else {}
    if scenes != raw_scenes:
        report.append(dict(section='scenes',reason='повреждённые исторические сцены сохранены только в legacy history'))
    camera_scene = scenes.get(old.get('camera', {}).get('scene_id'), {})
    camera_meta = old.get('scene_meta') or {}
    camera_location = location(camera_scene.get('location') or camera_meta.get('location'))
    actors = {}
    for cid, entry in world.get('characters', {}).items():
        live = {location(s.get('location')) for s in scenes.values()
                if s.get('status') == 'active' and cid in s.get('participants', [])}
        live.discard(None)
        lid = location(entry.get('location'))
        if lid is None and len(live) == 1:
            lid = next(iter(live))
        if lid is None and cid in camera_scene.get('participants', camera_meta.get('present_ids', [])):
            lid = camera_location
        actors[cid] = Character(id=cid, location_id=lid,
            **{key:deepcopy(entry[key]) for key in ('situation','emotion','goals','intentions','obligations') if key in entry}).model_dump()
        actors[cid]['birth_date'] = deepcopy(entry.get('birth_date'))
        for field in ('life_status','life_fact_id','capabilities','developmental_stage','name_history','display_name','parentage_complete_fact_id'):
            if field in entry: actors[cid][field] = deepcopy(entry[field])
        actors[cid]['display_name'] = actors[cid].get('display_name') or next((c['name'] for c in old['characters'] if c['id']==cid), None)
    actor = old.get('controlled_actor_id')
    present = camera_scene.get('participants', camera_meta.get('present_ids', []))
    present = list(dict.fromkeys(cid for cid in present if cid in actors))
    if actor is not None and actor not in actors:
        fatal('неизвестный controlled actor при миграции', 'migration_invalid')
    mode = old.get('camera', {}).get('mode', 'actor' if actor else 'observer')
    mode = 'actor' if mode == 'actor' and actor else 'observer'
    if mode == 'actor' and actor not in present:
        present.append(actor)
        report.append(dict(section='camera', entity=actor, reason='controlled actor восстановлен в камере'))
    for cid in present:
        if actors[cid]['location_id'] != camera_location:
            report.append(dict(section='characters', entity=cid, field='location_id', reason='позиция согласована с текущей камерой'))
        actors[cid]['location_id'] = camera_location
    state = WorldStateV3(camera=dict(location_id=camera_location, present_character_ids=present,
        controlled_actor_id=actor, mode=mode, situation=old.get('scene', '')), characters=actors,
        locations=locations, meta=dict(schema_version=3, turn_id=0, world_time=current_time(old))).model_dump()
    history = WorldHistoryV3()
    # Keep the complete legacy payload, including malformed provenance, for audit.
    history.legacy.append(dict(schema_version=2, world=deepcopy(world)))
    history.events.extend(deepcopy(list(world.get('events', {}).values()) if isinstance(world.get('events',{}),dict) else [world.get('events')]))
    history.turns.extend(deepcopy(list(world.get('scene_records', {}).values()) if isinstance(world.get('scene_records',{}),dict) else [world.get('scene_records')]))
    for fid, f in world.get('facts', {}).items():
        state['facts'][fid] = Fact(id=fid, text=f['text'], visibility='secret' if f.get('secret') else 'public',
            character_ids=[cid for cid in f.get('character_ids', []) if cid in actors]).model_dump()
    for key, k in world.get('knowledge', {}).items():
        if k.get('actor_id') not in actors or k.get('fact_id') not in state['facts']:
            report.append(dict(section='knowledge', entity=key, reason='отсутствует actor или fact', action='drop_record'))
            continue
        current = Knowledge(**{field:k[field] for field in ('actor_id','fact_id','status')}).model_dump()
        state['knowledge'][current['actor_id'] + ':' + current['fact_id']] = current
        acquisition = dict(current, source_event_id=k.get('source_event_id'), migrated=True)
        source = world.get('events', {}).get(k.get('source_event_id'), {})
        acquisition['provenance_complete'] = (k['actor_id'] in source.get('witnesses', []) and
            k['fact_id'] in source.get('fact_ids', []) and source.get('medium') in
            ('observation','conversation','message','testimony','discovery'))
        history.knowledge_acquisitions.append(acquisition)
        if not acquisition['provenance_complete']:
            report.append(dict(section='knowledge', entity=key, reason='неполное историческое происхождение', action='preserve_current'))
    from backend.services.relation_dimensions import RELATION_DIMENSIONS
    for key, r in world.get('relationships', {}).items():
        if r.get('source_id') not in actors or r.get('target_id') not in actors:
            report.append(dict(section='relationships',entity=key,reason='отсутствующий actor; исходная запись сохранена в legacy истории',action='drop_record'))
            continue
        dimensions = {}
        for name, value in r.get('dimensions', {}).items():
            if name in RELATION_DIMENSIONS and type(value) in (int,float) and -100 <= value <= 100:
                dimensions[name] = value
            else:
                report.append(dict(section='relationships', entity=key, field='dimensions.'+name, reason='legacy значение сохранено только в истории'))
        record = Relationship(source_id=r['source_id'], target_id=r['target_id'], dimensions=dimensions, context=r.get('context','')).model_dump()
        state['relationships'][r['source_id']+':'+r['target_id']] = record
    for tid, t in world.get('threads', {}).items():
        fields = {key:deepcopy(t[key]) for key in ('description','character_ids','status','state','relevance') if key in t}
        fields['character_ids']=[cid for cid in fields.get('character_ids',[]) if cid in actors]
        state['threads'][tid] = Thread(id=tid, **fields).model_dump()
    for eid, e in world.get('scheduled_events', {}).items():
        state['scheduled_events'][eid] = ScheduledEvent(id=eid, description=e['description'],
            character_ids=[cid for cid in e.get('participants',[]) if cid in actors], due_minute=e.get('due_minute'), status=e.get('status','pending'),
            condition=e.get('condition',''), type=e.get('type','event'),
            temporal=e.get('temporal'), time_reference_minute=e.get('time_reference_minute',state['meta']['world_time'])).model_dump()
        state['scheduled_events'][eid].update({k:deepcopy(e[k]) for k in ('commitment','end_temporal','depends_on','started_minute','outcome','evidence','source_turn','interrupts') if k in e})
    state['objective_relations'] = deepcopy(world.get('objective_relations',{}))
    state['conditions'] = deepcopy(world.get('conditions',{}))
    for section in ('residences','roles','organizations'):
        state[section] = deepcopy(world.get(section,{}))
    configured = old.get('world_clock', {}).get('calendar')
    if configured:
        from backend.runtime_v3.models import Calendar
        try: state['meta']['calendar'] = Calendar.model_validate(configured).model_dump()
        except (ValueError, TypeError):
            report.append(dict(section='calendar', reason='invalid optional calendar preserved in legacy history; relative time retained'))
            history.legacy.append(dict(calendar=deepcopy(configured)))
    initialize_calendar(state)
    state = assert_world_state_v3_invariants(state)
    # Presentation metadata is deliberately not a second mutable world.
    retained = ('world_summary','summary','title','setting','genre','tone','protagonist_id','world_id','sections','story_notes','campaign')
    cards=deepcopy(old['characters'])
    dynamic_fields={'Сейчас','Чего хочет','Намерения','Обязательства','Место','Время'}
    for card in cards:
        card['fields']={key:value for key,value in card.get('fields',{}).items() if key not in dynamic_fields and not key.startswith('Отношение к ')}
    snapshot = dict(schema_version=3, world_state=state, character_cards=cards,
        campaign={key:deepcopy(old[key]) for key in retained if key in old},
        memory=deepcopy(old.get('memory', {})), history_head=None)
    return MigrationResult(snapshot, history.to_dict(), report)


def initialize_calendar(state, start=None):
    meta = state['meta']
    if not meta.get('calendar'):
        start = meta['world_time'] if start is None else start
        from backend.runtime_v3.models import Calendar
        meta['calendar'] = Calendar(start_minute=start, start_weekday=start // 1440 % 7).model_dump()
    return state
