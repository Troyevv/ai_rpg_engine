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


def test_existing_save_reports_recorded_and_fresh_contracts_without_story_or_credentials(game):
    from backend.runtime_v3.context import build_context
    from fastapi.testclient import TestClient
    from backend.api.app import create_app
    repo, sid = game
    hidden_value = 'private-story-marker'
    old_rows = [dict(text='Предложить тост ' + str(i)) for i in range(6)]
    current_rows = [dict(text='Поднять бокал', speech='За нас!'), dict(text='Поставить тарелку.', speech=None)]
    # Resume a job with the actual format header reported by the old installation.
    jid = repo.begin_job(sid, 'Осмотреться.', 'turn', dict(CONFIG))
    snap = repo.get_snapshot(sid)
    messages = build_context(snap, [], 'Осмотреться.', 'turn', 131072, 2400)
    current = next(m for m in messages if m['content'].startswith('Текущий ввод\n'))
    body = json.loads(current['content'].split('\n', 1)[1])
    body['response_format'] = 'JSON со сценой и вариантами Варианты от лица героя. После scene включи actions.'
    current['content'] = 'Текущий ввод\n' + json.dumps(body, ensure_ascii=False)
    messages[0]['content'] = messages[0]['content'].replace(narrative_frame.AUTHOR_FORMAT, 'Добавь шесть actions с text.')
    repo.save_context(jid, messages, snap)

    def finish(job, rows):
        def stream(**kwargs):
            stage = identity()['stage']
            if stage == 'narrative':
                yield json.dumps(dict(scene=hidden_value, actions=rows), ensure_ascii=False)
            elif stage == 'remote_initiative':
                yield '{"action":null}'
            else:
                yield '{}'
        with patch('engine.chat_stream', side_effect=stream):
            engine.run_job(repo.path, job, engine.Worker(epoch=0, api_key='test-private-provider-key'))
        assert repo.get_job(job)['status'] == 'saved'
        return repo.list_turns(sid)[-1]

    old = finish(jid, old_rows)
    new = finish(repo.begin_job(sid, 'Налить сок.', 'turn', dict(CONFIG)), current_rows)
    assert json.loads(old['choices_json']) == [dict(action=row['text'], speech='') for row in old_rows]
    with TestClient(create_app(repo.path)) as client:
        def audit(turn):
            res = client.get(f"/api/saves/{sid}/turns/{turn['id']}/choice-diagnostics",
                             params={'variant': turn['active_variant_id']})
            assert res.status_code == 200 and res.headers['cache-control'] == 'no-store'
            assert hidden_value not in res.text and 'test-private-provider-key' not in res.text and 'За нас!' not in res.text
            return res.json()
        previous, latest = audit(old), audit(new)
        assert previous['contract'] == 'narrative-actions/1'
        assert previous['raw']['missing'] == 6 and previous['saved_turn']['empty'] == 6
        assert latest['contract'] == client.get('/api/health').json()['choice_contract'] == 'narrative-actions/2'
        assert latest['raw']['null'] == 1
        assert latest['raw']['fields'] == {'text': 2, 'speech': 2}
        for stage in ('raw', 'checkpoint', 'published', 'saved_variant', 'saved_turn'):
            assert latest[stage]['rows'] == 2 and latest[stage]['spoken'] == 1
        assert latest['generating_build'] == client.get('/api/health').json()['backend_build']
        assert latest['same_saved_choices'] is True
        assert client.get(f"/api/saves/{sid}/turns/{old['id']}/choice-diagnostics",
                          params={'variant': new['active_variant_id']}).status_code == 409
        projection = client.get(f'/api/saves/{sid}').json()
        assert projection['physical_choice_source']['variant_id'] == new['active_variant_id']
        assert projection['turns'][-1]['choices'][0]['speech'] == 'За нас!'
        assert projection['turns'][-2]['choices'] == json.loads(old['choices_json'])
