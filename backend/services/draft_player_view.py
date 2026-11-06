"""Read-only reader view of an *authored draft*. This is not Runtime Knowledge.

Ordinary dossiers and world records are readable; spoiler-bearing records are
gated before serialization. Never ship director prose, history or raw evidence
and try to hide it with CSS. References, not guesses about Russian prose, decide.
"""
from copy import deepcopy

from backend.runtime_v3.birth_identity import is_game_birth, birth_sex_disclosed
from backend.runtime_v3.personality import CARD_FIELDS as TRAIT_LABELS
from backend.services.world import CARD_FIELDS, KINDS

BINDINGS = 'card_field_facts'
DYNAMIC = {'Сейчас','Чего хочет','Намерения','Обязательства','Место','Время'}
PRIVATE_FIELDS = {'Секрет','Скрытые мотивы','Тайны','Тайна'}
RESERVED_FIELDS = PRIVATE_FIELDS | DYNAMIC
SOCIAL = {
    'roles': ('actor_id','title','kind','organization_id','field'),
    'residences': ('actor_id','location_id'),
    'organizations': ('name','kind','location_ids','aliases'),
    'objective_relations': ('kind','source_id','target_id'),
    'conditions': ('actor_id','description','duration','effects'),
    'possessions': ('name','kind','owner_id','holder_id','location_id'),
    'contacts': ('character_id','owner_id','kind','label','address','available','blocked'),
    'pregnancies': ('gestational_actor_id','parent_ids','status','due_minute','children'),
    'reproductive_events': ('participants','gestational_actor_id','impregnating_actor_id','exact_minute','closed'),
    'naming_decisions': ('child_id','display_name','established','decision_actor_ids','status'),
}


def pick(row, *keys):
    return {k:deepcopy(row[k]) for k in keys if k in row}


def binding_errors(state):
    """Optional authoring-only map. Deleting a referenced fact cannot unmask a field."""
    mapping=state.get(BINDINGS,{})
    if not isinstance(mapping,dict):return ['Привязки полей к фактам: ожидался объект.']
    cards={c['id']:c['fields'] for c in state['characters']}
    facts=state['world']['facts']
    return [f'Некорректная привязка полей карточки {cid} к фактам.'
            for cid,fields in mapping.items() if cid not in cards or not isinstance(fields,dict) or
            any(key not in cards[cid] or key in RESERVED_FIELDS or not isinstance(refs,list) or
                any(not isinstance(fid,str) or fid not in facts for fid in refs) or len(set(refs))!=len(refs)
                for key,refs in fields.items())]


def set_binding(state, cid, field, visibility):
    if field in RESERVED_FIELDS:
        raise ValueError('Это поле не поддерживает настройку видимости.')
    if visibility=='default':
        fields=state.get(BINDINGS,{}).get(cid,{})
        fields.pop(field,None)
        if not fields:state.get(BINDINGS,{}).pop(cid,None)
        if not state.get(BINDINGS):state.pop(BINDINGS,None)
    else:
        state.setdefault(BINDINGS,{}).setdefault(cid,{})[field]=deepcopy(visibility)
    errors=binding_errors(state)
    if errors:raise ValueError(errors[0])


