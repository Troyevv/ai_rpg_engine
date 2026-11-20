"""Portrait presentation and scoped assets for versioned pre-game drafts."""
from copy import deepcopy
import hashlib
import json
import uuid
from pydantic import TypeAdapter
from backend.runtime_v3.models import PortraitDescriptor, ProceduralPortrait, ProceduralPortraitV2, ProceduralPortraitV3, ProceduralPortraitV4
from backend.runtime_v3.portraits import life_period, projection, visual_age
from backend.repositories.portraits import mutate


from backend.runtime_v3.portrait_catalog import ILLUSTRATION, ILLUSTRATION_STYLES

DESCRIPTORS = TypeAdapter(PortraitDescriptor)

def authoring_context(state):
    """Include canonical appearance in authoring prompts and omit v3 renderer geometry."""
    actors = state['world']['characters']
    actors_without_art = {}
    for cid, actor in actors.items():
        art = actor.get('procedural_portrait') or {}
        actors_without_art[cid] = ({k:v for k,v in actor.items() if k != 'procedural_portrait'}
                              if art.get('version') in (3,4) else actor)
    return {**state, 'world':{**state['world'], 'characters':actors_without_art}}


def portrait_state(state):
    # Minimal adapter to the existing portrait selector, no second calendar/POV rules.
    return dict(characters=state['world']['characters'], knowledge=state['world'].get('knowledge',{}),
        facts=state['world'].get('facts', {}),
        pregnancies=state['world'].get('pregnancies',{}), camera={'controlled_actor_id':state.get('controlled_actor_id')},
        meta={'world_time':state['world_clock']['minute'],'calendar':state['world_clock'].get('calendar')})


def body_frame(actor):
    sex = actor.get('biological_sex')
    return sex if sex in ('male', 'female') else 'neutral'


def beard_eligible(actor, stage):
    return stage == 'adult' and body_frame(actor) == 'male'


