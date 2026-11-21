"""Six authoring situations, from Narrative input through publication and the next turn."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

import engine
from backend.runtime_v3 import narrative_frame
from backend.services.provider_attempt import identity
from test_milestones import snapshot
from test_published_narrative263 import CONFIG, game

pytestmark = pytest.mark.extraction_current

# Synthetic scenes, also usable with the regular Narrative provider in an opt-in review.
# The six response fixtures are recorded from deepseek-flash with these inputs.
# Replaying them here exercises the engine without network or model credentials.
SCENES = [
    ('friends', ['Илья', 'Соня'], 'Кухня', 'Друзья детства. Перед тостом Соня прячет листок под бокалом.',
     'Добродушно подшучивает, говорит коротко.', 'Придвигаю пустой бокал.'),
    ('romance', ['Ася', 'Нина'], 'Платформа', 'Они давно близки. Поезд Нины задерживается; обе стоят под одним зонтом.',
     'Смущается громких признаний, замечает мелочи.', 'Перехватываю ручку зонта.'),
    ('disagreement', ['Вера', 'Лев'], 'Редакция', 'Редактор Лев убрал имя Веры из подписи к её снимку. На столе лежит корректура.',
     'Фотограф. Упряма, требует точных ответов.', 'Кладу корректуру на стол.'),
    ('repair', ['Мила', 'Игорь'], 'Мастерская', 'Они чинят протекающий сифон. Вода капает в таз, новая прокладка лежит на полке.',
     'Опытная мастерица, спокойна и экономна в словах.', 'Пододвигаю таз под стык.'),
    ('ensemble', ['Тимур', 'Соня', 'Мёрфи'], 'Веранда', 'Друзья разбирают выцветшие фотографии. Соня узнаёт дом, Мёрфи подписывает конверты.',
     'Любит задавать неожиданные вопросы друзьям.', 'Переворачиваю верхний снимок.'),
    ('silent', ['Лада'], 'Фотолаборатория', 'Лада одна в тёмной комнате. В первой ванночке проявляется снимок. Таймер остановлен.',
     'Внимательная лаборантка. Обычно работает в тишине.', 'Наклоняюсь над ванночкой.'),
]


def scene_snapshot(case):
    _, names, place, situation, voice, _ = case
    snap = snapshot()
    world = snap['world_state']
    actors = list('abc'[:len(names)])
    for card, name in zip(snap['character_cards'], names):
        actor = world['characters'][card['id']]
        actor.update(display_name=name, location_id='home')
        card.update(name=name, fields={'Стиль общения': voice} if card['id'] == 'a' else {})
    world['camera'].update(present_character_ids=actors, situation=situation)
    world['locations']['home'].update(name=place, description=situation)
    return snap


@pytest.mark.parametrize('case', SCENES, ids=[row[0] for row in SCENES])
def test_authored_options_survive_publication_reload_and_next_input(game, case):
    repo, sid = game
    snap = scene_snapshot(case)
    snap['history_head'] = repo.get_snapshot(sid)['history_head']
    with repo.connect() as db:
        db.execute('UPDATE saves SET state_json=? WHERE id=?', (json.dumps(snap), sid))
    label, _, _, _, _, player_input = case
    wire = json.loads((Path(__file__).parent / 'fixtures' / 'choice_speech' / (label + '.json')).read_text())
    expected = [dict(action=row['text'], speech=row['speech'] or '') for row in wire['actions']]
    assert len(expected) == 6
    # Publication and final interpretation run in separate transactions.
    def run(text):
        stages = []
        def stream(**kwargs):
            stage = identity()['stage']
            stages.append(stage)
            if stage == 'narrative':
                messages = kwargs['messages']
                assert narrative_frame.explicit_speech(messages)
                assert narrative_frame.CHOICE_CONTRACT in messages[0]['content']
                current = next(m for m in messages if m['content'].startswith('Текущий ввод\n'))
                assert json.loads(current['content'].split('\n', 1)[1])['player_input'] == text
                yield json.dumps(wire, ensure_ascii=False)
            elif stage == 'extraction':
                assert json.loads(repo.list_turns(sid)[-1]['choices_json']) == expected
                yield '{}'
            elif stage == 'remote_initiative':
                yield '{"action":null}'
            else:
                pytest.fail(stage)
        jid = repo.begin_job(sid, text, 'turn', dict(CONFIG))
        with patch('engine.chat_stream', side_effect=stream):
            engine.run_job(repo.path, jid, engine.Worker(epoch=0, api_key='offline'))
        result = repo.get_job(jid)
        assert result['status'] == 'saved', result['error']
        assert stages.count('narrative') == 1
        assert stages.count('extraction') == 1
        return json.loads(type(repo)(repo.path).list_turns(sid)[-1]['choices_json'])
    saved = run(player_input)
    assert saved == expected
    first = next(row for row in saved if bool(row['speech']) == (label != 'silent'))
    chosen = first['action']
    if first['speech']:
        chosen += ': «' + first['speech'] + '»'
    assert run(chosen) == expected


def test_explicit_speech_validates_shape_without_editing_authored_words():
    world = scene_snapshot(SCENES[0])['world_state']
    words = 'Сонь…  Слышишь?\nЯ здесь. '
    frame = dict(actions=[dict(text='Окликнуть Соню', speech=words),
                          dict(text='Подойти.', speech=None), dict(text='Старый вариант'),
                          dict(text='Пустая строка', speech='  '), dict(text='Не строка', speech=True)])
    wire = json.dumps(dict(scene='Тихо.', **frame))
    def decode(fmt):
        recorded = [dict(content='Текущий ввод\n' + json.dumps(dict(response_format=fmt)))]
        return narrative_frame.recorded_reply(wire, recorded)[1]
    choices, warnings = narrative_frame.menu(decode(narrative_frame.EXPLICIT_FORMAT), world)
    assert choices == [dict(action='Окликнуть Соню', speech=words), dict(action='Подойти.', speech='')]
    assert warnings[0]['available'] == 2
    legacy, _ = narrative_frame.menu(decode(narrative_frame.FORMAT), world)
    assert dict(action='Старый вариант', speech='') in legacy
