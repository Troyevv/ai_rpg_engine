"""Persisted reconstructed saves, transactional history and 100 saved turns."""
import json
import sqlite3
from copy import deepcopy
import pytest
from backend.runtime_v3.repository import initialize,migrate_snapshot,committed_snapshot,read_history
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.models import assert_world_state_v3_invariants
from backend.runtime_v3.camera import transition,observe
from backend.runtime_v3.selectors import ui_view
from test_runtime_v3_domain import initial,payload,QUOTE
from world_parser import parse_summary
from test_worlds import summary


def connection(path):
    db=sqlite3.connect(path);initialize(db)
    db.execute('CREATE TABLE IF NOT EXISTS snapshots(id INTEGER PRIMARY KEY,payload TEXT)')
    db.commit();return db


def test_v2_migration_save_reload_play_is_idempotent(tmp_path):
    path=tmp_path/'migration.sqlite';db=connection(path)
    legacy=parse_summary(summary())
    with db:snapshot,report=migrate_snapshot(db,legacy)
    assert snapshot['schema_version']==3
    first_head=snapshot['history_head']
    with db:assert migrate_snapshot(db,legacy)[0]['history_head']==first_head
    for _ in range(2):
        camera=snapshot['world_state']['camera']
        raw=dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids'],elapsed_minutes=1))
        result=StateResolver(snapshot['world_state'],'Пауза.','').resolve(raw)
        with db:
            snapshot=committed_snapshot(db,snapshot,result)
            db.execute('INSERT INTO snapshots(payload) VALUES(?)',(json.dumps(snapshot),))
        db.close();db=connection(path)
        snapshot=json.loads(db.execute('SELECT payload FROM snapshots ORDER BY id DESC LIMIT 1').fetchone()[0])
        assert_world_state_v3_invariants(snapshot['world_state'])
        assert ui_view(snapshot)['runtime_version']==3
    assert snapshot['world_state']['meta']['turn_id']==2


def snapshot_fixture():
    return dict(schema_version=3,world_state=initial(),character_cards=[dict(id=c,name=c,is_player=c=='a',fields={}) for c in ('a','b','c')],
        campaign=dict(protagonist_id='a'),memory={},history_head=None)


def test_100_persisted_turns_and_history_corruption(tmp_path):
    db=connection(tmp_path/'long.sqlite');snapshot=snapshot_fixture()
    for turn in range(100):
        if turn%10==2:snapshot=transition(snapshot,'b')
        if turn%10==3:snapshot=observe(snapshot,'c',allow_protagonist=True)
        if turn%10==4:snapshot=transition(snapshot,'a')
        actor=snapshot['world_state']['camera']['controlled_actor_id'] or 'c'
        location='hall' if turn%2 else 'room'
        p=payload();p['facts'][0]['id']=f'f{turn}';p['events'][0]['fact_ids']=[f'f{turn}'];p['knowledge_gained'][0]['fact_id']=f'f{turn}'
        p['final_scene'].update(location_id=location,present_character_ids=[actor])
        p['relationship_changes']=[dict(source_id='b',target_id='c',dimensions=dict(trust=turn),context='Разговор',evidence=QUOTE)]
        p['thread_changes']=[dict(id='thread',description='Найти письмо',character_ids=['a'],state=str(turn),evidence=QUOTE)]
        p['scheduled_event_changes']=[dict(id='schedule',description='Встреча',character_ids=['b'],due_minute=1000,evidence=QUOTE)]
        if turn%7==0:p['knowledge_gained'][0]['source_event_id']='missing'
        resolved=StateResolver(snapshot['world_state'],QUOTE,'').resolve(p)
        with db:
            snapshot=committed_snapshot(db,snapshot,resolved)
            db.execute('INSERT INTO snapshots(payload) VALUES(?)',(json.dumps(snapshot),))
        snapshot=json.loads(db.execute('SELECT payload FROM snapshots ORDER BY id DESC LIMIT 1').fetchone()[0])
        assert_world_state_v3_invariants(snapshot['world_state'])
        if turn==50:
            with db:db.execute("UPDATE world_history_v3 SET payload_json='broken' WHERE id=?",(snapshot['history_head'],))
    history,warnings=read_history(db,snapshot['history_head'],limit=200)
    assert warnings and len(history['turns'])==99
    assert snapshot['world_state']['meta']['turn_id']==100
    assert len(snapshot['world_state']['knowledge'])==85


def test_atomic_failure_and_immutable_sibling_history(tmp_path):
    db=connection(tmp_path/'variants.sqlite');before=snapshot_fixture()
    resolved=StateResolver(before['world_state'],QUOTE,'').resolve(payload())
    with pytest.raises(RuntimeError):
        with db:
            committed_snapshot(db,before,resolved)
            raise RuntimeError('variant insert failed')
    assert db.execute('SELECT count(*) FROM world_history_v3').fetchone()[0]==0
    with db:
        first=committed_snapshot(db,before,resolved)
        second=committed_snapshot(db,before,resolved)
    assert first['history_head']!=second['history_head']
    assert read_history(db,first['history_head'])==read_history(db,second['history_head'])
    assert db.execute('SELECT parent_id FROM world_history_v3').fetchall()==[(None,),(None,)]


@pytest.mark.parametrize('bad',[None,[],3,{'id':[]},{'id':'broken','witnesses':None},{'id':'broken','witnesses':[],'fact_ids':{},'medium':[]}])
def test_corrupt_history_record_cannot_break_current_or_ui(tmp_path,bad):
    from backend.runtime_v3.repository import append_history
    db=connection(tmp_path/'corrupt.sqlite');snapshot=snapshot_fixture()
    with db:snapshot['history_head']=append_history(db,None,dict(events=[bad],knowledge_acquisitions=[dict(source_event_id=[],actor_id='a',fact_id='f')]))
    history,warnings=read_history(db,snapshot['history_head'])
    assert warnings
    assert ui_view(snapshot,history)['runtime_version']==3
    result=StateResolver(snapshot['world_state'],QUOTE,'').resolve(payload())
    assert result.state['knowledge']['a:f']
