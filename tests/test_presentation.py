"""Presentation must persist without changing any runtime state or LLM request."""
import pytest
from fastapi.testclient import TestClient
from backend.api.app import create_app
from backend.repositories.preparation import Repository
from backend.repositories.presentation import suggested_theme
from test_worlds import summary


def test_legacy_default_and_world_scoped_persistence(tmp_path):
    path = tmp_path / 'themes.sqlite3'
    app = create_app(path)
    repo = app.state.repository
    wid = repo.save_world('Вампиры', summary())
    other = repo.save_world('Другой мир', summary())
    sid = repo.create_save(wid, 'Первое')
    sid2 = repo.create_save(wid, 'Второе')
    before = repo.get_save(sid)
    source = repo.get_world(wid)
    with TestClient(app) as client:
        url = f'/api/worlds/{wid}/presentation'
        assert client.get(url).json() == {'theme_id':'graphite', 'mode':'manual'}
        assert client.put(url,json={'theme_id':'gothic'}).json()['theme_id'] == 'gothic'
        assert client.get(f'/api/worlds/{wid}').json()['presentation']['theme_id'] == 'gothic'
        for theme in ['graphite','gothic','parchment','noir','neon']:
            assert client.put(url,json={'theme_id':theme}).status_code == 200
        assert client.put(url,json={'theme_id':'arbitrary-css'}).status_code == 422
        assert client.put(url,json={'theme_id':'gothic','css':'bad'}).status_code == 422
        assert client.get(f'/api/worlds/{other}/presentation').json()['theme_id'] == 'graphite'
    assert Repository(path).get_presentation(wid)['theme_id'] == 'neon'
    assert repo.get_save(sid) == before
    assert repo.get_world(wid) == source
    assert repo.get_save(sid2)['state'] == before['state']
    with repo.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM llm_requests').fetchone()[0] == 0


def test_auto_is_resolved_once_even_after_manual_switch(tmp_path):
    repo = Repository(tmp_path / 'auto.sqlite3')
    wid = repo.save_world('Готика, вампиры', summary())
    assert repo.set_presentation(wid,'auto') == {'theme_id':'gothic','mode':'auto'}
    repo.set_presentation(wid,'neon')
    # Changing source metadata later must not change the previously resolved auto theme.
    with repo.connect() as db:
        db.execute('UPDATE worlds SET name=?,source_md=? WHERE id=?',('Киберпанк','sci-fi',wid))
    assert repo.set_presentation(wid,'auto')['theme_id'] == 'gothic'


@pytest.mark.parametrize('text,expected', [('Город друзей','graphite'),('Vampire horror','gothic'),('Средневековое фэнтези','parchment'),('Детектив нуар','noir'),('Научная фантастика','neon')])
def test_fixed_auto_rules(text, expected):
    assert suggested_theme(text) == expected


def test_missing_world_cannot_create_or_read_presentation(tmp_path):
    with TestClient(create_app(tmp_path/'missing.sqlite3')) as client:
        assert client.get('/api/worlds/999/presentation').status_code == 409
        assert client.put('/api/worlds/999/presentation',json={'theme_id':'auto'}).status_code == 409