def default_descriptor(cid,stage,actor=None,hints=None,age_style=None, *, version=2, world_id="", profile="neutral", art_style="legacy", warnings=None):
    from backend.services.portrait_traits import FACIAL_HAIR, graphic_choices
    identity = json.dumps([world_id, cid], ensure_ascii=False) if version >= 3 else 'workshop-portrait-v1:'+cid
    seed=hashlib.sha256(identity.encode()).hexdigest()[:32]
    # Neutral graphic choices never become canonical appearance facts.
    values=[int(seed[i:i+2],16) for i in range(0,14,2)]
    hinted_form = hints.get('form') if isinstance(hints,dict) else None
    human = stage in ('infant','child','adolescent','adult') or version>=3 and hinted_form=='human'
    form = 'human' if human and hinted_form!='neutral' else 'neutral'
    choices=dict(face=values[0]%7,hair=values[1]%8,skin=values[2]%7,eyes=values[3]%7,
        clothing=0,accessory=0,palette=values[6]%7)
    actor = actor or {}
    eligible = (version >= 2 and form == 'human' and beard_eligible(actor, stage)
                and age_style not in ('infant', 'child', 'adolescent'))
    if version==4:
        # Domain-separated draws make individual choices independent. Persist
        # every selected ID, so reopening never depends on the current catalog.
        def pick(field, pool):
            digest=hashlib.sha256((seed+':'+field).encode()).digest()
            return tuple(pool)[int.from_bytes(digest[:8],'big') % len(pool)]
        traits={key:pick(key,options) for key,options in ILLUSTRATION_STYLES.items()}
        traits.update(clothing=pick('clothing',ILLUSTRATION['wardrobes'].get(profile, ILLUSTRATION['wardrobes']['neutral'])),
                      hair_color=pick('hair_color', ILLUSTRATION['natural_hair']), detail='none', expression='neutral')
        if not eligible: traits['facial_hair']='clean_shaven'
        traits.update(graphic_choices(actor,hints,facial_hair=eligible,warnings=warnings,semantic=True))
        return ProceduralPortraitV4(version=4,art_revision=1,art_style=art_style,seed=seed,
                stage=stage,form=form,visual_age=age_style,palette=choices['palette'],
                body_frame=body_frame(actor) if form=='human' else 'neutral',traits=traits).model_dump(exclude_none=True)
    authored = graphic_choices(actor, hints, facial_hair=eligible, warnings=warnings, catalog_labels=version==3) if form=='human' or version==3 else {}
    choices.update(authored)
    common = dict(seed=seed, stage=stage, form=form, visual_age=age_style)
    if version < 3:
        for key in ('hair','clothing'):
            if choices[key] > 7: choices[key] = values[1]%8 if key=='hair' else 0
    if version == 1:
        return ProceduralPortrait(**common, **choices).model_dump()
    style = choices.pop('facial_hair', int(seed[14:16], 16) % len(FACIAL_HAIR))
    if version == 3:
        from backend.runtime_v3.portrait_catalog import CATALOG, STYLES
        wardrobes = CATALOG['wardrobes']
        pool = wardrobes.get(profile, wardrobes['neutral']) if isinstance(profile,str) else wardrobes['neutral']
        hair = STYLES['hair'][authored.get('hair', values[1] % len(STYLES['hair']))]
        garment = STYLES['clothing'][authored['clothing']] if 'clothing' in authored else pool[values[4] % len(pool)]
        choices.update(hair=min(STYLES['hair'].index(hair),7), clothing=min(STYLES['clothing'].index(garment),7),
                       eyes=authored.get('eyes',values[3] % len(STYLES['eyes'])))
        choices.setdefault('hair_color',int(seed[16:18],16)%len(STYLES['hair_color']))
        choices.setdefault('clothing_color',int(seed[18:20],16)%len(STYLES['clothing_color']))
        def pick(field, pool):
            digest = hashlib.sha256(f'{seed}:{field}'.encode()).digest()
            return tuple(pool)[int.from_bytes(digest[:4], 'big') % len(pool)]
        for field, options in CATALOG['features'].items():
            choices.setdefault(field, pick(field, options))
        # Keep explicit choices. Pattern baldness and adult beard presets are poor defaults for children.
        age = age_style or stage
        if age == 'infant':
            if 'hair' not in authored:
                hair = pick('infant-hair', ('short','buzz','bald','curly','fringe'))
                choices['hair'] = min(STYLES['hair'].index(hair), 7)
            if 'clothing' not in authored:
                garment = pick('infant-garment', ('smock','plain','jumper') if profile == 'modern' else ('smock','plain'))
                choices['clothing'] = min(STYLES['clothing'].index(garment), 7)
        if age in ('child', 'adolescent') and 'hair' not in authored and hair == 'receding':
            hair = pick('juvenile-hair', ('short', 'curly', 'fringe', 'medium', 'bob'))
            choices['hair'] = min(STYLES['hair'].index(hair), 7)
        if age in ('infant','child','adolescent') and 'hair_color' not in authored:
            choices['hair_color'] = pick('juvenile-color', (0,1,2,3,4))
        if age == 'elderly' and 'hair_color' not in authored:
            choices['hair_color'] = pick('age-hair', (0, 1, 3, 5, 5, 5, 6))
        if eligible and 'facial_hair' not in authored:
            style = pick('beard', (0, 0, 0, 1, 1, 2, 3, 4))
        return ProceduralPortraitV3(**common, **choices, version=3, hairstyle=hair, garment=garment,
            visage=STYLES['face'][choices['face']], face_revision=4, eye_revision=2, skin_swatch=True,eye_swatch=True,
            body_frame=body_frame(actor) if form=='human' else 'neutral',
            facial_hair=FACIAL_HAIR[style] if eligible else 'clean_shaven').model_dump()
    return ProceduralPortraitV2(**common, **choices, version=2,
        body_frame=body_frame(actor) if form == 'human' else 'neutral',
        facial_hair=FACIAL_HAIR[style] if eligible else 'clean_shaven').model_dump()


def world_art(state):
    campaign = state.get('campaign', {})
    return dict(world_id=state.get('portrait_world_id') or json.dumps(campaign, sort_keys=True),
                profile=campaign.get('portrait_profile', 'neutral'),
                art_style='legacy')


def consume_authored_traits(state, warnings=None, *, version=3):
    """Materialize art direction once, after ID remap; never add it to a card."""
    runtime=portrait_state(state)
    for card in state['characters']:
        hints=card.pop('portrait_traits',None)
        cid=card['id'];actor=runtime['characters'].get(cid)
        if hints is not None and actor is not None and not actor.get('procedural_portrait'):
            actor['procedural_portrait']=default_descriptor(cid,life_period(runtime,cid)[1],actor,hints,visual_age(runtime,cid),version=version, warnings=warnings, **world_art(state))


