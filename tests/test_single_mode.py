"""Upgrade boundaries for installations created before #125."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from pathlib import Path
import sqlite3

import pytest

from backend.runtime_v3.migration import migrate_v2
from storage import Storage
from test_api import api
from test_worlds import summary


def test_removed_api_and_incompatible_import(api):
    client, app = api
    assert all('/tabletop' not in path for path in app.openapi()['paths'])
    assert client.get('/api/tabletop/games').status_code == 404
    # FastAPI's GET-only SPA fallback returns 405 for any unknown POST.
    assert client.post('/api/tabletop/games', json={}).status_code == 405
    campaign = dict(schema_version=2, campaign={'name': 'Old'}, ruleset={'id': 'd20-basic-v2'},
                    world={'name': 'Old'}, characters={'hero': {}}, party=['hero'])
    with pytest.raises(ValueError):
        migrate_v2(campaign)
    workspace = client.post('/api/workspaces', json={'name': 'Import'}).json()
    url = f"/api/workspaces/{workspace['id']}/draft"
    before = client.get(url).json()
    response = client.post(url + '/import', json=dict(
        format='json', text=json.dumps(campaign), revision=before['revision']))
    assert 400 <= response.status_code < 500
    assert client.get(url).json() == before


def test_mixed_database_backup_includes_wal_and_history(tmp_path):
    path = tmp_path / 'game.sqlite3'
    repo = Storage(path)
    wid = repo.save_world('Narrative', summary())
    sid = repo.create_save(wid, 'История')
    snapshot = repo.get_snapshot(sid)
    assert not list(tmp_path.glob('*.bak'))

    # Keep the original connection open: committed pages still live in the WAL.
    with closing(sqlite3.connect(path)) as old:
        old.execute('PRAGMA journal_mode=WAL')
        old.execute('PRAGMA wal_autocheckpoint=0')
        old.executescript("""
            CREATE TABLE tabletop_games(id INTEGER PRIMARY KEY, state_json TEXT);
            CREATE TABLE tabletop_history(game_id REFERENCES tabletop_games, before_json TEXT);
            CREATE TABLE tabletop_settings(id TEXT);
            CREATE TABLE tabletop_migrations(original_json TEXT);
            CREATE TABLE tabletop_requests(payload TEXT);
            CREATE TABLE tabletop_drafts(definition_json TEXT);
            CREATE INDEX old_history_index ON tabletop_history(game_id);
            CREATE TRIGGER old_history_trigger AFTER INSERT ON tabletop_history
                BEGIN INSERT INTO tabletop_requests VALUES ('roll'); END;
            INSERT INTO tabletop_games VALUES (1,'campaign');
            INSERT INTO tabletop_history VALUES (1,'turn');
            INSERT INTO tabletop_drafts VALUES ('draft');
            INSERT INTO tabletop_settings VALUES ('settings');
            INSERT INTO tabletop_migrations VALUES ('original');
        """)
        original = list(old.iterdump())
        assert Path(str(path) + '-wal').stat().st_size > 0
        with ThreadPoolExecutor(max_workers=2) as workers:
            list(workers.map(Storage, [path, path]))
        assert not old.execute("SELECT name FROM sqlite_master WHERE name GLOB 'tabletop_*'").fetchall()
        assert not old.execute("SELECT name FROM sqlite_master WHERE name LIKE 'old_history_%'").fetchall()
        with closing(sqlite3.connect(next(tmp_path.glob('*.bak')))) as restored:
            assert list(restored.iterdump()) == original
        # Every surviving Narrative row, including historical JSON, is byte-identical.
        retained = [line for line in original if 'tabletop_' not in line and 'old_history_' not in line]
        assert list(old.iterdump()) == retained
    assert Storage(path).get_snapshot(sid) == snapshot
    assert len(list(tmp_path.glob('*.bak'))) == 1


def test_backup_validation_failure_preserves_source(tmp_path, monkeypatch):
    path = tmp_path / 'legacy.sqlite3'
    with closing(sqlite3.connect(path)) as db:
        db.executescript("CREATE TABLE tabletop_drafts(payload); INSERT INTO tabletop_drafts VALUES ('draft');")
        original = list(db.iterdump())
    connect = sqlite3.connect

    def unreadable_backup(database, *args, **kwargs):
        if kwargs.get('uri') and str(database).endswith('?mode=ro'):
            raise sqlite3.DatabaseError('cannot reopen backup')
        return connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, 'connect', unreadable_backup)
    with pytest.raises(sqlite3.DatabaseError, match='cannot reopen backup'):
        Storage(path)
    with closing(connect(path)) as db:
        assert list(db.iterdump()) == original
    assert not list(tmp_path.glob('*.bak'))
    assert not list(tmp_path.glob('*.pending'))


def test_unknown_foreign_key_cannot_cascade_into_surviving_data(tmp_path):
    path = tmp_path / 'extended.db'
    with closing(sqlite3.connect(path)) as db:
        db.executescript("""
            CREATE TABLE tabletop_games(id INTEGER PRIMARY KEY);
            CREATE TABLE extension(game_id REFERENCES tabletop_games ON DELETE CASCADE);
            INSERT INTO tabletop_games VALUES (1);
            INSERT INTO extension VALUES (1);
        """)
        original = list(db.iterdump())
    with pytest.raises(sqlite3.DatabaseError, match='extension'):
        Storage(path)
    with closing(sqlite3.connect(path)) as db:
        assert list(db.iterdump()) == original
