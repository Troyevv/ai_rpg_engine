"""SQLite worlds are immutable revisions; saves own independent snapshots."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from world_parser import parse_summary
from engine_storage import EngineStorage
from backend.repositories.runtime import RuntimeStorage
from backend.repositories.documents import DocumentStorage

DEFAULT_DB = Path(__file__).resolve().parent / 'data' / 'rpg.sqlite3'


class Storage(EngineStorage, RuntimeStorage, DocumentStorage):
    def __init__(self, path=None):
        self.path = Path(path or os.environ.get('RPG_DB_PATH', DEFAULT_DB))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        from backend.repositories.retired_schema import remove_retired_tables
        remove_retired_tables(self)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS worlds (
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL, name_key TEXT NOT NULL,
                    version INTEGER NOT NULL, source_md TEXT NOT NULL, digest TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                    UNIQUE(name_key, version), UNIQUE(name_key, digest));
                CREATE TABLE IF NOT EXISTS world_parts (
                    world_id INTEGER NOT NULL REFERENCES worlds(id),
                    kind TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(world_id, kind));
                CREATE TABLE IF NOT EXISTS saves (
                    id INTEGER PRIMARY KEY, world_id INTEGER NOT NULL REFERENCES worlds(id),
                    name TEXT NOT NULL, state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
                CREATE TABLE IF NOT EXISTS turns (
                    id INTEGER PRIMARY KEY, save_id INTEGER NOT NULL REFERENCES saves(id),
                    sequence INTEGER NOT NULL, user_text TEXT NOT NULL, assistant_text TEXT NOT NULL,
                    before_json TEXT NOT NULL, after_json TEXT NOT NULL,
                    UNIQUE(save_id, sequence));
            ''')

        self.init_engine()
        with self.connect() as db:
            db.execute("""CREATE INDEX IF NOT EXISTS turns_time_jumps ON turns(save_id,sequence)
                WHERE kind='long_term' OR json_type(changes_json,'$.time_skip')='object'""")
        self.init_runtime()
        self.init_documents()
        from backend.repositories.living_world import migrate
        migrate(self)
        from backend.runtime_v3.repository import migrate_database
        migrate_database(self)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def save_world(self, name, markdown):
        name = name.strip()
        if not name or len(name) > 120:
            raise ValueError('Название мира должно содержать от 1 до 120 символов.')
        state = parse_summary(markdown)
        digest = hashlib.sha256(markdown.encode('utf-8')).hexdigest()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT id FROM worlds WHERE name_key=? AND digest=?', (name.casefold(), digest)).fetchone()
            if existing:
                db.execute('UPDATE worlds SET deleted=0 WHERE id=?',(existing['id'],))
                return existing['id']
            version = db.execute('SELECT COALESCE(MAX(version),0)+1 FROM worlds WHERE name_key=?', (name.casefold(),)).fetchone()[0]
            world_id = db.execute('INSERT INTO worlds(name,name_key,version,source_md,digest) VALUES(?,?,?,?,?)',
                                  (name, name.casefold(), version, markdown, digest)).lastrowid
            db.executemany('INSERT INTO world_parts VALUES(?,?,?)',
                           [(world_id, key, json.dumps(value, ensure_ascii=False)) for key, value in state.items()])
        return world_id

    def list_worlds(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute('SELECT id,name,version,created_at FROM worlds WHERE deleted=0 ORDER BY id DESC')]

    def get_world(self, world_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM worlds WHERE id=?', (world_id,)).fetchone()
            if row is None:
                raise ValueError('Мир не найден.')
            result = dict(row)
            result['state'] = {row['kind']: json.loads(row['payload']) for row in db.execute(
                'SELECT kind,payload FROM world_parts WHERE world_id=?', (world_id,))}
            from backend.services.world import normalize
            result['state'] = normalize(result['state'])
            return result

    def create_save(self, world_id, name):
        name = name.strip()
        if not name or len(name) > 120:
            raise ValueError('Название прохождения должно содержать от 1 до 120 символов.')
        world = self.get_world(world_id)
        with self.connect() as db:
            from backend.runtime_v3.repository import migrate_snapshot
            snapshot,_=migrate_snapshot(db,world['state'])
            sid = db.execute('INSERT INTO saves(world_id,name,state_json) VALUES(?,?,?)',
                              (world_id, name, json.dumps(snapshot, ensure_ascii=False))).lastrowid
            from backend.repositories.living_world import project
            project(db,sid,snapshot)
            return sid

    def list_saves(self, world_id):
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                'SELECT id,name,created_at,updated_at FROM saves WHERE world_id=? ORDER BY id DESC', (world_id,))]

    def get_save(self, save_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM saves WHERE id=?', (save_id,)).fetchone()
            if row is None:
                raise ValueError('Прохождение не найдено.')
            result = dict(row)
            from backend.runtime_v3.selectors import ui_view
            from backend.runtime_v3.repository import read_history
            snapshot=json.loads(result.pop('state_json'))
            from backend.runtime_v3.models import assert_world_state_v3_invariants
            from backend.runtime_v3.repository import restore_biographical_secrets
            restore_biographical_secrets(db, snapshot)
            snapshot['world_state'] = assert_world_state_v3_invariants(snapshot['world_state'])
            from backend.runtime_v3.appearance import initialize_profiles as initialize_appearance
            initialize_appearance(snapshot)
            history,warnings=read_history(db,snapshot.get('history_head'))
            from backend.runtime_v3.notifications import read_story_receipts
            history['_story_receipts'] = read_story_receipts(db, snapshot.get('history_head'))
            result['state']=ui_view(snapshot,history)
            result['history_warnings']=warnings
            return result

    def context_history(self, save_id, before_id, limit, actor, main):
        """Choose IDs before projecting snapshot JSON. Sequence bounds bind regeneration."""
        with self.connect() as db:
            stop = (db.execute('SELECT sequence FROM turns WHERE id=? AND save_id=?', (before_id,save_id)).fetchone()[0]
                    if before_id is not None else 2**63-1)
            params = dict(save=save_id, stop=stop, actor=actor, main=main, limit=max(3,min(20,limit)))
            sequence = db.execute('SELECT max(sequence) FROM turns WHERE save_id=:save AND sequence<:stop', params).fetchone()[0]
            ids = {r[0] for r in db.execute("""
                SELECT id FROM turns WHERE save_id=:save AND sequence<:stop AND kind!='communication'
                AND (:actor IS NULL OR EXISTS(SELECT 1 FROM json_each(audience_json) WHERE value=:actor)
                     OR (coalesce(json_array_length(audience_json),0)=0 AND kind!='background'
                         AND coalesce(pov_actor_id,:main)=:actor))
                ORDER BY sequence DESC LIMIT :limit""",params)}
            # Preserve elapsed-time provenance across a long interval even when the jump
            # is outside the literary tail. Later situation edits can refresh old prose.
            jump = db.execute("""SELECT id,sequence FROM turns WHERE save_id=:save AND sequence<:stop
                AND (kind='long_term' OR json_type(changes_json,'$.time_skip')='object')
                ORDER BY sequence DESC LIMIT 1""",params).fetchone()
            refreshed = set()
            legacy_temporal = set()
            if jump:
                bounds = dict(params, start=jump['sequence']+1)
                refreshed.update(r[0] for r in db.execute("""
                    SELECT DISTINCT change.value FROM turns, json_each(changes_json,'$.context_situation_changes') change
                    WHERE save_id=:save AND sequence BETWEEN :start AND :stop-1""", bounds))
                # Older active variants have no receipt. Read their own snapshot
                # projections only where the original situation may have changed.
                legacy_temporal.update(r[0] for r in db.execute("""
                    SELECT id FROM turns WHERE save_id=:save AND sequence BETWEEN :start AND :stop-1
                    AND json_type(changes_json,'$.context_situation_changes') IS NULL
                    AND (json_type(changes_json,'$.state_patch') IS NULL
                         OR json_extract(before_json,'$.world_state.camera.situation')
                            IS NOT json_extract(after_json,'$.world_state.camera.situation')
                         OR EXISTS (SELECT 1 FROM json_each(changes_json,'$.state_patch.upserts.characters') c
                             WHERE json_extract(c.value,'$.situation')
                               IS NOT json_extract(before_json,'$.world_state.characters.' || json_quote(c.key) || '.situation')))
                    """, bounds))
                legacy_temporal.add(jump['id'])
        rows = self.list_turns(save_id, context=True, ids=ids|legacy_temporal)
        for row in rows:
            row['_temporal_only'] = row['id'] not in ids
            if jump and row['id'] == jump['id']:
                row['_refreshed_situations'] = refreshed
        return rows, 0 if sequence is None else sequence+1

    def list_turns(self, save_id, *, context=False, ids=None, sequences=None):
        with self.connect() as db:
            # Internal context metadata comes from the active turn snapshots.
            # Public history neither exposes GM situations nor ships snapshots.
            temporal = ''
            if context:
                for column, name in (('before_json', 'temporal_before'), ('after_json', 'temporal_after')):
                    temporal += f""", json_object(
                        'meta',json_object('world_time',json_extract({column},'$.world_state.meta.world_time'),
                                           'calendar',json_extract({column},'$.world_state.meta.calendar')),
                        'camera',json_object('situation',json_extract({column},'$.world_state.camera.situation')),
                        'characters',json((SELECT json_group_object(c.key,json_object('situation',json_extract(c.value,'$.situation')))
                            FROM json_each(turns.{column},'$.world_state.characters') c))) AS {name}"""
            clause, params = ' WHERE save_id=?', [save_id]
            for key, items in (('id', ids), ('sequence', sequences)):
                if items is not None:
                    clause += f' AND {key} IN (SELECT value FROM json_each(?))'
                    params.append(json.dumps(sorted(items)))
            rows = [dict(row) for row in db.execute(
                'SELECT id,sequence,user_text,assistant_text,kind,choices_json,changes_json,node_id,active_variant_id,memory_archived,pov_actor_id,audience_json,timing_json,CASE WHEN json_extract(changes_json,\'$.presentation.surface\') IS NOT NULL THEN \'{}\' ELSE before_json END AS before_json'
                + temporal + ' FROM turns' + clause + ' ORDER BY sequence', params)]
            from backend.runtime_v3.surfaces import route
            for row in rows:
                before = json.loads(row.pop('before_json'))
                row['presentation'] = json.loads(row['changes_json']).get('presentation') or route(before, row['kind'])
                if context:
                    for key in ('temporal_before', 'temporal_after'):
                        row[key] = json.loads(row[key])
            return rows

    def physical_choice_source(self, save_id, turns, state):
        from backend.runtime_v3.surfaces import physical_choice_source
        with self.connect() as db:
            def after_for(tid):
                row=db.execute('SELECT after_json FROM turns WHERE save_id=? AND id=?',(save_id,tid)).fetchone()
                return json.loads(row[0]) if row else {}
            return physical_choice_source(turns,state,after_for)

    def update_scene_meta(self, save_id, metadata, expected_revision=None):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._assert_idle(db, save_id)
            row = db.execute('SELECT state_json,revision FROM saves WHERE id=?', (save_id,)).fetchone()
            if row is None:
                raise ValueError('Прохождение не найдено.')
            if expected_revision is not None and row['revision'] != expected_revision:
                raise ValueError('Сейв изменился. Обнови сцену.')
            state = json.loads(row['state_json'])
            from backend.runtime_v3.models import Location, identity, assert_world_state_v3_invariants
            from backend.services.timeline import parse_time
            from backend.repositories.living_world import project
            world=state['world_state'];before=json.loads(row['state_json'])['world_state']
            def location_id(name, current_id):
                name = name.strip()
                if not name:
                    return current_id
                matches = [lid for lid, loc in world['locations'].items() if loc['name'].casefold() == name.casefold()]
                if current_id in matches:
                    return current_id
                if len(matches)>1:
                    raise ValueError('Имя места неоднозначно. Уточни название.')
                lid = matches[0] if matches else identity('location',name.casefold())
                world['locations'].setdefault(lid, Location(id=lid,name=name).model_dump())
                return lid

            lid = location_id(metadata['location'],world['camera']['location_id'])
            present = metadata['present_ids']
            if len(set(present)) != len(present) or any(cid not in world['characters'] for cid in present):
                raise ValueError('Проверь список участников сцены.')
            camera = world['camera']
            camera.update(location_id=lid, present_character_ids=present,
                          observed_character_ids=[cid for cid in camera['observed_character_ids'] if cid not in present],
                          remote_interactions=[row for row in camera['remote_interactions'] if row['actor_id'] not in present])
            for cid in present:
                world['characters'][cid]['location_id']=lid
            minute=parse_time(metadata['time'],world['meta']['world_time'])
            if minute is not None:world['meta']['world_time']=minute
            from backend.runtime_v3.models import Fact, Knowledge, WorldHistoryV3
            from backend.runtime_v3.repository import append_history
            batch = WorldHistoryV3()
            position = metadata.get('position')
            if position:
                actor = position['actor_id']
                if actor not in world['characters']:
                    raise ValueError('Неизвестный персонаж.')
                dest = location_id(position['location'],world['characters'][actor]['location_id'])
                world['characters'][actor]['location_id'] = dest
                camera = world['camera']
                if camera.get('controlled_actor_id') == actor and dest != lid:
                    camera.update(location_id=dest,present_character_ids=[actor],observed_character_ids=[])
                elif dest != lid:
                    camera['present_character_ids'] = [cid for cid in present if cid != actor]
                batch.state_changes.append(dict(kind='manual_position',source='player_edit',actor_id=actor,
                    location_id=dest,turn_id=world['meta']['turn_id']))
            if before['camera'] != world['camera']:
                batch.state_changes.append(dict(kind='manual_scene',source='player_edit',
                    turn_id=world['meta']['turn_id'], location_id=world['camera']['location_id'], present_ids=world['camera']['present_character_ids']))
            knowledge = metadata.get('knowledge')
            if knowledge:
                text = knowledge['text'].strip()
                actors = knowledge['actor_ids']
                if len(set(actors)) != len(actors) or any(cid not in world['characters'] for cid in actors):
                    raise ValueError('Укажи точное сведение и его получателей.')
                # An author's own proposition has stable identity, independent
                # of other assertions with the same words from different sources.
                fid = knowledge.get('fact_id')
                if fid:
                    from backend.runtime_v3.secrets import visible_fact_ids
                    if text or fid not in visible_fact_ids(before):
                        raise ValueError('Выбери доступное утверждение или введи новое.')
                else:
                    if not text:
                        raise ValueError('Введи текст нового сведения.')
                    fid = identity('manual-fact', text)
                    world['facts'].setdefault(fid, Fact(id=fid,text=text,visibility='secret').model_dump())
                for actor in actors:
                    key = actor + ':' + fid
                    prior = world['knowledge'].get(key, {})
                    if prior.get('status') == knowledge['status']:
                        continue
                    updated = Knowledge(actor_id=actor, fact_id=fid, status=knowledge['status'],
                        revision=prior.get('revision',0)+1,source_turn=world['meta']['turn_id'],
                        confirmed_once=prior.get('confirmed_once',False) or knowledge['status']=='known')
                    world['knowledge'][key] = updated.model_dump()
                    batch.state_changes.append(dict(kind='manual_knowledge',source='player_edit',
                        turn_id=world['meta']['turn_id'], actor_id=actor, fact_id=fid, status=updated.status))
            if metadata.get('social'):
                from backend.runtime_v3.manual_social import correct
                world = state['world_state'] = correct(world,batch,metadata['social'],row['revision'])
            assert_world_state_v3_invariants(world,before)
            state['history_head'] = append_history(db,state.get('history_head'),batch.to_dict(),before=before,after=world)
            project(db,save_id,state)
            db.execute("UPDATE saves SET state_json=?, revision=revision+1, updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
                       (json.dumps(state, ensure_ascii=False), save_id))

    def get_snapshot(self, save_id):
        with self.connect() as db:
            row=db.execute('SELECT state_json FROM saves WHERE id=?',(save_id,)).fetchone()
            if not row:raise ValueError('Прохождение не найдено.')
            snapshot=json.loads(row[0])
            from backend.runtime_v3.models import assert_world_state_v3_invariants
            from backend.runtime_v3.repository import restore_biographical_secrets
            restore_biographical_secrets(db, snapshot)
            snapshot['world_state'] = assert_world_state_v3_invariants(snapshot['world_state'])
            from backend.runtime_v3.appearance import initialize_profiles as initialize_appearance
            initialize_appearance(snapshot)
            from backend.runtime_v3.protagonist import initialize
            initialize(snapshot)
            return snapshot

    def story_secret_spoilers(self, save_id, revision, character_id=None):
        from backend.runtime_v3.repository import migrate_snapshot
        from backend.runtime_v3.secrets import spoiler_projection
        with self.connect() as db:
            row = db.execute('SELECT state_json,revision FROM saves WHERE id=?', (save_id,)).fetchone()
            if row is None: raise ValueError('Прохождение не найдено.')
            if row['revision'] != revision: raise ValueError('Сохранение изменилось. Обновите раздел.')
            snapshot, _ = migrate_snapshot(db, json.loads(row['state_json']))
            return dict(revision=revision, character_id=character_id,
                        rows=spoiler_projection(snapshot, character_id))