def refine_automatic(state, cid, hints, warnings=None):
    if state.get('authoring', {}).get('manual_portraits', {}).get(cid): return
    runtime = portrait_state(state)
    actor = runtime['characters'][cid]
    old = actor.get('procedural_portrait') or {}
    generated = default_descriptor(cid, life_period(runtime,cid)[1], actor, hints, visual_age(runtime,cid),
                                   version=4 if old.get('version')==4 else 3, **{**world_art(state),'art_style':old.get('art_style','legacy')})
    if old.get('version') not in (3,4) or old.get('version') != generated['version'] or old.get('seed') != generated['seed']: return
    if old['version']==4:
        from backend.services.portrait_traits import graphic_choices
        conflicts=[]
        eligible=beard_eligible(actor,generated['stage']) and generated['form']=='human'
        traits=graphic_choices(actor,hints,facial_hair=eligible,warnings=conflicts,semantic=True)
        old['traits'].update(traits)
        if not eligible: old['traits']['facial_hair']='clean_shaven'
        if isinstance(hints,dict) and hints.get('form') in ('human','neutral') or old['stage']=='unknown' and generated['stage']!='unknown':
            old['form']=generated['form']
        for key in ('body_frame','stage','visual_age'):
            old[key]=generated.get(key)
        if old['form']=='neutral':
            old['body_frame']='neutral'
            old['traits']['facial_hair']='clean_shaven'
        if warnings is not None:
            warnings.extend(dict(category='portrait_traits',path=f'/characters/{cid}/portrait_traits',message=w) for w in conflicts)
        return
    from backend.services.portrait_traits import graphic_choices
    conflicts=[]
    fields=graphic_choices(actor,hints,facial_hair=beard_eligible(actor,generated['stage']),warnings=conflicts,catalog_labels=True)
    if warnings is not None:
        warnings.extend(dict(category='portrait_traits',path=f'/characters/{cid}/portrait_traits',message=message) for message in conflicts)
    if old['stage']=='unknown' and generated['stage']!='unknown':
        old['form']=generated['form']
    old.update(stage=generated['stage'],visual_age=generated.get('visual_age'),body_frame=generated['body_frame'])
    if not beard_eligible(actor,generated['stage']): old['facial_hair']='clean_shaven'
    if old['visual_age'] is None: old.pop('visual_age')
    for field in fields:
        old[field] = generated[field]
        layer = {'hair':'hairstyle','clothing':'garment','face':'visage'}.get(field)
        if layer: old[layer] = generated[layer]
    if isinstance(hints,dict) and hints.get('form') in ('human','neutral'):
        old.update(form=generated['form'],facial_hair=generated['facial_hair'])
    if old['form']=='neutral': old.update(body_frame='neutral',facial_hair='clean_shaven')


def initialize(state, *, version=1, character_ids=None):
    """Historical drafts could display v1 without storing a descriptor at all."""
    runtime=portrait_state(state)
    for cid in runtime['characters'] if character_ids is None else character_ids:
        actor = runtime['characters'][cid]
        if not actor.get('procedural_portrait'):
            actor['procedural_portrait']=default_descriptor(cid,life_period(runtime,cid)[1],actor,age_style=visual_age(runtime,cid),version=version,**world_art(state))
    return state


def appearance_disclosed(state, public_card):
    """An explicitly spoiler-gated description also gates its visual representation.

    public_card comes from the SAME player projection as the dossier (including
    canonical Knowledge and fact visibility). No inference from absent/empty prose.
    """
    from backend.services.draft_player_view import BINDINGS
    bindings=state.get(BINDINGS,{})
    gates=bindings.get(public_card['id'],{}) if isinstance(bindings,dict) else None
    from backend.runtime_v3.appearance import VISUAL_FIELDS
    return isinstance(gates,dict) and all(field not in gates or field in public_card['fields'] for field in VISUAL_FIELDS)


def reader_card(state,cid):
    from backend.services.draft_world import player_view
    card=next((c for c in player_view(state)['characters'] if c['id']==cid),None)
    if card is None: raise ValueError('Портрет недоступен.')
    return card


def can_update_eyes(actor):
    art = actor.get('procedural_portrait') or {}
    return (art.get('version') == 3 and art.get('face_revision') in (3, 4)
            and art.get('eye_revision') is None and art.get('form') == 'human'
            and not any(not image.get('deleted') for image in actor.get('portraits', [])))


def presentation_for(state,runtime,card,author):
    cid=card['id']
    if not author and not appearance_disclosed(state,card):
        return dict(portrait=None,procedural_portrait=None,silhouette='neutral')
    result=projection(runtime,cid)
    if author:
        actor = runtime['characters'][cid]
        result['procedural_portrait'] = actor['procedural_portrait']
        if can_update_eyes(actor):
            result['can_update_eyes'] = True
    return result


def presentation_map(state,visible_cards,author):
    runtime=portrait_state(initialize(deepcopy(state)))
    return {c['id']:presentation_for(state,runtime,c,author)
            for c in visible_cards if c['id'] in runtime['characters']}


