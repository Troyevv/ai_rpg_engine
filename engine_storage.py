"""Durable drafts and optimistic, atomic game turns."""
import json
import sqlite3
import uuid

ACTIVE = ('generating', 'extracting', 'validating')
UNAPPLIED = "narrative_complete=1 AND status IN ('error','stopped')"


class ExistingJob(Exception):
    def __init__(self, job_id):
        self.job_id = job_id


class EngineStorage:
    def init_engine(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for table, additions in {
                'saves': {'revision': 'INTEGER NOT NULL DEFAULT 0'},
                'turns': {'kind': "TEXT NOT NULL DEFAULT 'turn'", 'choices_json': "TEXT NOT NULL DEFAULT '[]'",
                          'changes_json': "TEXT NOT NULL DEFAULT '{}'"},
            }.items():
                columns = {r['name'] for r in db.execute(f'PRAGMA table_info({table})')}
                for name, declaration in additions.items():
                    if name not in columns:
                        db.execute(f'ALTER TABLE {table} ADD COLUMN {name} {declaration}')
            db.execute('''CREATE TABLE IF NOT EXISTS game_jobs (
                id TEXT PRIMARY KEY, save_id INTEGER NOT NULL REFERENCES saves(id),
                revision INTEGER NOT NULL, before_json TEXT NOT NULL, user_text TEXT NOT NULL,
                kind TEXT NOT NULL, replaces_id INTEGER, status TEXT NOT NULL,
                narrative TEXT NOT NULL DEFAULT '', narrative_complete INTEGER NOT NULL DEFAULT 0,
                error TEXT NOT NULL DEFAULT '', config_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))''')
            columns={r['name'] for r in db.execute('PRAGMA table_info(game_jobs)')}
            if 'attempt_epoch' not in columns: db.execute('ALTER TABLE game_jobs ADD COLUMN attempt_epoch INTEGER NOT NULL DEFAULT 0')
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS active_game_job ON game_jobs(save_id) WHERE status IN ('generating','extracting','validating')")
            db.execute(f"CREATE INDEX IF NOT EXISTS unapplied_game_job ON game_jobs(save_id, revision) WHERE {UNAPPLIED}")
            db.execute('''CREATE TABLE IF NOT EXISTS archived_turns (
                id INTEGER PRIMARY KEY, save_id INTEGER NOT NULL, reason TEXT NOT NULL, payload TEXT NOT NULL)''')

    def latest_job(self, save_id, revision=None):
        with self.connect() as db:
            # Regeneration can leave multiple previews at one revision. An older
            # retry may be active, or a complete rejected scene may still block play.
            row = db.execute(f"""SELECT * FROM game_jobs WHERE id=COALESCE(
                (SELECT id FROM game_jobs WHERE save_id=? AND status IN ('generating','extracting','validating')),
                (SELECT id FROM game_jobs WHERE save_id=? AND revision=? AND {UNAPPLIED} ORDER BY rowid DESC LIMIT 1),
                (SELECT id FROM game_jobs WHERE save_id=? ORDER BY rowid DESC LIMIT 1))""",
                (save_id, save_id, revision, save_id)).fetchone()
            return dict(row) if row else None

    def get_job(self, job_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM game_jobs WHERE id=?', (job_id,)).fetchone()
            if row is None:
                raise ValueError('Черновик не найден.')
            return dict(row)

    def begin_job(self, save_id, user_text, kind, config):
        if kind not in ('start', 'turn', 'regenerate','background','pov','long_term','communication'):
            raise ValueError('Неизвестный тип хода.')
        from backend.runtime_v3.player_actions import EXTRACTION_VERSION
        from backend.services.structured_extraction import transport
        config = dict(config, _extraction_contract=EXTRACTION_VERSION, _extraction_transport=transport(config))
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            save = db.execute('SELECT * FROM saves WHERE id=?', (save_id,)).fetchone()
            if save is None:
                raise ValueError('Прохождение не найдено.')
            recovery = None
            source_id = config.pop('_recovery_source_job_id', None)
            if source_id:
                if kind != 'turn' or user_text:
                    raise ValueError('Восстановление принимает только сохранённый обычный ход.')
                recovery = db.execute('SELECT * FROM game_jobs WHERE id=? AND save_id=?', (source_id,save_id)).fetchone()
                if recovery is None or recovery['kind'] != 'turn' or not recovery['narrative_complete'] or not recovery['narrative'].strip():
                    raise ValueError('Нет завершённого исходного Narrative для восстановления.')
                source_before = json.loads(recovery['before_json'])
                current_before = json.loads(save['state_json'])
                if source_before['world_state']['meta']['turn_id'] != current_before['world_state']['meta']['turn_id']:
                    raise ValueError('Сначала откати цепочку к позиции исходного хода; повторное применение запрещено.')
                from hashlib import sha256
                config['_narrative_recovery'] = dict(source_job_id=source_id,
                    source_revision=recovery['revision'], source_contract=json.loads(recovery['config_json']).get('_extraction_contract',1),
                    narrative_sha256=sha256(recovery['narrative'].encode()).hexdigest())
                source_config = json.loads(recovery['config_json'])
                for key in ('interaction_channel','time_skip','_narrative_suggestions'):
                    config.pop(key, None)
                    if key in source_config: config[key] = source_config[key]
                user_text = recovery['user_text']
            if kind == 'communication':
                from backend.runtime_v3.communication import Continuation
                config = dict(config)
                command = config.pop('remote_command', None)
                command_created = False
                if command:
                    if command['action'] not in ('send', 'call'):
                        raise ValueError('Продолжение доступно для отправки сообщения или вызова.')
                    is_duplicate = any(e['operation_id']==command['operation_id'] for e in json.loads(save['state_json'])['world_state']['remote_events'].values())
                    if not is_duplicate and db.execute(f"SELECT 1 FROM game_jobs WHERE save_id=? AND revision=? AND {UNAPPLIED}", (save_id, save['revision'])).fetchone():
                        raise ValueError('Предыдущее действие ещё не обработано. Повтори обработку или отмени неудачный ход.')
                    # Command + registration are atomic; provider work happens after commit.
                    prior_revision = save['revision']
                    snap = self._remote_action(db, save_id, config.get('expected_revision'), command)
                    event = next(e for e in snap['world_state']['remote_events'].values() if e['operation_id'] == command['operation_id'])
                    config['communication'] = dict(source_event_id=event['id'], owner_id=event['sender_id'], request_id=command['operation_id'])
                    save = db.execute('SELECT * FROM saves WHERE id=?', (save_id,)).fetchone()
                    command_created = save['revision'] != prior_revision
                r = Continuation.model_validate(config.get('communication', {}))
                snap = json.loads(save['state_json'])
                if snap['world_state']['camera']['controlled_actor_id'] != r.owner_id:
                    raise ValueError('Владелец телефона изменился.')
                receipt = db.execute("""WITH RECURSIVE lineage(id,parent_id,payload_json) AS (
                    SELECT id,parent_id,payload_json FROM world_history_v3 WHERE id=?
                    UNION ALL SELECT h.id,h.parent_id,h.payload_json FROM world_history_v3 h JOIN lineage l ON h.id=l.parent_id)
                    SELECT j.value FROM lineage,json_each(lineage.payload_json,'$.state_changes') j
                    WHERE json_extract(j.value,'$.kind')='communication_receipt' AND json_extract(j.value,'$.request_id')=? LIMIT 1""", (snap.get('history_head'),r.request_id)).fetchone()
                if receipt:
                    previous_id = json.loads(receipt[0])['job_id']
                    previous = db.execute('SELECT config_json FROM game_jobs WHERE id=?',(previous_id,)).fetchone()
                    if not previous or json.loads(previous[0]).get('communication') != r.model_dump():
                        raise ValueError('ID продолжения уже использован с другими данными.')
                    raise ExistingJob(previous_id)
                existing = db.execute("SELECT id,config_json FROM game_jobs WHERE save_id=? AND revision=? AND kind='communication' ORDER BY rowid DESC", (save_id,save['revision'])).fetchall()
                for old in existing:
                    previous = json.loads(old['config_json']).get('communication', {})
                    if previous == r.model_dump():
                        raise ExistingJob(old['id'])
                    if previous.get('request_id') == r.request_id:
                        raise ValueError('ID продолжения уже использован с другими данными.')
                if command:
                    if not command_created:
                        raise ValueError('Исходный запрос уже обработан в другой ветке. Для нового ожидания используй явное продолжение связи.')
                    config['expected_revision'] = save['revision']
            self._assert_idle(db, save_id)
            if config.get('expected_revision', save['revision']) != save['revision']:
                raise ValueError('Сейв уже изменился. Обнови страницу перед следующим действием.')
            last = db.execute('SELECT * FROM turns WHERE save_id=? ORDER BY sequence DESC LIMIT 1', (save_id,)).fetchone()
            if kind == 'start' and last:
                raise ValueError('Игра уже начата.')
            if kind not in ('start','pov') and last is None:
                raise ValueError('Сначала начни игру.')
            pending=db.execute(f"SELECT 1 FROM game_jobs WHERE save_id=? AND revision=? AND {UNAPPLIED}", (save_id, save['revision'])).fetchone()
            if pending and kind!='regenerate':
                raise ValueError('Текст сцены уже сохранён, состояние ещё не применено. Повтори обработку состояния или отмени неудачный ход.')
            before, replaces = save['state_json'], None
            if kind=='pov':
                from backend.runtime_v3.camera import transition
                target=config.get('actor_id')
                source=config.get('source_turn_id')
                if source is not None and (not last or last['id']!=source or last['kind']!='background' or target not in json.loads(last['audience_json'])):
                    raise ValueError('Выбери участника последней закулисной сцены.')
                transition(json.loads(before),target)  # Validate before starting any paid request.
                config=dict(config,source_node_id=last['node_id'] if source is not None else None)
            context_json, memory_before = None, None
            if kind == 'regenerate':
                target = config.get('target_turn_id')
                if target is not None:
                    last = db.execute('SELECT * FROM turns WHERE id=? AND save_id=?', (target,save_id)).fetchone()
                    if not last:
                        raise ValueError('Исходный ход не найден.')
                    # Keep subsequent turns until a replacement commits successfully.
                    later = db.execute('SELECT 1 FROM turns WHERE save_id=? AND sequence>?', (save_id,last['sequence'])).fetchone()
                    if later and not config.get('rollback_following'):
                        raise ValueError('Подтверди откат последующих ходов.')
                v = db.execute('SELECT context_json,memory_before_json,job_id FROM response_variants WHERE id=?', (last['active_variant_id'],)).fetchone()
                context_json, memory_before = (v[0],v[1]) if v else (None,None)
                config['_extraction_contract'] = 1  # Recorded pre-version variants stay legacy.
                if v and v['job_id']:
                    original=db.execute('SELECT config_json FROM game_jobs WHERE id=?',(v['job_id'],)).fetchone()
                    if original:
                        config['_extraction_contract'] = json.loads(original[0]).get('_extraction_contract', 1)
                        config['_extraction_transport'] = json.loads(original[0]).get('_extraction_transport', 'chat_json_object')
                    if original and '_prompts' in json.loads(original[0]):
                        config=dict(config,_prompts=json.loads(original[0])['_prompts'])
                        for key in ('_context_selection','long_term_advance','communication','interaction_channel','time_skip','actor_id','source_turn_id','source_node_id','camera_actor_id','camera_scene_id','camera_direct'):
                            if key in json.loads(original[0]):config[key]=json.loads(original[0])[key]
                if context_json is None:
                    raise ValueError('У старого хода нет снимка исходного контекста. Точная перегенерация недоступна.')
                if EXTRACTION_VERSION >= 10 and last['kind'] in ('start','turn','pov','background'):
                    config['_extraction_contract'] = EXTRACTION_VERSION
                    config['_extraction_transport'] = transport(config)
                    config.get('_prompts',{}).pop('_scene_rules',None)
                before, replaces, user_text, kind = last['before_json'], last['id'], last['user_text'], last['kind']
            from backend.runtime_v3.models import assert_world_state_v3_invariants
            before_snapshot=json.loads(before)
            from backend.runtime_v3.repository import restore_biographical_secrets
            restore_biographical_secrets(db, before_snapshot)
            before_snapshot['world_state']=assert_world_state_v3_invariants(before_snapshot['world_state'])
            from backend.runtime_v3.protagonist import initialize
            initialize(before_snapshot)
            before=json.dumps(before_snapshot,ensure_ascii=False)
            validated_state = before_snapshot['world_state']
            if validated_state['meta'].get('protagonist_required') and replaces is None:
                raise ValueError('Главный герой умер. Выбери нового главного героя, чтобы продолжить.')
            if not json.loads(before)['world_state']['characters']:
                raise ValueError('В старом сохранении нет персонажей. Сначала подготовь мир для игры.')
            if kind == 'long_term':
                from backend.runtime_v3.long_term import plan
                plan(before_snapshot, config.get('long_term_advance', {}))
            if kind == 'communication':
                from backend.runtime_v3.communication import validate
                validate(before_snapshot, config.get('communication', {}))
            from backend.runtime_v3.camera import controlled
            if kind == 'turn' and controlled(json.loads(before)) is None and not config.get('time_skip'):
                raise ValueError('Камера наблюдает мир. Выбери персонажа для управления или продолжи наблюдение.')
            if kind == 'turn' and user_text.strip():
                from backend.runtime_v3.life import capabilities
                if not capabilities(validated_state,controlled(json.loads(before)))['can_act']:
                    raise ValueError('Персонаж сейчас не может действовать. Продолжи наблюдение или течение времени.')
            if kind == 'background':
                from backend.runtime_v3.camera import observe
                observe(json.loads(before),config.get('camera_actor_id'),config.get('camera_scene_id'),config.get('camera_direct',False))
            if kind == 'turn' and not user_text.strip() and not config.get('time_skip'):
                from backend.runtime_v3.life import capabilities
                if capabilities(validated_state,controlled(json.loads(before)))['can_act']:
                    raise ValueError('Напиши действие.')
            from backend.runtime_v3.camera import controlled
            config = dict(config)
            if kind == 'turn' and config.get('interaction_channel') == 'call':
                from backend.runtime_v3.remote import active_call
                call = active_call(validated_state, validated_state['camera']['controlled_actor_id'])
                if not call or call['status'] != 'answered':
                    raise ValueError('Нет соединённого звонка для телефонной реплики.')
            if '_prompts' not in config:
                config['_prompts'] = self.prompt_snapshot(db)
            if config['_extraction_contract'] >= 9 and '_scene_rules' not in config['_prompts']:
                from backend.repositories.documents import ROOT
                template = 'state_update_prompt.md' if config['_extraction_contract'] >= 10 else 'state_update_v9.md'
                config['_prompts']['_scene_rules'] = {'content':(ROOT/template).read_text(encoding='utf-8')}
            job_id = uuid.uuid4().hex
            db.execute('''INSERT INTO game_jobs(id,save_id,revision,before_json,user_text,kind,replaces_id,status,config_json)
                          VALUES(?,?,?,?,?,?,?,'generating',?)''',
                       (job_id, save_id, save['revision'], before, user_text, kind, replaces, json.dumps(config)))
            session_id = self.ensure_session(db, save_id)
            db.execute('UPDATE game_jobs SET context_json=?,memory_before_json=?,session_id=? WHERE id=?', (context_json,memory_before,session_id,job_id))
            db.execute('UPDATE game_jobs SET pov_actor_id=? WHERE id=?',(None if kind=='background' else config.get('actor_id') if kind=='pov' else controlled(json.loads(before)),job_id))
            if recovery is not None:
                db.execute("UPDATE game_jobs SET narrative=?,narrative_complete=1,status='extracting' WHERE id=?", (recovery['narrative'],job_id))
            if kind == 'communication':
                db.execute('UPDATE game_jobs SET narrative_complete=1 WHERE id=?',(job_id,))
        return job_id

    @staticmethod
    def _assert_idle(db, save_id):
        if db.execute("SELECT 1 FROM game_jobs WHERE save_id=? AND status IN ('generating','extracting','validating')", (save_id,)).fetchone():
            raise ValueError('Для этого прохождения уже выполняется ход.')

    def job_progress(self, job_id, status, narrative=None, complete=False, error=''):
        if status not in (*ACTIVE, 'error', 'stopped'):
            raise ValueError('Некорректный статус.')
        with self.connect() as db:
            db.execute("""UPDATE game_jobs SET status=?, narrative=COALESCE(?,narrative),
                        narrative_complete=MAX(narrative_complete,?), error=?
                        WHERE id=? AND status IN ('generating','extracting','validating') AND (? IS NULL OR attempt_epoch=?)""",
                       (status, narrative, int(complete), error, job_id, getattr(self,'worker_epoch',None),getattr(self,'worker_epoch',None)))

    def abandon_job(self, save_id, job_id, revision, attempt_epoch):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            job = db.execute("""SELECT j.status, j.revision, j.attempt_epoch, s.revision AS save_revision
                                FROM game_jobs j JOIN saves s ON s.id=j.save_id
                                WHERE j.save_id=? AND j.id=?""", (save_id, job_id)).fetchone()
            if not job:
                raise ValueError('Ход не найден в этом прохождении.')
            if job['revision'] != revision or job['attempt_epoch'] != attempt_epoch:
                raise ValueError('Попытка обработки изменилась. Обнови игру.')
            if job['status'] == 'abandoned':
                return
            if job['save_revision'] != revision:
                raise ValueError('Сейв изменился. Этот черновик устарел.')
            self._assert_idle(db, save_id)
            if job['status'] not in ('error', 'stopped'):
                raise ValueError('Отменить можно только неудачный или остановленный ход.')
            db.execute("UPDATE game_jobs SET status='abandoned' WHERE id=?", (job_id,))

    def correct_chronology_job(self, job_id, revision, attempt_epoch):
        """New candidate/lineage; the rejected job and accepted History stay intact."""
        from backend.services.world_delta_errors import prose_correction
        from hashlib import sha256
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM game_jobs WHERE id=?', (job_id,)).fetchone()
            if row is None:
                raise ValueError('Ход не найден.')
            job = dict(row)
            grounds = prose_correction(json.loads(job.get('repair_diagnostics_json') or '[]'), job['narrative'])
            if (job['status'] not in ('error', 'stopped') or not job['narrative_complete'] or
                    job['kind'] not in ('start', 'turn', 'regenerate', 'background', 'pov') or
                    not grounds or job['attempt_epoch'] != attempt_epoch or job['revision'] != revision):
                raise ValueError('Этот кандидат недоступен для адресной коррекции.')
            self._assert_idle(db, job['save_id'])
            save = db.execute('SELECT revision FROM saves WHERE id=?', (job['save_id'],)).fetchone()
            if save['revision'] != revision:
                raise ValueError('Сейв изменился. Этот черновик устарел.')
            if not job.get('context_json'):
                raise ValueError('Исходный контекст коррекции отсутствует.')
            config = json.loads(job['config_json'])
            config['_narrative_correction'] = dict(source_job_id=job_id,
                original=job['narrative'], original_sha256=sha256(job['narrative'].encode()).hexdigest(), grounds=grounds)
            new_id = uuid.uuid4().hex
            columns = ['save_id','revision','before_json','user_text','kind','replaces_id',
                       'context_json','memory_before_json','pov_actor_id','audience_json','session_id']
            db.execute('INSERT INTO game_jobs(id,status,config_json,'+','.join(columns)+') VALUES('+','.join('?' for _ in range(len(columns)+3))+')',
                [new_id, 'generating', json.dumps(config, ensure_ascii=False), *[job.get(k) for k in columns]])
            db.execute("UPDATE game_jobs SET status='abandoned' WHERE id=?", (job_id,))
        return new_id

    def retry_job(self, job_id, config=None, *, revision=None, attempt_epoch=None):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            job = db.execute('SELECT * FROM game_jobs WHERE id=?', (job_id,)).fetchone()
            if job is None or not job['narrative_complete'] or job['status'] not in ('error', 'stopped'):
                raise ValueError('Нет завершённого текста для повторной обработки.')
            if ((revision is not None and revision != job['revision']) or
                    (attempt_epoch is not None and attempt_epoch != job['attempt_epoch'])):
                raise ValueError('Запрос восстановления устарел. Обнови состояние игры.')
            from backend.services.world_delta_errors import requires_narrative_reauthor
            if requires_narrative_reauthor(json.loads(job['repair_diagnostics_json'] or '[]')):
                raise ValueError('Этот текст противоречит канону или выбору игрока. '
                                 'Отмените неудачный ход и создайте новую сцену.')
            self._assert_idle(db, job['save_id'])
            revision = db.execute('SELECT revision FROM saves WHERE id=?', (job['save_id'],)).fetchone()[0]
            settings = json.loads(job['config_json'])
            if revision != settings.get('_published_scene', {}).get('revision', job['revision']):
                raise ValueError('Сейв изменился. Этот черновик устарел.')
            previous_provider = (settings.get('provider','local'), settings.get('model'))
            if config:
                settings.update({k:v for k,v in config.items() if k not in ('target_turn_id','rollback_following','expected_revision','_prompts','_extraction_contract','_extraction_transport','actor_id','source_turn_id','source_node_id','communication','remote_command')})
            if settings.get('_extraction_contract',1) >= 6 and previous_provider != (settings.get('provider','local'),settings.get('model')):
                from backend.services.structured_extraction import transport
                settings['_extraction_transport'] = transport(settings)
            session_id = self.ensure_session(db, job['save_id'])
            db.execute("UPDATE game_jobs SET status='extracting',attempt_epoch=attempt_epoch+1,error='',warnings_json='[]',config_json=?,session_id=? WHERE id=?", (json.dumps(settings),session_id,job_id))

    def publish_scene(self, job_id, before, sequence, narrative, user_text, timing, *, recovery=None):
        """Publish the original text at its branch position before starting Extraction."""
        from copy import deepcopy
        from backend.runtime_v3.models import identity
        state = deepcopy(before)
        history = state.pop('_remote_batch', {})
        for key in ('_resolver_turn_id', '_time_skip', '_interaction_input_channel', 'last_time_skip'):
            state.pop(key, None)
        world = state['world_state']
        world['meta']['turn_id'] = sequence + 1
        minute = world['meta']['world_time']
        history.setdefault('turns', []).append(dict(id=identity('record',sequence+1,narrative,True),
            sequence=sequence, turn_id=sequence+1, narrative=narrative, player_input=user_text,
            camera_before=world['camera'], camera=world['camera'], game_time_before=minute,
            world_time=minute, player_observed=True))
        changes = {'interpretation':'pending' if recovery is None else 'deferred'}
        if recovery is not None:
            changes['interpretation_warnings'] = [dict(section='extraction',code='player_saved_prose',action='preserve_scene')]
        self.commit_job(job_id, state, [], changes, timing, history, publish=True, recovery=recovery)

    def save_completed_scene(self, job_id, revision, attempt_epoch):
        job = self.get_job(job_id)
        public = json.loads(job['config_json']).get('_published_scene')
        if (job['kind'] not in ('start','turn','pov','background') or not job['narrative_complete']
                or job['attempt_epoch'] != attempt_epoch or not job['narrative'].strip()):
            raise ValueError('Нет законченного текста этой попытки.')
        if public:
            if revision != public['revision'] and not (job['status']=='saved' and revision==job['revision']):
                raise ValueError('Опубликованный вариант изменился.')
            self.finish_interpretation(job_id,'player_saved_prose', recovery=(revision, attempt_epoch))
            return
        before = json.loads(job['memory_before_json'] or job['before_json'])
        camera = before['world_state']['camera']
        _, sequence = self.context_history(job['save_id'], job['replaces_id'], 1,
            camera.get('pov_actor_id') or camera.get('controlled_actor_id'), before.get('campaign',{}).get('protagonist_id'))
        self.publish_scene(job_id,before,sequence,job['narrative'],job['user_text'],None,
                           recovery=(revision,attempt_epoch))

    def finish_interpretation(self, job_id, reason, *, recovery=None):
        """Close interrupted optional work on the exact published variant, under the save fence."""
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            job = db.execute('SELECT * FROM game_jobs WHERE id=?',(job_id,)).fetchone()
            if recovery is None and (not job or job['status'] not in ACTIVE):
                return False
            if recovery is not None and job['status'] not in ('error','stopped','saved'):
                raise ValueError('Дождись завершения обработки.')
            if recovery is not None:
                self._assert_idle(db,job['save_id'])
                if job['attempt_epoch'] != recovery[1]:
                    raise ValueError('Попытка обработки изменилась.')
            publication = json.loads(job['config_json']).get('_published_scene')
            if not publication:
                return False
            self._published_turn(db, job, publication)
            if job['status'] == 'saved':
                return True
            warning = dict(section='extraction', code=reason, action='preserve_scene')
            turn = dict(db.execute('SELECT * FROM turns WHERE id=?',(publication['turn_id'],)).fetchone())
            changes = json.loads(turn['changes_json'])
            changes.update(interpretation='deferred', interpretation_warnings=[warning])
            turn['changes_json'] = json.dumps(changes, ensure_ascii=False)
            db.execute('UPDATE turns SET changes_json=? WHERE id=?',(turn['changes_json'],turn['id']))
            db.execute('UPDATE response_variants SET payload=? WHERE id=?',
                       (json.dumps(turn,ensure_ascii=False),publication['variant_id']))
            warnings = json.loads(job['warnings_json'] or '[]') + [warning]
            db.execute("UPDATE game_jobs SET status='saved', error='', warnings_json=? WHERE id=?",
                       (json.dumps(warnings,ensure_ascii=False),job_id))
            return True

    def _published_turn(self, db, job, publication):
        active = db.execute('SELECT active_variant_id FROM turns WHERE id=? AND save_id=?',
                            (publication['turn_id'],job['save_id'])).fetchone()
        revision = db.execute('SELECT revision FROM saves WHERE id=?',(job['save_id'],)).fetchone()[0]
        epoch = getattr(self,'worker_epoch',None)
        if (not active or active[0] != publication['variant_id'] or revision != publication['revision']
                or epoch is not None and epoch != job['attempt_epoch']):
            raise ValueError('Опубликованный вариант изменился. Обнови игру.')

    def commit_job(self, job_id, state, choices, changes, timing=None, history_batch=None, *, publish=False, recovery=None, audience=None):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            job = db.execute('SELECT * FROM game_jobs WHERE id=?', (job_id,)).fetchone()
            expected = ('error','stopped') if recovery is not None else ('extracting' if publish else 'validating',)
            if recovery is not None:
                self._assert_idle(db, job['save_id'])
                if (job['revision'],job['attempt_epoch']) != recovery:
                    raise ValueError('Сейв или попытка обработки изменились.')
            if job is None or job['status'] not in expected or (getattr(self,'worker_epoch',None) is not None and self.worker_epoch!=job['attempt_epoch']):
                raise ValueError('Ход остановлен или уже сохранён.')
            save = db.execute('SELECT revision FROM saves WHERE id=?', (job['save_id'],)).fetchone()
            publication = json.loads(job['config_json']).get('_published_scene')
            if publication:
                self._published_turn(db, job, publication)
                if publish:
                    return
            elif save['revision'] != job['revision']:
                raise ValueError('Состояние сейва изменилось во время генерации.')
            if job['replaces_id'] is not None and not publication:
                old = db.execute('SELECT * FROM turns WHERE id=? AND save_id=?', (job['replaces_id'], job['save_id'])).fetchone()
                if old is None:
                    raise ValueError('Исходный ход уже изменён.')
                db.execute('INSERT INTO archived_turns(save_id,reason,payload) VALUES(?,?,?)',
                           (job['save_id'], 'regenerate', json.dumps(dict(old), ensure_ascii=False)))
                self._rollback_after(db, job['save_id'], old['sequence'], json.loads(job['config_json']).get('rollback_following',False))
            sequence = publication['sequence'] if publication else old['sequence'] if job['replaces_id'] is not None else db.execute('SELECT COALESCE(MAX(sequence),-1)+1 FROM turns WHERE save_id=?', (job['save_id'],)).fetchone()[0]
            from backend.runtime_v3.models import assert_world_state_v3_invariants
            from backend.runtime_v3.repository import append_history
            assert_world_state_v3_invariants(state['world_state'],json.loads(job['before_json'])['world_state'])
            if history_batch is not None:
                state=dict(state,history_head=append_history(db,state.get('history_head'),history_batch, before=json.loads(job['before_json'])['world_state'], after=state['world_state']))
            from backend.runtime_v3.surfaces import committed_route
            changes = dict(changes, presentation=committed_route(dict(job), history_batch))
            if json.loads(job['config_json']).get('_extraction_contract', 1) >= 9:
                before_world = json.loads(job['before_json'])['world_state']
                after_world = state['world_state']
                changed = [cid for cid in before_world['characters'].keys() & after_world['characters'].keys()
                           if before_world['characters'][cid].get('situation') != after_world['characters'][cid].get('situation')]
                if before_world['camera'].get('situation') != after_world['camera'].get('situation'):
                    changed.append('camera')
                changes['context_situation_changes'] = sorted(changed)
            if publish:
                audience = state['world_state']['camera']['present_character_ids']
            if audience is not None:
                db.execute('UPDATE game_jobs SET audience_json=? WHERE id=?',(json.dumps(audience),job_id))
                job = db.execute('SELECT * FROM game_jobs WHERE id=?',(job_id,)).fetchone()
            after = json.dumps(state, ensure_ascii=False)
            values = (job['user_text'], job['narrative'], job['before_json'], after, job['kind'],
                      json.dumps(choices,ensure_ascii=False), json.dumps(changes,ensure_ascii=False))
            if publication or job['replaces_id'] is not None:
                tid = publication['turn_id'] if publication else old['id']
                db.execute('UPDATE turns SET user_text=?,assistant_text=?,before_json=?,after_json=?,kind=?,choices_json=?,changes_json=? WHERE id=?', (*values,tid))
            else:
                tid = db.execute('INSERT INTO turns(user_text,assistant_text,before_json,after_json,kind,choices_json,changes_json,save_id,sequence) VALUES(?,?,?,?,?,?,?,?,?)', (*values,job['save_id'],sequence)).lastrowid
            db.execute('UPDATE turns SET pov_actor_id=?,audience_json=?,timing_json=? WHERE id=?',(job['pov_actor_id'],job['audience_json'],json.dumps(timing) if timing else None,tid))
            record = dict(db.execute('SELECT * FROM turns WHERE id=?', (tid,)).fetchone())
            recovery_source = json.loads(job['config_json']).get('_narrative_recovery')
            if recovery_source and job['replaces_id'] is None:
                source = db.execute('SELECT * FROM response_variants WHERE job_id=? ORDER BY rowid DESC LIMIT 1',
                                    (recovery_source['source_job_id'],)).fetchone()
                parent = db.execute('SELECT active_variant_id FROM turns WHERE save_id=? AND sequence<? ORDER BY sequence DESC LIMIT 1',
                                    (job['save_id'], sequence)).fetchone()
                # A sibling may share a node only with the identical before and
                # parent. A corrected suffix has new parents and remains a new
                # branch with its explicit source-job provenance.
                if (source and source['parent_variant_id'] == (parent[0] if parent else None)
                        and json.loads(source['payload'])['before_json'] == job['before_json']):
                    record['node_id'] = source['node_id']
            if publication:
                db.execute('UPDATE response_variants SET payload=?,context_json=?,memory_before_json=? WHERE id=?',
                    (json.dumps(record, ensure_ascii=False), job['context_json'],job['memory_before_json'],publication['variant_id']))
            else:
                variant = self._variant(db, record, job_id, job['context_json'], job['memory_before_json'])
            if changes.get('interpretation_warnings'):
                warnings = json.loads(job['warnings_json'] or '[]') + changes['interpretation_warnings']
                db.execute('UPDATE game_jobs SET warnings_json=? WHERE id=?',(json.dumps(warnings,ensure_ascii=False),job_id))
            if publish:
                marker = dict(turn_id=tid,variant_id=variant,sequence=sequence,revision=save['revision']+1)
                db.execute("UPDATE game_jobs SET config_json=json_set(config_json,'$._published_scene',json(?)) WHERE id=?",
                           (json.dumps(marker), job_id))
            self._archive_memory(db, job['save_id'], state)
            db.execute("UPDATE saves SET state_json=?,revision=revision+1,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?", (after, job['save_id']))
            db.execute("UPDATE game_jobs SET status=?,error='',timing_json=? WHERE id=?",
                       ('extracting' if publish and recovery is None else 'saved', json.dumps(timing) if timing else None,job_id))

    def finalize_job_timing(self, job_id, total):
        """Persist elapsed wall-clock time after the save and variant are committed."""
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            job=db.execute('SELECT timing_json FROM game_jobs WHERE id=? AND status=\'saved\'',(job_id,)).fetchone()
            if not job or not job['timing_json']:return
            timing=json.loads(job['timing_json'])
            timing['total']=total
            encoded=json.dumps(timing)
            db.execute('UPDATE game_jobs SET timing_json=? WHERE id=?',(encoded,job_id))
            variant=db.execute('SELECT id,payload FROM response_variants WHERE job_id=? ORDER BY rowid DESC LIMIT 1',(job_id,)).fetchone()
            if variant:
                payload=json.loads(variant['payload'])
                payload['timing_json']=encoded
                db.execute('UPDATE response_variants SET payload=? WHERE id=?',(json.dumps(payload,ensure_ascii=False),variant['id']))
                db.execute('UPDATE turns SET timing_json=? WHERE active_variant_id=?',(encoded,variant['id']))

    def rollback_last(self, save_id, expected_revision=None):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._assert_idle(db, save_id)
            current = db.execute('SELECT revision FROM saves WHERE id=?', (save_id,)).fetchone()
            if expected_revision is not None and (current is None or current['revision'] != expected_revision):
                raise ValueError('Сейв изменился. Обнови страницу перед откатом.')
            last = db.execute('SELECT * FROM turns WHERE save_id=? ORDER BY sequence DESC LIMIT 1', (save_id,)).fetchone()
            if last is None:
                raise ValueError('Нет ходов для отката.')
            db.execute('INSERT INTO archived_turns(save_id,reason,payload) VALUES(?,?,?)', (save_id, 'rollback', json.dumps(dict(last), ensure_ascii=False)))
            db.execute('DELETE FROM turns WHERE id=?', (last['id'],))
            db.execute("UPDATE saves SET state_json=?,revision=revision+1,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?", (last['before_json'], save_id))
            self._archive_memory(db, save_id, json.loads(last['before_json']))
