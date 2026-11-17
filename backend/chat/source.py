"""Read-only, explicit initial projection. Never consulted again during Chat turns."""
import hashlib
import json

from backend.chat.context import TEMPLATE
from backend.chat.repository import uid, dump


def preview(storage, source):
    if (source.save_id is None) == (source.world_id is None):
        raise ValueError('Выберите один мир или одно принятое прохождение.')
    if source.save_id is not None:
        with storage.connect() as db:
            saved = db.execute('SELECT * FROM saves WHERE id=?', (source.save_id,)).fetchone()
            if not saved: raise ValueError('Прохождение не найдено.')
            if source.revision != saved['revision']: raise ValueError('Narrative изменился. Обновите исходное прохождение.')
            snapshot = json.loads(saved['state_json'])
            turns = [dict(t) for t in db.execute('''SELECT id,sequence,user_text,assistant_text,active_variant_id
                FROM turns WHERE save_id=? ORDER BY sequence DESC LIMIT ?''', (source.save_id,source.history_turns))][::-1]
        from backend.runtime_v3.selectors import ui_view
        state = ui_view(snapshot)
        state['campaign'] = snapshot.get('campaign', {})
        state['campaign'].setdefault('title', saved['name'])
        # Existing human-readable projection. Supplement author facts/knowledge explicitly,
        # rather than presenting POV-hidden material as public knowledge.
        from backend.services.draft_world import export_markdown
        text = export_markdown(state, readable_text=True)
        canonical = snapshot['world_state']
        names = {c['id']:c['name'] for c in snapshot['character_cards']}
        text += '\n\nАВТОРСКИЕ ФАКТЫ И ЗНАНИЯ (могут содержать спойлеры)\n'
        for fid, fact in canonical['facts'].items():
            text += '\n' + fact['text'] + '\n'
            for known in canonical['knowledge'].values():
                if known['fact_id']==fid:
                    text += f"- {names.get(known['actor_id'],known['actor_id'])}: {known['status']}\n"
        text += '\n\nСОГЛАСОВАННЫЙ ФРАГМЕНТ ПРИНЯТОЙ ИСТОРИИ (уже произошёл)\n'
        for turn in turns:
            text += '\nИгрок: '+turn['user_text']+'\nИстория: '+turn['assistant_text']+'\n'
        origin = dict(mode='narrative',save_id=source.save_id,revision=saved['revision'],
                      history_head=snapshot.get('history_head'),turns=turns,
                      snapshot_sha256=hashlib.sha256(saved['state_json'].encode()).hexdigest())
    else:
        world = storage.get_world(source.world_id)
        from backend.services.draft_world import export_markdown, prepare
        text = export_markdown(prepare(world['state']), readable_text=True)
        origin = dict(mode='world',world_id=source.world_id,version=world['version'],snapshot_sha256=world['digest'])
    text = TEMPLATE + '\n\nИСХОДНЫЙ СНИМОК — проверьте и распределите по полям; неизвестное можно оставить пустым.\n\n' + text
    ident = uid()
    with storage.connect() as db:
        db.execute('INSERT INTO chat_sources VALUES(?,?,?)', (ident,text,dump(origin)))
    return dict(id=ident,memory=text,origin=origin)
