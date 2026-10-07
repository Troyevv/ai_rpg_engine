"""Request-local behavioral participation, independent of presence and similarity."""
import re


def authored_request(text):
    return bool(re.search(r'(?:прочита|читать|читаю|перечит|откр|прослуш|послуш|слушаю|посмотр|смотрю|вспомн|вспомина|покаж|показать|read|open|listen|recall|show)', text, re.I)
                and re.search(r'(?:сообщени|письм|голосов|запис|слов|сказал|реплик|диалог|message|letter|voicemail|said)', text, re.I))


def active_actors(snapshot, user_text, names, recent_views, history):
    from backend.runtime_v3.scope import mentions
    state = snapshot['world_state']; actors = set(state['characters'])
    # Runtime simulation metadata is an explicit request to model these actors.
    active = set(snapshot.get('_background_actor_ids', [])) & actors
    offscreen = bool(re.search(r'(?:покажи|показать|опиши|описать|show).*?(?:делает|действует|реагирует|за кадром|вне сцены)', user_text, re.I))
    if not authored_request(user_text) and not offscreen: return active
    explicit = {cid for cid, aliases in names.items() if mentions(user_text, aliases)}
    if explicit: return active | explicit
    # Prefer an actual author, never infer authorship from all event participants.
    now = state['meta']['turn_id']
    for event in reversed((history or {}).get('events', [])):
        if not isinstance(event, dict): continue
        if event.get('medium') != 'message' or event.get('author_id') not in actors: continue
        if event.get('turn_id') not in (now, now-1, now-2): continue
        pov = state['camera']['controlled_actor_id']
        if pov and pov not in event.get('witnesses', []): continue
        return active | {event['author_id']}
    # Compatibility for old narrative without authored Event metadata: only a
    # named communication in latest visible continuity, not any mentioned actor.
    latest = recent_views[-1].get('assistant_text', '') if recent_views else ''
    for clause in re.split(r'[.!?\n]', latest):
        if re.search(r'(?:сообщение|письмо|голосовое|запись)\s+(?:от\s+)?', clause, re.I):
            matched = {cid for cid, aliases in names.items() if mentions(clause, aliases)}
            if len(matched) == 1: active |= matched
    return active
