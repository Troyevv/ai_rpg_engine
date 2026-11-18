"""Publication fences, lossless recovery and independent gameplay consequences through real repositories."""
import json
import sqlite3
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import engine
from backend.api.app import create_app
from backend.repositories.preparation import Repository
from backend.services.provider_attempt import identity
from backend.runtime_v3.repository import read_history
from backend.runtime_v3.consequences import resolve_consequences
from backend.runtime_v3.player_actions import resolver_options
from backend.runtime_v3.resolver import StateResolver
from test_scene_steps255 import fixture
from test_integrated_repair247 import seed

pytestmark = pytest.mark.extraction_current
CONFIG = dict(provider='deepseek',model='deepseek-v4-flash',context_length=131072,max_tokens=2400,update_tokens=8192)


@pytest.fixture
def game(tmp_path):
    repo = Repository(tmp_path/'game.sqlite')
    from test_spatial256 import original
    from test_berezovsk_followup248 import LTA
    from copy import deepcopy
    state = original('cafe')['snapshot']['world_state']
    with patch('backend.runtime_v3.player_actions.EXTRACTION_VERSION',5):
        sid = seed(repo,dict(before=state))['save']
    snapshot = deepcopy(LTA['snapshot'])
    snapshot.update(world_state=state,history_head=repo.get_snapshot(sid)['history_head'])
    with repo.connect() as db:
        db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(snapshot),sid))
    return repo,sid


def play(repo,sid,prose,extract,kind='turn',**config):
    jid = repo.begin_job(sid,'Иду в парк.' if kind=='turn' else '',kind,dict(CONFIG,**config))
    calls = []
    def stream(**kwargs):
        stage = identity()['stage']
        calls.append(stage)
        if stage == 'remote_initiative':
            yield '{"action":null}'
        elif stage == 'narrative':
            yield prose
        elif stage == 'extraction':
            # An unrelated connection can already read this scene while
            # Extraction has not even produced its first byte.
            turn = Repository(repo.path).list_turns(sid)[-1]
            assert turn['assistant_text'] == prose
            assert json.loads(turn['changes_json'])['interpretation']=='pending'
            yield extract(jid) if callable(extract) else extract
        else:
            raise AssertionError(stage)
    with patch('engine.chat_stream',side_effect=stream):
        engine.run_job(repo.path,jid,engine.Worker(epoch=0,api_key='offline'))
    assert 'extraction_repair' not in calls
    return repo.get_job(jid)


def test_units_preserve_dependent_integrity_and_separate_perceptions():
    state,_=fixture()
    def apply(raw):
        return StateResolver(state,'Шёл дождь.','Слушаю.',turn_id=1,**resolver_options(state,'Слушаю.','turn',10)).resolve(raw)
    payload = dict(scene=dict(elapsed_minutes=3),scene_steps=[
        dict(kind='movement',actor_ids=['a'],endpoint='park'),
        dict(kind='movement',actor_ids=['missing'],endpoint='new-place'),
        dict(kind='information',claims=[
            dict(fact=dict(text='Открыто по четвергам'),perceived_by=['b']),
            dict(fact=dict(text='Недействительная запись'),perceived_by=['missing'])])],
        locations=[dict(id='new-place',name='Новый двор',evidence='')])
    _, result = resolve_consequences(payload,state,'Шёл дождь.',1,[],apply)
    after=result.state
    assert after['characters']['a']['location_id']=='park' and 'new-place' not in after['locations']
    assert after['meta']['world_time']==state['meta']['world_time']+3
    assert [r['text'] for r in after['facts'].values()]==['Открыто по четвергам']
    assert [k['actor_id'] for k in after['knowledge'].values()]==['b']


