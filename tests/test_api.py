from canonical_fixture import canonical, fixture_sequence
import json
import sqlite3
import threading
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from backend.api.app import create_app
from backend.repositories.preparation import Repository
from test_worlds import summary
from test_engine import CONFIG, NARRATIVE, result

REMOTE = {**CONFIG, 'provider': 'deepseek', 'model': 'deepseek-flash'}

@pytest.fixture
def api(tmp_path):
    app = create_app(tmp_path / 'api.sqlite3')
    with TestClient(app) as client:
        yield client, app


def wait_job(client, jid):
    for _ in range(200):
        job = client.get('/api/jobs/' + jid).json()
        if job['status'] not in ('generating', 'extracting', 'validating'):
            return job
        time.sleep(.01)
    raise AssertionError('job timed out')


def new_save(client):
    world = client.post('/api/worlds', json={'name':'Мир', 'markdown':summary()}).json()
    save = client.post(f"/api/worlds/{world['id']}/saves", json={'name':'Игра'}).json()
    return world, save


def test_preparation_to_game_parity(api):
    client, app = api
    workspace = client.post('/api/workspaces', json={'name':'Новая история'}).json()
    with patch('backend.services.preparation.chat_stream', return_value=iter(['Сценарий про друзей.'])):
        response = client.post(f"/api/workspaces/{workspace['id']}/generate", json={'kind':'idea','text':'Город и друзья','revision':0,'config':REMOTE,'api_key':'test-secret'})
        assert response.status_code == 200
        assert wait_job(client,response.json()['id'])['status'] == 'saved'
    workspace = client.get(f"/api/workspaces/{workspace['id']}").json()
    assert workspace['idea'] == 'Сценарий про друзей.'
    assert workspace['messages'] == [{'role':'user','content':'Город и друзья'}]
    with patch('backend.services.preparation.chat_stream', return_value=iter([summary()])):
        job = client.post(f"/api/workspaces/{workspace['id']}/generate", json={'kind':'summary','revision':workspace['revision'],'config':REMOTE,'api_key':'test-secret'}).json()
        assert wait_job(client,job['id'])['status'] == 'saved'
    world = client.post(f"/api/workspaces/{workspace['id']}/world", json={'name':'Новая история'}).json()
    save = client.post(f"/api/worlds/{world['id']}/saves",json={'name':'Первое'}).json()
    def stream(**kw):
        yield json.dumps(canonical(result(),len(app.state.repository.list_turns(save['id']))),ensure_ascii=False) if kw.get('response_format') else NARRATIVE
    with patch('engine.chat_stream',side_effect=stream),patch('engine.find_loaded_model',side_effect=AssertionError('LM Studio not needed')):
        j=client.post(f"/api/saves/{save['id']}/turns",json={'kind':'start','revision':0,'config':REMOTE,'api_key':'test-secret'}).json()
        assert wait_job(client,j['id'])['status']=='saved'
        save=client.get(f"/api/saves/{save['id']}").json()
        assert len(save['turns'][0]['choices'])==6
        j=client.post(f"/api/saves/{save['id']}/turns",json={'kind':'turn','text':'Сесть рядом','revision':save['revision'],'config':REMOTE,'api_key':'test-secret'}).json()
        assert wait_job(client,j['id'])['status']=='saved'
    current=client.get(f"/api/saves/{save['id']}").json()
    assert current['turns'][-1]['user_text']=='Сесть рядом'
    assert client.post(f"/api/saves/{save['id']}/rollback",json={'revision':0}).status_code==409
    assert client.post(f"/api/saves/{save['id']}/rollback",json={'revision':current['revision']}).status_code==200
    with app.state.repository.connect() as db:
        assert 'test-secret' not in '\n'.join(db.iterdump())
    # Replay/reconnect yields current complete snapshot, never duplicate text fragments.
    stream=client.get(f"/api/jobs/{j['id']}/events")
    assert stream.headers['content-type'].startswith('text/event-stream')
    assert stream.text.count('event: snapshot')==1
    assert json.loads(stream.text.split('data: ')[1])['narrative']==NARRATIVE


def test_stop_preparation_blocks_late_result_and_stale_reset(api):
    client, app = api
    entered, release = threading.Event(), threading.Event()
    def stream(**kw):
        yield 'Частичный текст'
        entered.set(); release.wait(5)
        yield ' ПОЗДНИЙ ТЕКСТ'
    wid=client.post('/api/workspaces',json={'name':'Тест'}).json()['id']
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        j=client.post(f'/api/workspaces/{wid}/generate',json={'kind':'idea','text':'Идея','revision':0,'config':REMOTE,'api_key':'secret'}).json()
        assert entered.wait(2)
        assert client.post(f"/api/jobs/{j['id']}/stop").status_code==200
        release.set()
        w=client.get(f'/api/workspaces/{wid}').json()
        assert w['idea']=='Частичный текст'
        assert not w['summary_complete']
        assert client.post(f'/api/workspaces/{wid}/world',json={'name':'Черновик'}).status_code==409
        assert client.post(f'/api/workspaces/{wid}/reset',json={'revision':0}).status_code==409
        assert client.post(f'/api/workspaces/{wid}/reset',json={'revision':w['revision']}).status_code==200