def player_view(state):
    world=state['world']; actor=state.get('controlled_actor_id')
    # Legacy drafts may use arbitrary keys for successive states of the same
    # belief. The V2 handoff keeps the last entry for an (actor, fact) pair.
    current={(k.get('actor_id'),k.get('fact_id')):(key,k) for key,k in world['knowledge'].items()}
    known={fid for (cid,fid),(_,belief) in current.items() if cid==actor and belief.get('status')=='known'}
    def access(row):
        return not row.get('director_only') and ('visible_to_ids' not in row or actor in row['visible_to_ids'])
    scene=world['scenes'].get(state.get('camera',{}).get('scene_id'),{})
    before=world['characters']
    def known_identity(c):
        row=before.get(c['id'],{})
        return c['id'] in before and (not is_game_birth(world,c['id']) or c['id']==actor or row.get('life_fact_id') in known)
    cards={c['id']:c for c in state['characters'] if known_identity(c) and not c.get('director_only') and
           (not c.get('hidden') or c['id']==actor or actor in c.get('visible_to_ids',[]) or c['id'] in scene.get('participants',[]))}
    people=set(cards)
    def visible_people(row):
        ids={row[k] for k in ('actor_id','gestational_actor_id','impregnating_actor_id','child_id','owner_id','holder_id','source_id','target_id','character_id') if row.get(k)}
        for k in ('participants','witnesses','character_ids','secret_subject_ids','secret_biography_ids','secret_keeper_ids','parent_ids','decision_actor_ids'):
            ids.update(row.get(k,[]))
        return ids<=people
    facts={fid for fid,f in world['facts'].items() if access(f) and visible_people(f)
           and (not(f.get('secret') or f.get('story_secret') or f.get('visibility')=='secret') or fid in known)}
    unknown=[f for fid,f in world['facts'].items() if fid not in facts]
    reserved_people={cid for f in unknown for k in ('character_ids','secret_subject_ids','secret_keeper_ids','secret_biography_ids') for cid in f.get(k,[])}
    reserved_people.update(f['owner_id'] for f in unknown if f.get('owner_id'))
    hidden_bio={cid for f in unknown for cid in f.get('secret_biography_ids',[])}
    def fact_safe(row):
        ids=set(row.get('fact_ids',[])) | {row[k] for k in ('fact_id','closure_fact_id','count_fact_id') if row.get(k)}
        ids.update(row.get('field_facts',{}).values());ids.update(row.get('sex_fact_ids',{}).values())
        return ids<=facts
    def allowed(row):
        return (access(row) and visible_people(row) and fact_safe(row) and
                (not (row.get('secret') or row.get('hidden') or row.get('visibility')=='secret') or actor in row.get('visible_to_ids',[])))
    locations={p['id']:pick(p,'id','name','text','kind','aliases','parent_id') for p in state['locations'] if allowed(p)}
    for loc in locations.values():
        if loc.get('parent_id') not in locations:loc.pop('parent_id',None)
    hidden_locations={x for p in state['locations'] if p['id'] not in locations for x in (p['id'],p.get('name'),*p.get('aliases',[]))}
    def known_location(value):
        # V2 allows both location IDs and legacy display names.
        return value not in hidden_locations
    public=pick(state,'protagonist_id','controlled_actor_id','world_clock')
    cp=(public.get('world_clock',{}).get('calendar') or {}).get('profile') or {}
    if cp.get('observances'):
        cp['observances']=[o for o in cp['observances'] if set(o.get('character_ids',[]))<=people]
    camp=pick(state['campaign'],'title','setting','era','genre','tone','public_description')
    camp.update(description=camp.get('public_description',''),rules='')
    out={group:{} for group in (*KINDS,*SOCIAL)};out['version']=2
    if 'communication' in world:out['communication']=pick(world['communication'],'profile_version','preset','text_message','voice_call','presentation','region','ring_timeout_minutes','emergency_numbers','letter','courier','telegram','landline','magic','delivery_policy','delivery_minutes')
    public.update(campaign=camp,locations=list(locations.values()),characters=[],world=out,sections={},story_notes='')
    for fid in world['facts']:
        if fid in facts:
            row=pick(world['facts'][fid],'id','text','secret','story_secret','character_ids','secret_subject_ids','secret_keeper_ids','secret_biography_ids')
            row['evidence']=[];out['facts'][fid]=row
    for key,k in current.values():
        if k['fact_id'] in facts and k['actor_id'] in people and k['status'] in ('known','suspected'):
            # Shared ordinary knowledge is readable in the Workshop, but knowing a secret
            # does not reveal everyone else's beliefs about that secret.
            f=world['facts'][k['fact_id']]
            if k['actor_id']==actor or not(f.get('secret') or f.get('story_secret') or f.get('visibility')=='secret'):
                out['knowledge'][key]=pick(k,'actor_id','fact_id','status')
    for key,e in world['events'].items():
        if allowed(e):out['events'][key]=pick(e,'id','text','participants','witnesses','minute','fact_ids','medium','player_observed')
    events=set(out['events'])
    def sourced(r):
        return allowed(r) and (not r.get('source_event_id') or r['source_event_id'] in events)
    for key,r in world['scenes'].items():
        if allowed(r) and known_location(r.get('location')) and set(r.get('event_ids',[]))<=events:
            out['scenes'][key]=pick(r,'id','location','text','participants','start_minute','end_minute','status','event_ids')
    for key,e in out['events'].items():
        sid=world['events'][key].get('scene_id')
        if sid in out['scenes']:e['scene_id']=sid
    scene_id=state.get('camera',{}).get('scene_id')
    current=out['scenes'].get(scene_id,{})
    public.update(camera=dict(scene_id=scene_id if current else '',mode=state.get('camera',{}).get('mode','actor')),
                  scene=current.get('text',''),scene_meta=dict(time=public['world_clock'].get('last_event_time',''),
                  location=current.get('location',''),present_ids=current.get('participants',[])))
    for key,r in world['threads'].items():
        if not sourced(r) or r.get('last_event_id') and r['last_event_id'] not in events: continue
        if not r.get('public_state') and 'visible_to_ids' not in r and reserved_people.intersection(r.get('character_ids',[])):continue
        summary=r.get('public_state','')
        explicit='visible_to_ids' in r
        out['threads'][key]=dict(pick(r,'id','status','character_ids'),description=(r.get('description','') if explicit else summary or r.get('description','')),
                                 state=summary or (r.get('state','') if not reserved_people.intersection(r.get('character_ids',[])) else ''))
    for key,r in world['relationships'].items():
        if not allowed(r):continue
        if 'visible_to_ids' not in r and r['source_id']!=actor and r['source_id'] in reserved_people:continue
        out['relationships'][key]=pick(r,'source_id','target_id','dimensions','context')
    public['relationships']=[dict(source_id=r['source_id'],target_id=r['target_id'],text=r.get('context','')) for r in out['relationships'].values()]
    for group,keys in SOCIAL.items():
        for key,r in world.get(group,{}).items():
            if not sourced(r) or r.get('location_id') and not known_location(r['location_id']):continue
            if group=='contacts' and (not r.get('identity_visible',True) and r.get('owner_id')!=actor):continue
            if group=='reproductive_events' and not r.get('source_event_id'):continue
            if group=='pregnancies' and (r.get('fact_id') not in known or any(ch.get('id') not in people for ch in r.get('children',[]))):continue
            row=pick(r,'id','status','since','until','since_date','until_date',*keys)
            if group=='contacts' and not r.get('identity_visible',False):row.pop('character_id',None)
            if 'location_ids' in row:row['location_ids']=[x for x in row['location_ids'] if x in locations]
            # Context on merged objective edges can include a *private directed*
            # edge even when the basis fact is ordinary. Show the confirmed basis.
            basis=out['facts'].get(r.get('fact_id'),{})
            if group=='objective_relations':row['context']=basis.get('text','')
            elif group in ('roles','organizations','residences'):row['context']=r.get('context','')
            out[group][key]=row
    for r in out['roles'].values():
        if r.get('organization_id') not in out['organizations']:r.pop('organization_id',None)
    for key,s in world['scheduled_events'].items():
        if not sourced(s) or s.get('resolved_event_id') and s['resolved_event_id'] not in events:continue
        if s.get('location_id') and not known_location(s['location_id']):continue
        out['scheduled_events'][key]=pick(s,'id','description','participants','character_ids','status','due_minute','type','location_id')
    # Never expose schedules conditional on a hidden earlier appointment.
    while bad:={k for k in out['scheduled_events'] if not set(world['scheduled_events'][k].get('depends_on',[]))<=out['scheduled_events'].keys()}:
        for k in bad:del out['scheduled_events'][k]
    visible_refs={k:records.keys() for k,records in out.items() if isinstance(records,dict)}
    visible_refs.update(characters=people,locations=locations.keys(),fact_ids=facts,event_ids=events)
    bindings=state.get(BINDINGS,{})
    for cid,card in cards.items():
        a=world['characters'].get(cid,{})
        row=pick(a,'id','location','situation','emotion','minute','life_status','developmental_stage','biological_sex','birth_date','physical_state','capabilities','reproductive_capability')
        if a.get('scene_id') in out['scenes']:row['scene_id']=a['scene_id']
        if not known_location(row.get('location')):row.pop('location',None)
        if a.get('life_fact_id') and a['life_fact_id'] not in facts:row.pop('life_status',None)
        if a.get('last_event_id') and a['last_event_id'] not in events:
            row.pop('situation',None);row.pop('emotion',None)
        for mk in ('goals','intentions','obligations'):
            rows=[]
            for m in a.get(mk,[]):
                if isinstance(m,str):rows.append(m);continue
                deps=m.get('dependencies',{})
                if sourced(m) and all(k in visible_refs and set(ids)<=visible_refs[k] for k,ids in deps.items()):
                    rows.append(pick(m,'text','status','due_minute'))
            if rows:row[mk]=rows
        field_gates=bindings.get(cid,{}) if isinstance(bindings,dict) else None
        def readable(k):
            if k in PRIVATE_FIELDS or k in DYNAMIC or not isinstance(field_gates,dict):return False
            if k in field_gates:
                refs=field_gates[k]
                return isinstance(refs,list) and all(isinstance(x,str) and x in facts and x in known for x in refs)
            if k=='Биография' and cid in hidden_bio:return False
            if k=='Страхи и уязвимости' and cid in reserved_people:return False
            return k in CARD_FIELDS or k in ('Ценности','Приоритеты','Пол') or not unknown
        fields={k:v for k,v in card['fields'].items() if readable(k)}
        if not readable('Возраст'):
            for key in ('birth_date', 'developmental_stage'):
                row.pop(key, None)
        if not readable('Пол') or not birth_sex_disclosed(world, cid, actor, known.__contains__):
            row.pop('biological_sex', None)
            row.pop('reproductive_capability', None)
            fields.pop('Пол', None)
        public_card=dict(pick(card,'id','name','is_player'),fields=fields)
        # An alias can itself be an undiscovered identity in imported dossiers.
        if cid not in reserved_people:public_card.update(pick(card,'aliases'))
        public['characters'].append(public_card)
        app=a.get('appearance') or {}
        features={i:pick(f,'category','kind','text') for i,f in app.get('items',{}).items() if sourced(f) and (not f.get('condition_id') or f['condition_id'] in out['conditions'])}
        if features and readable('Внешность'):row['appearance']={'items':features}
        traits={i:pick(t,'field','text') for i,t in (a.get('personality') or {}).get('items',{}).items() if
                sourced(t) and readable(TRAIT_LABELS.get(t.get('field'),'Характер'))}
        if traits:row['personality']={'items':traits}
        vals={i:pick(v,'text','status') for i,v in (a.get('values') or {}).items() if sourced(v) and v.get('status')=='active'}
        if vals and readable('Ценности'):row['values']=vals
        out['characters'][cid]=row
    return public
