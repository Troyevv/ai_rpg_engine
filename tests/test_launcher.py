import json
from pathlib import Path
from unittest.mock import patch
import pytest
import launcher


def test_existing_server_does_not_reinstall_or_start_another(tmp_path,monkeypatch):
    monkeypatch.setattr(launcher,'RUNTIME',tmp_path)
    monkeypatch.setattr(launcher,'STATE',tmp_path/'server.json')
    launcher.STATE.write_text(json.dumps({'url':'http://127.0.0.1:8000','token':'private'}))
    with patch('launcher.request',return_value={'service':'ai-rpg-engine'}),patch('launcher.prepare') as prepare,patch('launcher.subprocess.Popen') as spawn:
        launcher.start(open_browser=False)
    prepare.assert_not_called();spawn.assert_not_called()


def test_stop_only_uses_control_token_for_own_server(tmp_path,monkeypatch):
    monkeypatch.setattr(launcher,'STATE',tmp_path/'server.json')
    launcher.STATE.write_text(json.dumps({'url':'http://127.0.0.1:8000','token':'private'}))
    with patch('launcher.request') as request:
        launcher.stop()
    request.assert_called_once_with('http://127.0.0.1:8000/api/_shutdown','private')
    assert not launcher.STATE.exists()


def test_wrong_server_identity_is_not_killed(tmp_path,monkeypatch):
    from urllib.error import HTTPError
    monkeypatch.setattr(launcher,'STATE',tmp_path/'server.json')
    launcher.STATE.write_text(json.dumps({'url':'http://127.0.0.1:8000','token':'private'}))
    with patch('launcher.request',side_effect=HTTPError('',403,'denied',{},None)):
        with pytest.raises(RuntimeError,match='identity'):
            launcher.stop()
    assert launcher.STATE.exists()


def test_frontend_hash_tracks_source_changes(tmp_path,monkeypatch):
    monkeypatch.setattr(launcher,'FRONTEND',tmp_path)
    (tmp_path/'src').mkdir();(tmp_path/'src/main.tsx').write_text('a')
    before=launcher.frontend_digest()
    (tmp_path/'src/main.tsx').write_text('b')
    assert before!=launcher.frontend_digest()
