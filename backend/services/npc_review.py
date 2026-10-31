"""Post-commit card review. Drafts belong to snapshots, never to canonical context.

The canonical card holds identity only until approval. The draft uses the same
card format and CARD_FIELDS as world authoring; it is not another Character.
"""
from copy import deepcopy
import json
import uuid
import threading
from contextlib import contextmanager

_generation_lock = threading.Lock()
_generating = set()


@contextmanager
def generation_guard(key):
    with _generation_lock:
        if key in _generating: raise ValueError("Генерация этого поля уже выполняется.")
        _generating.add(key)
    try: yield
    finally:
        with _generation_lock: _generating.discard(key)
from backend.services.world import CARD_FIELDS
from backend.runtime_v3.models import fatal, assert_world_state_v3_invariants


def card_fields(fields, *, complete=False):
    if not isinstance(fields, dict) or set(fields) - set(CARD_FIELDS) or any(not isinstance(v, str) for v in fields.values()):
        raise ValueError('Поля карточки должны быть строками из общей структуры CARD_FIELDS.')
    result = {key: fields.get(key, '') for key in CARD_FIELDS}
    if complete and any(not value.strip() for value in result.values()):
        raise ValueError('Заполни все 11 полей карточки.')
    return result


def promotion_card(item):
    try:
        if not isinstance(item, dict) or any(not isinstance(item.get(k), str) or not item[k].strip() for k in ('id', 'name')):
            raise ValueError('Нужны непустые ID и имя нового персонажа.')
        if not isinstance(item.get('evidence', ''), str):
            raise ValueError('Некорректный источник создания персонажа.')
        fields = card_fields(item.get('fields'))
        from backend.runtime_v3.npc_identity import initial_character
        initial_character(item['id'], item['name'], item.get('character', {}))
    except ValueError as exc:
        fatal(str(exc), 'promotion_invalid', repairable=True, section='promotions')
    return dict(id=item['id'], name=item['name'], fields=fields, aliases=[], is_player=False)


def identity_card(card):
    return dict(deepcopy(card), fields=dict.fromkeys(CARD_FIELDS, ''))


def review_projection(snapshot):
    actor = snapshot['world_state']['camera']['controlled_actor_id']
    records = []
    for cid, record in snapshot.get('pending_reviews', {}).items():
        if cid not in snapshot['world_state']['characters'] or actor not in record['audience_ids']:
            continue
        from backend.runtime_v3.npc_identity import editable_values
        from backend.runtime_v3.calendar import age_on, current_time, profile_of
        state=snapshot['world_state']
        records.append(dict(id=cid, age=age_on(state['characters'][cid]['birth_date'], current_time(state)['date'], profile_of(state)), character=deepcopy(record.get('character_edits', {})),
            baseline=deepcopy(record['character_baseline']), current=editable_values(snapshot['world_state']['characters'][cid]),
            **{key: deepcopy(record[key]) for key in
            ('card', 'status', 'revision', 'created_turn', 'creation_id', 'proposals', 'extracted_fields')}))
    from backend.runtime_v3.npc_identity import editor_schema
    return dict(fields=list(CARD_FIELDS), attributes=editor_schema(), records=records)


def review_record(snapshot, cid):
    record = snapshot.get('pending_reviews', {}).get(cid)
    actor = snapshot['world_state']['camera']['controlled_actor_id']
    if record is None or cid not in snapshot['world_state']['characters'] or actor not in record['audience_ids']:
        raise ValueError('Карточка недоступна в текущем прохождении и POV.')
    return record