def load(repo,db,wid,cid,revision=None,editable=False):
    w=repo._draft_workspace(db,wid,revision,idle=editable)
    head=repo._draft_head(db,wid)
    if not head: raise ValueError('Сначала создайте мир.')
    record=json.loads(head['content'])
    from backend.services.draft_world import prepare
    state=prepare(record['state'])
    if cid not in state['world']['characters']: raise ValueError('Портрет недоступен.')
    return w,record,state


def listing(repo,wid,cid,author=False):
    with repo.connect() as db:
        w,_,state=load(repo,db,wid,cid)
        # Same computed fallback as /draft, without persisting a read.
        initialize(state)
        if not author:
            card=reader_card(state,cid)
            return dict(revision=w['revision'],portraits=[],**presentation_for(state,portrait_state(state),card,False))
        runtime=portrait_state(state)
        return dict(revision=w['revision'], portraits=[p for p in runtime['characters'][cid].get('portraits',[]) if not p['deleted']],
                    **projection(runtime,cid), **editor_metadata(runtime,cid,wid))


def editor_metadata(runtime,cid,world_id):
    actor=runtime['characters'][cid]
    age,stage=life_period(runtime,cid)
    descriptor=actor.get('procedural_portrait')
    return dict(descriptor=descriptor or default_descriptor(cid,stage,actor,age_style=visual_age(runtime,cid),
                         world_id=str(world_id),version=3),
                portrait_mode=actor.get('portrait_mode','auto'),
                anatomy_reference=dict(body_frame=body_frame(actor),facial_hair_allowed=beard_eligible(actor,stage)),
                age_reference=dict(age=age,stage=stage,visual_age=visual_age(runtime,cid)))


def asset(repo,wid,cid,aid,author=False):
    with repo.connect() as db:
        _,_,state=load(repo,db,wid,cid)
        if not author:
            card=reader_card(state,cid)
            selected=presentation_for(state,portrait_state(state),card,False)['portrait']
            if not selected or selected['asset_id']!=aid: raise ValueError('Портрет недоступен.')
        if not any(p['asset_id']==aid and not p['deleted'] for p in state['world']['characters'][cid].get('portraits',[])):
            raise ValueError('Портрет недоступен.')
        row=db.execute("SELECT content FROM portrait_assets p JOIN portrait_asset_access a ON p.id=a.asset_id WHERE p.id=? AND a.scope='draft' AND a.owner=?",(aid,wid)).fetchone()
        if row is None: raise ValueError('Портрет недоступен.')
        return row[0]


def apply_descriptor(runtime,cid,descriptor,mode,*,preserve_mode=False):
    actor=runtime['characters'][cid]
    art=DESCRIPTORS.validate_python(descriptor)
    old=actor.get('procedural_portrait') or {}
    same_basis=(old.get('version')==4 and isinstance(art,ProceduralPortraitV4) and
                all(old.get(k)==getattr(art,k) for k in ('stage','visual_age','visual_age_mode')))
    if art.visual_age_mode == 'auto' and not same_basis:
        # Resolve once at explicit save, never silently redraw on a birthday.
        art.stage=life_period(runtime,cid)[1]
        art.visual_age=visual_age(runtime,cid)
    elif art.visual_age_mode == 'manual' and art.visual_age is None:
        raise ValueError('Выберите визуальный возраст.')
    beard = art.traits['facial_hair'] if isinstance(art, ProceduralPortraitV4) else getattr(art,'facial_hair','clean_shaven')
    if beard != 'clean_shaven':
        if (art.form != 'human' or art.visual_age in ('infant','child','adolescent')
                or not beard_eligible(actor, life_period(runtime,cid)[1])):
            raise ValueError('Растительность на лице доступна только взрослому мужчине со взрослым визуальным возрастом.')
    actor['procedural_portrait']=art.model_dump(exclude_none=isinstance(art,ProceduralPortraitV4))
    if not preserve_mode: actor['portrait_mode']=mode or 'procedural'


def edit(repo,wid,cid,revision,*,image=None,portrait_id=None,changes=None,remove=False,descriptor=None,mode=None,descriptors=None,preserve_mode=False):
    with repo.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        _,record,state=load(repo,db,wid,cid,revision,editable=True)
        runtime=portrait_state(state);actor=runtime['characters'][cid]
        if descriptor is not None or descriptors:
            for target, art in (descriptors or {cid:descriptor}).items():
                if target not in runtime['characters']: raise ValueError('Портрет недоступен.')
                apply_descriptor(runtime,target,art,mode,preserve_mode=preserve_mode)
                if state.get('portrait_world_id'):
                    state.setdefault('authoring',{}).setdefault('manual_portraits',{})[target]=True
        elif mode is not None: actor['portrait_mode']=mode
        else:
            aid=uuid.uuid4().hex if image is not None else None
            mutate(actor,runtime,cid,image=image,asset_id=aid,portrait_id=portrait_id,changes=changes,remove=remove)
            if image is not None:
                content,w,h=image
                db.execute('INSERT INTO portrait_assets(id,world_id,content,width,height) VALUES(?,0,?,?,?)',(aid,content,w,h))
                db.execute("INSERT INTO portrait_asset_access VALUES(?,'draft',?)",(aid,wid))
        write_portrait_edit(repo, db, wid, state, record)
    return listing(repo,wid,cid,author=True)