def test_prose_only_variant_restart_regeneration_branch_and_rollback(game):
    repo,sid=game
    before=repo.get_snapshot(sid)['world_state']
    first=play(repo,sid,'Пахнет сиренью.  \n','{broken')
    assert first['status']=='saved',first['error']
    original=repo.list_turns(sid)[-1]
    sibling=play(repo,sid,'Мимо пробежала собака.','{}',kind='regenerate',target_turn_id=original['id'])
    assert sibling['status']=='saved',sibling['error']
    second=repo.list_turns(sid)[-1]
    assert second['id']==original['id'] and second['active_variant_id']!=original['active_variant_id']
    next_job=play(repo,sid,'Собака исчезла за поворотом.','{}')
    assert next_job['status']=='saved'
    repo.select_variant(sid,original['id'],original['active_variant_id'],repo.get_save(sid)['revision'],True)
    fresh=Repository(repo.path)
    assert fresh.list_turns(sid)[-1]['assistant_text']==first['narrative']=='Пахнет сиренью.  \n'
    assert len(fresh.variants(original['node_id']))==2
    subsequent=play(fresh,sid,'Я задержался у сирени.','{}')
    assert first['narrative'] in [m['content'] for m in json.loads(subsequent['context_json'])]
    assert sibling['narrative'] not in str(json.loads(subsequent['context_json']))
    fresh.rollback_last(sid)
    fresh.rollback_last(sid)
    assert fresh.get_snapshot(sid)['world_state']==before


@pytest.mark.parametrize('phase',['publish','enrich'])
def test_failed_sql_write_recover_without_provider_or_duplicate(game,monkeypatch,phase):
    repo,sid=game
    original_count=len(repo.list_turns(sid))
    with repo.connect() as db:
        trigger = "BEFORE INSERT ON turns" if phase=='publish' else "BEFORE UPDATE OF after_json ON turns"
        db.execute(f"CREATE TRIGGER fail_write {trigger} BEGIN SELECT RAISE(ABORT,'disk failure'); END")
    prose='Они открыли дверь.'
    job=play(repo,sid,prose,'{}')
    assert job['status']=='error' and job['narrative_complete'] and job['narrative']==prose
    assert 'disk failure' in job['error']
    assert len(repo.list_turns(sid))==original_count+int(phase=='enrich')
    with repo.connect() as db:db.execute('DROP TRIGGER fail_write')
    rev=repo.get_save(sid)['revision']
    with patch('engine.chat_stream',side_effect=AssertionError('unexpected model call')):
        repo.save_completed_scene(job['id'],rev,0)
        saved=repo.get_job(job['id'])
        repo.save_completed_scene(job['id'],repo.get_save(sid)['revision'],0)
    assert saved['status']=='saved'
    turn=repo.list_turns(sid)[-1]
    assert len(repo.list_turns(sid))==original_count+1 and len(repo.variants(turn['node_id']))==1
    assert turn['assistant_text']==prose and json.loads(turn['changes_json'])['interpretation']=='deferred'


def test_server_restart_after_publication_and_manual_edit(game):
    repo,sid=game
    def restart(jid):
        with TestClient(create_app(repo.path)) as client:
            assert client.get('/api/jobs/'+jid).json()['status']=='saved'
        return '{}'
    job=play(repo,sid,'Я разглядел афишу.',restart)
    assert job['status']=='saved' and json.loads(job['warnings_json'])[-1]['code']=='interpretation_interrupted'
    revision=repo.get_save(sid)['revision']
    with TestClient(create_app(repo.path)) as client:
        edit=dict(time='',location='Небольшая площадь',present_ids=['char_alexey'],
                  knowledge=dict(text='Концерт в четверг',actor_ids=['char_alexey'],status='known'),revision=revision)
        response=client.patch(f'/api/saves/{sid}/scene',json=edit)
        assert response.status_code==200,response.text
        assert client.patch(f'/api/saves/{sid}/scene',json=edit).status_code!=200
    fresh=Repository(repo.path);snap=fresh.get_snapshot(sid);world=snap['world_state']
    assert world['locations'][world['camera']['location_id']]['name']==edit['location']
    assert [row['actor_id'] for row in world['knowledge'].values() if world['facts'][row['fact_id']]['text']=='Концерт в четверг']==['char_alexey']
    with fresh.connect() as db:
        hist=read_history(db,snap['history_head'])[0]
        assert {'manual_scene','manual_knowledge'} <= {v.get('kind') for v in hist['state_changes']}
        assert db.execute('pragma integrity_check').fetchone()[0]=='ok'
    fid=next(fid for fid,fact in world['facts'].items() if fact['text']=='Концерт в четверг')
    with TestClient(create_app(repo.path)) as client:
        edit.update(revision=fresh.get_save(sid)['revision'],
                    position=dict(actor_id='char_galina',location='Книжная лавка'),
                    knowledge=dict(fact_id=fid,actor_ids=['char_alexey'],status='refuted'))
        assert client.patch(f'/api/saves/{sid}/scene',json=edit).status_code==200
    corrected=fresh.get_snapshot(sid)['world_state']
    assert corrected['knowledge']['char_alexey:'+fid]['status']=='refuted'
    assert corrected['locations'][corrected['characters']['char_galina']['location_id']]['name']=='Книжная лавка'
    assert corrected['camera']['location_id']==world['camera']['location_id']
    later=play(fresh,sid,'Я запомнил дату концерта.','{}')
    assert any(m['content'].startswith('Ручные исправления канона') for m in json.loads(later['context_json']))