def edit(repo, sid, cid, *, revision, review_revision, operation_id, fields, action='save', proposals=None, character=None):
    """Save, defer, or confirm under one lock and existing save revision guard.

    Operation receipts live in the same snapshot; retries cannot cross branches.
    Neither confirmation nor deferral rewrites turn/variant history snapshots.
    """
    from backend.runtime_v3.repository import append_history
    from backend.repositories.living_world import project
    fields = card_fields(fields, complete=action == 'confirm')
    if action not in ('save', 'defer', 'confirm'): raise ValueError('Неизвестное действие.')
    from backend.runtime_v3.npc_identity import validate_patch, apply_review
    character = validate_patch(cid, character or {})
    proposals = proposals or {}
    card_fields(proposals)
    signature = dict(fields=fields, proposals=proposals, character=character, action=action, review_revision=review_revision)
    with repo.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        repo._assert_idle(db, sid)
        row = db.execute('SELECT state_json,revision FROM saves WHERE id=?', (sid,)).fetchone()
        if row is None: raise ValueError('Прохождение не найдено.')
        snapshot = json.loads(row['state_json'])
        record = review_record(snapshot, cid)
        receipt = record.get('receipt')
        if receipt and receipt['id'] == operation_id:
            if receipt['request'] != signature: raise ValueError('ID запроса уже использован для другого изменения.')
            return
        if row['revision'] != revision or record['revision'] != review_revision:
            raise ValueError('Карточка или мир изменились. Обнови данные; твой текст сохранён в редакторе.')
        if record['status'] == 'confirmed': raise ValueError('Карточка уже подтверждена.')
        previous = deepcopy(record)
        record['card']['fields'] = fields
        record['proposals'] = deepcopy(proposals)
        record['character_edits'] = deepcopy(character)
        record['revision'] += 1
        record['status'] = {'save':'pending_review','defer':'deferred','confirm':'confirmed'}[action]
        record['receipt'] = dict(id=operation_id, request=signature)
        deferred = []
        if action == 'defer':
            owner = snapshot['world_state']['camera']['controlled_actor_id']
            for other_id, other in snapshot.get('pending_reviews', {}).items():
                if other_id != cid and owner in other['audience_ids'] and other['status'] == 'pending_review':
                    other['status'] = 'deferred'
                    other['revision'] += 1
                    deferred.append(other_id)
        canonical_before = deepcopy(snapshot['world_state']['characters'][cid])
        lifecycle_audit = {}
        if action == 'confirm':
            lifecycle_audit = apply_review(snapshot['world_state'], cid, character, record['character_baseline'])
            cards = [c for c in snapshot['character_cards'] if c['id'] == cid]
            if len(cards) != 1: raise ValueError('Нарушена уникальность канонической карточки.')
            cards[0]['fields'] = deepcopy(fields)
            # Initial descriptive data must not replace dynamic personality or appearance.
            from backend.runtime_v3.personality import initialize_profiles
            from backend.runtime_v3.models import Character
            actor = snapshot['world_state']['characters'][cid]
            baseline = dict(world_state=dict(characters={cid:Character(id=cid).model_dump()}), character_cards=cards)
            initialize_profiles(baseline)
            profile = baseline['world_state']['characters'][cid]['personality']
            if actor.get('personality') is None:
                actor['personality'] = profile
            else:
                existing_fields = {v['field'] for v in actor['personality']['items'].values()}
                if actor['personality']['applied']: existing_fields.update(profile['items'])
                for key, item in profile['items'].items():
                    if item['field'] not in existing_fields:
                        actor['personality']['items'][key] = item
            initialize_profiles(dict(world_state=snapshot['world_state'], character_cards=cards))
            # Confirmed descriptive data has one source of truth: character_cards.
            record['card'] = identity_card(record['card'])
            record['proposals'] = {}
        assert_world_state_v3_invariants(snapshot['world_state'])
        batch = lifecycle_audit or dict(state_changes=[])
        batch['state_changes'].append(dict(kind='npc_card_review', entity=cid, deferred_ids=deferred,
            turn_id=snapshot['world_state']['meta']['turn_id'], before=previous, after=deepcopy(record),
            character_before=canonical_before, character_after=deepcopy(snapshot['world_state']['characters'][cid])))
        snapshot['history_head'] = append_history(db, snapshot.get('history_head'), batch)
        project(db, sid, snapshot)
        db.execute('UPDATE saves SET state_json=?,revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=?',
                   (json.dumps(snapshot, ensure_ascii=False), sid))


def generate(repo, sid, cid, **kwargs):
    with generation_guard((str(repo.path), sid, cid, kwargs["field"])):
        return _generate(repo, sid, cid, **kwargs)


def _generate(repo, sid, cid, *, field, revision, review_revision, config, api_key):
    """A proposal can change only one field, never the world or accepted draft."""
    from backend.services.usage import tracked_stream
    from backend.services.coordinator import model_lease
    from backend.services.protagonist_creation import creation_context
    from context_builder import estimate
    import llm
    snapshot = repo.get_snapshot(sid)
    record = review_record(snapshot, cid)
    if field not in CARD_FIELDS or record['status'] == 'confirmed': raise ValueError('Поле недоступно.')
    if repo.get_save(sid)['revision'] != revision or record['revision'] != review_revision:
        raise ValueError('Контекст изменился. Сохрани карточку и повтори генерацию.')
    from backend.runtime_v3.npc_identity import editable_values
    messages = [dict(role='system', content='Ты дополняешь предложенную карточку уже существующего NPC. '
        'Верни JSON {"value":"текст"} только для выбранного поля, на русском. '
        'Черновик не является каноном. Не меняй личность, не принимай решений за игрока, '
        'не приписывай знания скрытых тайн. Учитывай установленные события и текущие сведения. '
        'Не генерируй другие поля.'), dict(role='user', content=json.dumps(dict(
            field=field, draft=record['card'], character=editable_values(snapshot['world_state']['characters'][cid]), context=creation_context(snapshot),
            situation=snapshot['world_state']['characters'][cid]['situation']), ensure_ascii=False))]
    budget = config['max_tokens']
    if estimate(messages) + budget > config['context_length']: raise ValueError('Недостаточно контекста для генерации поля.')
    class Accounting:
        def begin_request(self, jid, stage, cfg, msg, diag):
            return repo.begin_request(jid, stage, cfg, msg, diag, save_id=sid)
        def finish_request(self, *args, **kwargs): return repo.finish_request(*args, **kwargs)
    with model_lease(config['provider']):
        text = ''.join(tracked_stream(Accounting(), llm.chat_stream, uuid.uuid4().hex, 'npc_card_field', config, messages,
            model=config['model'], provider=config['provider'], api_key=api_key,
            temperature=config.get('temperature', 0.8), max_tokens=budget,
            require_complete=True, response_format={'type':'json_object'}))
    try:
        value = json.loads(text)
        if not isinstance(value, dict) or set(value) != {'value'} or not isinstance(value['value'], str) or not value['value'].strip(): raise ValueError()
    except (ValueError, TypeError): raise ValueError('Модель вернула некорректное предложение. Твой текст не изменён.')
    # Generation is read-only. Late responses are revision-bound and never auto-applied.
    return dict(field=field, value=value['value'], review_revision=review_revision, revision=revision)


def publish_cards(snapshot, resolved):
    """All turn materializers publish identities and reviews together."""
    snapshot['character_cards'].extend(deepcopy(resolved.cards))
    if resolved.pending_reviews:
        from backend.runtime_v3.npc_identity import editable_values
        for cid, record in resolved.pending_reviews.items():
            record['character_baseline'] = editable_values(snapshot['world_state']['characters'][cid])
            record['character_edits'] = {}
        snapshot.setdefault('pending_reviews', {}).update(deepcopy(resolved.pending_reviews))