def test_api_validation_does_not_echo_credentials(api):
    c,_=api
    r=c.post('/api/models/list',json={'provider':'unknown','api_key':'DO-NOT-ECHO'})
    assert r.status_code==422 and 'DO-NOT-ECHO' not in r.text
    assert c.post('/api/workspaces',json={'name':'World'},headers={'Origin':'https://evil.example'}).status_code==403
    assert c.get('/api/nonexistent').status_code==404
    assert c.post('/api/_shutdown').status_code==403


def test_scene_and_safe_character_links(api):
    c,_=api
    w,s=new_save(c)
    assert c.patch(f"/api/saves/{s['id']}/scene",json={'time':'20:00','location':'Двор','present_ids':['missing'],'revision':0}).status_code==409
    assert c.patch(f"/api/saves/{s['id']}/scene",json={'time':'20:00','location':'Двор','present_ids':['character_2'],'revision':0}).status_code==200
    assert c.patch(f"/api/saves/{s['id']}/scene",json={'time':'21:00','location':'Двор','present_ids':[],'revision':0}).status_code==409
    html=c.post('/api/markdown',json={'text':'Персонаж 1 <script>alert(1)</script>','save_id':s['id']}).json()['html']
    assert 'data-character-id="character_2"' in html and '<script>' not in html
    assert c.get(f"/api/worlds/{w['id']}").json()['state']==w['state']


def test_existing_database_keeps_old_json(tmp_path):
    path=tmp_path/'old.sqlite3'
    from world_parser import parse_summary
    state=parse_summary(summary());state['characters']=state['characters'][:7]
    original=json.dumps(state,ensure_ascii=False)
    with sqlite3.connect(path) as db:
        db.executescript('''CREATE TABLE worlds(id INTEGER PRIMARY KEY,name TEXT NOT NULL,name_key TEXT NOT NULL,version INTEGER NOT NULL,source_md TEXT NOT NULL,digest TEXT NOT NULL,created_at TEXT DEFAULT 'old',UNIQUE(name_key,version),UNIQUE(name_key,digest));
        CREATE TABLE world_parts(world_id INTEGER,kind TEXT,payload TEXT,PRIMARY KEY(world_id,kind));
        CREATE TABLE saves(id INTEGER PRIMARY KEY,world_id INTEGER,name TEXT,state_json TEXT,created_at TEXT DEFAULT 'old',updated_at TEXT DEFAULT 'old');
        CREATE TABLE turns(id INTEGER PRIMARY KEY,save_id INTEGER,sequence INTEGER,user_text TEXT,assistant_text TEXT,before_json TEXT,after_json TEXT,UNIQUE(save_id,sequence));''')
        db.execute("INSERT INTO worlds(id,name,name_key,version,source_md,digest) VALUES(1,'Old','old',1,'markdown','hash')")
        db.execute("INSERT INTO saves(id,world_id,name,state_json) VALUES(1,1,'Old save',?)",(original,))
        db.execute("INSERT INTO turns VALUES(1,1,0,'','Старая сцена',?,?)",(original,original))
    for _ in range(2):
        repo=Repository(path)
        assert all(repo.get_save(1)['state'][key]==value for key,value in state.items())
        assert repo.get_save(1)['state']['world']['version']==2
        assert repo.list_turns(1)[0]['assistant_text']=='Старая сцена'
    with repo.connect() as db:
        assert db.execute('SELECT before_json FROM turns').fetchone()[0]==original
        assert db.execute('SELECT after_json FROM turns').fetchone()[0]==original
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]


def test_local_model_management_and_lock(api):
    c,_=api
    from backend.services.coordinator import LOCAL_MODEL_LOCK
    with patch('llm.get_available_models',return_value=['local']),patch('llm.get_loaded_models',return_value=[]),patch('llm.load_model') as load,patch('llm.unload_all_models'):
        assert c.post('/api/models/list',json={'provider':'local'}).json()['models']==['local']
        assert c.post('/api/models/load',json={'model':'local','context_length':32768,'eval_batch_size':1024,'flash_attention':False,'offload_kv_cache_to_gpu':False}).status_code==200
        assert load.call_args.kwargs['eval_batch_size']==1024
        with LOCAL_MODEL_LOCK:
            assert c.post('/api/models/unload').status_code==409


def test_restart_recovers_jobs(tmp_path):
    path=tmp_path/'recover.sqlite3';repo=Repository(path)
    w=repo.create_workspace('Interrupted')
    jid=repo.begin_preparation(w['id'],'idea','idea',REMOTE,0)
    repo.preparation_progress(jid,'Сохрани черновик')
    world=repo.save_world('World',summary());save=repo.create_save(world,'Save')
    game=repo.begin_job(save,'','start',REMOTE)
    with TestClient(create_app(path)) as c:
        assert c.get('/api/jobs/'+jid).json()['status']=='stopped'
        assert c.get('/api/jobs/'+game).json()['status']=='stopped'
        assert c.get('/api/workspaces/'+w['id']).json()['idea']=='Сохрани черновик'