def test_restart_recovers_acknowledged_provider_text_before_publication(game):
    repo,sid=game
    jid=repo.begin_job(sid,'Смотрю в окно.','turn',CONFIG)
    completed='За окном качалась берёза.  '
    worker=Repository(repo.path)
    worker.worker_epoch=0
    rid=worker.begin_request(jid,'narrative',CONFIG,[],{})
    worker.finish_request(rid,'complete',None,finish_reason='stop',
                          response_text=completed+'\n<action_suggestions>["Подойти ближе"]')
    worker.job_progress(jid,'generating',narrative='За окном')
    with TestClient(create_app(repo.path)):
        pass
    job=repo.get_job(jid)
    assert job['status']=='saved',job['error']
    assert job['narrative']==repo.list_turns(sid)[-1]['assistant_text']==completed
    assert [r['stage'] for r in repo.request_log(job_id=jid)]==['narrative']


def test_revision_change_cannot_enrich_or_report_success(game):
    repo,sid=game
    def concurrent_revision(jid):
        with repo.connect() as db:
            db.execute('UPDATE saves SET revision=revision+1 WHERE id=?',(sid,))
        return '{"scene":{"elapsed_minutes":10}}'
    job=play(repo,sid,'Галина закрыла окно.',concurrent_revision)
    assert job['status']=='error' and job['narrative_complete']
    assert repo.list_turns(sid)[-1]['assistant_text']==job['narrative']
    with pytest.raises(ValueError):
        repo.save_completed_scene(job['id'],job['revision'],0)
    # A fresh explicit request can keep the already published active variant.
    # It only closes its warning and never reapplies consequences to the edited state.
    current=repo.get_save(sid)['revision']
    repo.save_completed_scene(job['id'],current,0)
    assert repo.get_job(job['id'])['status']=='saved' and repo.get_save(sid)['revision']==current
    assert repo.get_snapshot(sid)['world_state']['meta']['world_time']==json.loads(job['before_json'])['world_state']['meta']['world_time']


def test_current_long_term_keeps_offstage_prose_on_extraction_outage():
    from test_long_term_advance import fixture as interval
    from backend.runtime_v3.long_term import run
    from backend.runtime_v3.models import Thread
    before=interval()
    before['world_state']['threads']['work']=Thread(id='work',description='Новая работа', character_ids=['c'],relevance=1).model_dump()
    prose='На другом берегу открылась мастерская.'
    stages=[]
    def generate(stage,*args,**kwargs):
        stages.append(stage)
        if stage=='long_term_narrative':
            yield prose
        else:
            raise RuntimeError('provider offline')
    result,history,report=run(before,dict(amount=1,unit='years',max_llm_calls=4),generate=generate,
                              config={**CONFIG,'_extraction_contract':10})
    assert 'long_term_repair' not in stages and report['unresolved']
    assert any(r['narrative']==prose and not r['player_observed'] for r in history['turns'])
    assert result['world_state']['meta']['world_time']>before['world_state']['meta']['world_time']


def test_inline_marker_and_trailing_whitespace_remain_literary_text():
    from backend.runtime_v3.suggestions import MARKER, split_suggestions
    prose = 'На листке написано '+MARKER+' карандашом.  \n'
    wire = prose+'\n'+MARKER+'\n["Осмотреть листок"]'
    assert split_suggestions(prose,complete=True,verbatim=True)==(prose,[])
    assert split_suggestions(wire,complete=True,verbatim=True)==(prose,['Осмотреть листок'])
    for i in range(len(prose)+1,len(prose)+1+len(MARKER)):
        assert split_suggestions(wire[:i],verbatim=True)[0]==prose
