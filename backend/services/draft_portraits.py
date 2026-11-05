"""Portrait presentation and scoped assets for versioned pre-game drafts."""
from copy import deepcopy
import hashlib
import json
import uuid
from backend.runtime_v3.models import ProceduralPortrait
from backend.runtime_v3.portraits import life_period, projection
from backend.repositories.portraits import mutate


def portrait_state(state):
    # Minimal adapter to the existing portrait selector, no second calendar/POV rules.
    return dict(characters=state['world']['characters'], knowledge=state['world'].get('knowledge',{}),
        pregnancies=state['world'].get('pregnancies',{}), camera={'controlled_actor_id':state.get('controlled_actor_id')},
        meta={'world_time':state['world_clock']['minute'],'calendar':state['world_clock'].get('calendar')})


def default_descriptor(cid,stage,actor=None,hints=None):
    from backend.services.portrait_traits import graphic_choices
    seed=hashlib.sha256(('workshop-portrait-v1:'+cid).encode()).hexdigest()[:32]
    # Neutral graphic choices never become canonical appearance facts.
    values=[int(seed[i:i+2],16) for i in range(0,14,2)]
    form = 'human' if stage=='adult' and not (isinstance(hints,dict) and hints.get('form')=='neutral') else 'neutral'
    choices=dict(face=values[0]%7,hair=values[1]%8,skin=values[2]%7,eyes=values[3]%7,
        clothing=0,accessory=0,palette=values[6]%7)
    if form=='human': choices.update(graphic_choices(actor or {}, hints))
    return ProceduralPortrait(seed=seed,stage=stage,form=form,**choices).model_dump()


def consume_authored_traits(state):
    """Materialize art direction once, after ID remap; never add it to a card."""
    runtime=portrait_state(state)
    for card in state['characters']:
        hints=card.pop('portrait_traits',None)
        if hints is not None:
            from backend.services.portrait_traits import STYLES
            options = dict(STYLES,form=('human','neutral'))
            if not isinstance(hints,dict) or any(k not in options or v not in options[k] for k,v in hints.items()):
                raise ValueError('portrait_traits: используйте только поддерживаемые признаки из схемы.')
        cid=card['id'];actor=runtime['characters'].get(cid)
        if isinstance(hints,dict) and hints and actor is not None and not actor.get('procedural_portrait'):
            actor['procedural_portrait']=default_descriptor(cid,life_period(runtime,cid)[1],actor,hints)


def initialize(state):
    runtime=portrait_state(state)
    for cid,actor in runtime['characters'].items():
        if not actor.get('procedural_portrait'):
            actor['procedural_portrait']=default_descriptor(cid,life_period(runtime,cid)[1],actor)
    return state


def appearance_disclosed(state, public_card):
    """An explicitly spoiler-gated description also gates its visual representation.

    public_card comes from the SAME player projection as the dossier (including
    canonical Knowledge and fact visibility). No inference from absent/empty prose.
    """
    from backend.services.draft_player_view import BINDINGS
    bindings=state.get(BINDINGS,{})
    gates=bindings.get(public_card['id'],{}) if isinstance(bindings,dict) else None
    return isinstance(gates,dict) and ('Внешность' not in gates or 'Внешность' in public_card['fields'])


def reader_card(state,cid):
    from backend.services.draft_world import player_view
    card=next((c for c in player_view(state)['characters'] if c['id']==cid),None)
    if card is None: raise ValueError('Портрет недоступен.')
    return card


def presentation_for(state,runtime,card,author):
    cid=card['id']
    if not author and not appearance_disclosed(state,card):
        return dict(portrait=None,procedural_portrait=None,silhouette='neutral')
    result=projection(runtime,cid)
    if author:
        result['procedural_portrait']=runtime['characters'][cid]['procedural_portrait']
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
        return dict(revision=w['revision'],portraits=[p for p in runtime['characters'][cid].get('portraits',[]) if not p['deleted']],
            **projection(runtime,cid),descriptor=runtime['characters'][cid]['procedural_portrait'],
            portrait_mode=runtime['characters'][cid].get('portrait_mode','auto'))


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


def edit(repo,wid,cid,revision,*,image=None,portrait_id=None,changes=None,remove=False,descriptor=None,mode=None):
    with repo.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        _,record,state=load(repo,db,wid,cid,revision,editable=True)
        runtime=portrait_state(state);actor=runtime['characters'][cid]
        if descriptor is not None:
            actor['procedural_portrait']=ProceduralPortrait.model_validate(descriptor).model_dump()
            actor['portrait_mode']=mode or 'procedural'
        elif mode is not None: actor['portrait_mode']=mode
        else:
            aid=uuid.uuid4().hex if image is not None else None
            mutate(actor,runtime,cid,image=image,asset_id=aid,portrait_id=portrait_id,changes=changes,remove=remove)
            if image is not None:
                content,w,h=image
                db.execute('INSERT INTO portrait_assets(id,world_id,content,width,height) VALUES(?,0,?,?,?)',(aid,content,w,h))
                db.execute("INSERT INTO portrait_asset_access VALUES(?,'draft',?)",(aid,wid))
        # Visual-only changes do not add Knowledge or rewrite Appearance, but the
        # exact reviewed snapshot hash still becomes stale like every draft edit.
        review=record.get('review')
        if review: review=dict(review,status='stale',reason='Изменилось оформление персонажа; версия проверки устарела.')
        repo._write_draft(db,wid,state,'portrait',record.get('source',''),record.get('warnings',[]),
            outline=record.get('outline',''),generated=record.get('generated',False),review=review,origin_job=record.get('origin_job'))
    return listing(repo,wid,cid,author=True)


def handoff_assets(db,wid,world_id,state):
    for actor in state['world']['characters'].values():
        for p in actor.get('portraits',[]):
            aid=p['asset_id']
            if not db.execute("SELECT 1 FROM portrait_asset_access WHERE asset_id=? AND scope='draft' AND owner=?",(aid,wid)).fetchone():
                raise ValueError('Оригинал портрета недоступен этому черновику. Загрузите изображение заново.')
            db.execute("INSERT OR IGNORE INTO portrait_asset_access VALUES(?,'world',?)",(aid,str(world_id)))


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
