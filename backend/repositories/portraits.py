"""Atomic portrait edits; immutable originals retained across all snapshot lineage.

Removal detaches a reference in this snapshot. Physical cleanup is intentionally
conservative: assets live for the DB lifetime because archived turns/variants and
copied saves may still reference them. No unsafe reachability guesses or TTL.
"""
import json
import uuid
from copy import deepcopy
from backend.runtime_v3.models import PortraitReference, WorldHistoryV3
from backend.runtime_v3.portraits import authorized, life_period


def initialize(db):
    db.execute('''CREATE TABLE IF NOT EXISTS portrait_assets (
      id TEXT PRIMARY KEY, world_id INTEGER NOT NULL, content BLOB NOT NULL,
      width INTEGER NOT NULL, height INTEGER NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    db.execute("INSERT OR IGNORE INTO schema_migrations(name) VALUES('portrait_assets_v1')")


def load(db,sid,cid):
    row=db.execute('SELECT s.* FROM saves s JOIN worlds w ON w.id=s.world_id WHERE s.id=? AND w.deleted=0',(sid,)).fetchone()
    if row is None: raise ValueError('Портрет недоступен.')
    snapshot=json.loads(row['state_json'])
    from backend.runtime_v3.models import assert_world_state_v3_invariants
    from backend.runtime_v3.appearance import initialize_profiles
    snapshot['world_state']=assert_world_state_v3_invariants(snapshot['world_state'])
    initialize_profiles(snapshot)
    if not authorized(snapshot['world_state'],cid): raise ValueError('Портрет недоступен.')
    return row,snapshot


def listing(repo,sid,cid):
    with repo.connect() as db:
        row,snapshot=load(db,sid,cid)
        from backend.runtime_v3.portraits import projection
        return dict(revision=row['revision'],portraits=[p for p in snapshot['world_state']['characters'][cid]['portraits'] if not p['deleted']],
                    **projection(snapshot['world_state'],cid))


def asset(repo,sid,cid,aid):
    with repo.connect() as db:
        row,snapshot=load(db,sid,cid)
        if not any(p['asset_id']==aid and not p['deleted'] for p in snapshot['world_state']['characters'][cid]['portraits']):
            raise ValueError('Портрет недоступен.')
        value=db.execute('SELECT content FROM portrait_assets WHERE id=? AND world_id=?',(aid,row['world_id'])).fetchone()
        if value is None: raise ValueError('Портрет недоступен.')
        return value[0]


def edit(repo,sid,cid,revision,*,image=None,portrait_id=None,changes=None,remove=False):
    from backend.runtime_v3.repository import append_history
    from backend.repositories.living_world import project
    changes=changes or {}
    if set(changes)-{'crop','label','stage','min_age','max_age','make_current'}: raise ValueError('Неизвестное поле портрета.')
    with repo.connect() as db:
        db.execute('BEGIN IMMEDIATE');repo._assert_idle(db,sid)
        row,snapshot=load(db,sid,cid)
        if row['revision']!=revision: raise ValueError('Сейв изменился. Обнови карточку.')
        actor=snapshot['world_state']['characters'][cid];before=deepcopy(actor['portraits'])
        existing=next((p for p in actor['portraits'] if p['id']==portrait_id and not p['deleted']),None)
        if portrait_id is not None and existing is None: raise ValueError('Портрет недоступен.')
        if image is not None:
            if len(actor['portraits'])>=128: raise ValueError('Достигнут лимит 128 портретов персонажа.')
            content,w,h=image;aid=uuid.uuid4().hex
            _,stage=life_period(snapshot['world_state'],cid)
            p=PortraitReference(id=uuid.uuid4().hex,asset_id=aid,width=w,height=h,stage=stage,
                                order=max((p['order'] for p in actor['portraits']),default=0)+1).model_dump()
            # Replacement retains its predecessor in history; no shared mutable binary.
            if existing: p.update({k:deepcopy(existing[k]) for k in ('stage','min_age','max_age','label')})
            db.execute('INSERT INTO portrait_assets(id,world_id,content,width,height) VALUES(?,?,?,?,?)',(aid,row['world_id'],content,w,h))
            actor['portraits'].append(p)
        elif existing: p=existing
        else: raise ValueError('Выбери изображение.')
        p.update({k:deepcopy(v) for k,v in changes.items() if k!='make_current'})
        if changes.get('make_current'):
            p['order']=max((x['order'] for x in actor['portraits']),default=0)+1
        if remove: p['deleted']=True
        validated=PortraitReference.model_validate(p).model_dump();p.clear();p.update(validated)
        batch=WorldHistoryV3()
        batch.state_changes.append(dict(kind='portrait_edit',entity=cid,source='user_attachment',
            minute=snapshot['world_state']['meta']['world_time'],before=before,after=deepcopy(actor['portraits'])))
        snapshot['history_head']=append_history(db,snapshot.get('history_head'),batch.to_dict())
        project(db,sid,snapshot)
        db.execute('UPDATE saves SET state_json=?,revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=?',(json.dumps(snapshot,ensure_ascii=False),sid))
    return listing(repo,sid,cid)