def write_portrait_edit(repo, db, wid, state, record):
    # Visual-only changes do not add Knowledge or rewrite Appearance, but the
    # exact reviewed snapshot hash still becomes stale like every draft edit.
    review=record.get('review')
    if review: review=dict(review,status='stale',reason='Изменилось оформление персонажа; версия проверки устарела.')
    repo._write_draft(db,wid,state,'portrait',record.get('source',''),record.get('warnings',[]),
        outline=record.get('outline',''),generated=record.get('generated',False),review=review,origin_job=record.get('origin_job'))


def update_draft_eyes(repo, wid, revision):
    with repo.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        repo._draft_workspace(db, wid, revision, idle=True)
        head = repo._draft_head(db, wid)
        if not head:
            raise ValueError('Черновик недоступен.')
        record = json.loads(head['content'])
        state = record['state']
        count = 0
        for actor in state['world']['characters'].values():
            if can_update_eyes(actor):
                actor['procedural_portrait']['eye_revision'] = 2
                count += 1
        if count:
            write_portrait_edit(repo, db, wid, state, record)
        return {'updated': count}


def handoff_assets(db,wid,world_id,state,*,scope='world'):
    for actor in state['world']['characters'].values():
        for p in actor.get('portraits',[]):
            aid=p['asset_id']
            if not db.execute("SELECT 1 FROM portrait_asset_access WHERE asset_id=? AND scope='draft' AND owner=?",(aid,wid)).fetchone():
                raise ValueError('Оригинал портрета недоступен этому черновику. Загрузите изображение заново.')
            db.execute("INSERT OR IGNORE INTO portrait_asset_access VALUES(?,?,?)",(aid,scope,str(world_id)))


def export_assets(repo,wid,state):
    """Portable originals, scoped by the same capability as author preview."""
    import base64
    assets={}
    with repo.connect() as db:
        for actor in state['world']['characters'].values():
            for portrait in actor.get('portraits',[]):
                aid=portrait['asset_id']
                if aid in assets: continue
                row=db.execute("SELECT content FROM portrait_assets p JOIN portrait_asset_access a ON p.id=a.asset_id WHERE p.id=? AND a.scope='draft' AND a.owner=?",(aid,wid)).fetchone()
                if row is None: raise ValueError('Оригинал портрета недоступен для экспорта.')
                assets[aid]=base64.b64encode(row[0]).decode('ascii')
    return assets


def import_assets(db,wid,state,assets):
    """Import bytes transactionally; never grant access from a supplied asset ID."""
    import base64
    from backend.services.portrait_assets import decode_image,MAX_SIDE
    refs={p['asset_id'] for actor in state['world']['characters'].values() for p in actor.get('portraits',[])}
    if not refs: return
    if not isinstance(assets,dict): raise ValueError('В импорте отсутствуют оригиналы портретов. Используйте полный экспорт мастерской.')
    max_bytes=MAX_SIDE*MAX_SIDE*4+1024*1024
    replacements={}
    for old in refs:
        encoded=assets.get(old)
        if not isinstance(encoded,str) or len(encoded)>max_bytes*4//3+8:
            raise ValueError('Оригинал портрета отсутствует или превышает допустимый размер.')
        try: raw=base64.b64decode(encoded,validate=True)
        except ValueError as exc: raise ValueError('Повреждён оригинал портрета.') from exc
        # Stored originals are normalized PNGs by the existing upload service.
        content,w,h=decode_image(raw,'image/png',max_bytes=max_bytes)
        aid=uuid.uuid4().hex;replacements[old]=aid
        db.execute('INSERT INTO portrait_assets(id,world_id,content,width,height) VALUES(?,0,?,?,?)',(aid,content,w,h))
        db.execute("INSERT INTO portrait_asset_access VALUES(?,'draft',?)",(aid,wid))
    for actor in state['world']['characters'].values():
        for portrait in actor.get('portraits',[]): portrait['asset_id']=replacements[portrait['asset_id']]
