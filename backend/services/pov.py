"""Role and visibility policy independent of HTTP and the protagonist marker."""
from copy import deepcopy
import json


def protagonist(state):
    return state.get('protagonist_id') or next((c['id'] for c in state.get('characters',[]) if c.get('is_player')),None)


def controlled(state):
    return state.get('controlled_actor_id') or protagonist(state)


def visible(turn,actor,main):
    # Legacy ordinary scenes were written with the original protagonist's POV.
    audience=json.loads(turn.get('audience_json') or '[]')
    if audience:
        return actor in audience
    return turn.get('kind')!='background' and actor==(turn.get('pov_actor_id') or main)


def role_rules(state,kind,extraction=False):
    main,actor=protagonist(state),controlled(state)
    if kind=='background':
        return (f'\nТип хода: background. Запрещённые участники: protagonist_id={main}, controlled_actor_id={actor}. '
                'Они отсутствуют. choices должен быть пустым массивом. scene описывает ТОЛЬКО закулисную сцену. '
                'Не меняй их карточки, цели, планы и знания. Носители новых фактов и участники событий — только scene.present_ids. '
                'Отношения могут описывать отношение присутствующего NPC к отсутствующему, но не реакцию отсутствующего. '
                'Фиксация основной сцены будет сохранена движком отдельно.')
    return (f'\nРОЛИ ТЕКУЩЕГО ХОДА: protagonist_id={main}; controlled_actor_id={actor}. '
            f'Во всех общих правилах «ГГ/игрок» означает controlled_actor_id={actor}. '
            'Только этот персонаж защищён от решений ведущего: не пиши за него действия, реплики, мысли, чувства и решения. '
            'Разрешены последствия явно введённого игроком действия. Остальные персонажи, включая основной protagonist, '
            'действуют как NPC. Камера следует controlled_actor. choices — 6 действий controlled_actor. '
            'Не меняй его goal. Если переключение POV не сопровождалось переходом, не телепортируй других персонажей. '
            'Знания POV и объективные сведения ведущего разделены. Не раскрывай сведения из director_only как известные POV. '
            'Носителями нового знания могут быть только свидетели scene.present_ids; события вне их наблюдения не дают знания.')


def apply_scene_policy(before,after,changes,kind):
    main,actor=protagonist(before),controlled(before)
    after['protagonist_id'],after['controlled_actor_id']=main,actor
    scene=deepcopy(after['scene_meta'])
    audience=set(scene['present_ids'])
    if kind=='background':
        if audience.intersection({main,actor}):
            raise ValueError('Закулисная сцена включает основного или управляемого персонажа.')
        if not audience:
            raise ValueError('У закулисной сцены должны быть участники NPC.')
        protected={main,actor}
        for change in changes.get('characters',[]):
            if change['id'] in protected or change['id'] not in audience:
                raise ValueError('Закулисная сцена меняет отсутствующего персонажа.')
        for relation in changes.get('relationships',[]):
            if relation['source_id'] not in audience:
                raise ValueError('Нельзя приписать реакцию отсутствующему NPC.')
        after['last_background_scene']={'scene':after['scene'],'scene_meta':scene}
        after['scene']=before['scene']
        after['sections']['scene']=before['sections']['scene']
        after['scene_meta']=deepcopy(before.get('scene_meta',{}))
    for fact in changes.get('facts',[]):
        if not set(fact['known_by'])<=audience:
            raise ValueError('Новое знание передано отсутствующему персонажу.')
    for key in ('events','plans'):
        for entry in changes.get(key,[]):
            if kind=='background' and not set(entry['character_ids'])<=audience:
                raise ValueError('Событие закулисья приписано отсутствующему персонажу.')
    after.setdefault('world_clock',{})['last_event_time']=scene['time']
    after.setdefault('actor_scenes',{})
    for cid in audience:
        after['actor_scenes'][cid]={'text': changes['scene']['text'],'meta':deepcopy(scene)}
    return after, sorted(audience|({actor} if kind!='background' else set()))


def actor_view(turn,actor,main):
    """Other viewpoints expose only explicitly attributed knowledge, not private prose."""
    if turn.get('kind')!='background' and actor==(turn.get('pov_actor_id') or main):
        return turn
    changes=json.loads(turn.get('changes_json') or '{}')
    facts=[f['text'] for f in changes.get('facts',[]) if actor in f.get('known_by',[])]
    return {**turn,'user_text':'','assistant_text':'Доступные персонажу факты:\n'+'\n'.join(facts)}
