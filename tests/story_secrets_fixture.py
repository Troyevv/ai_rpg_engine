"""Shared API/browser fixture: production Remote + semantic resolver, no fake reads."""
import json
from devtools.narrative_test_world import load_fixture
from backend.runtime_v3.models import Fact, Knowledge
from backend.runtime_v3.remote import apply
from backend.runtime_v3.remote_semantics import resolve
from backend.runtime_v3.repository import append_history


def seed(repo):
    selected=load_fixture(repo,'phone');sid=selected['save'];snap=repo.get_snapshot(sid);s=snap['world_state']
    s['facts']['plot178']=Fact(id='plot178',text='Вера тайно написала роман.',visibility='secret',story_secret=True,
        secret_subject_ids=['qa_vera'],secret_existence='discoverable').model_dump()
    s['facts']['hidden178']=Fact(id='hidden178',text='NEVER-EXPOSE-178',visibility='secret',story_secret=True).model_dump()
    s['knowledge']['qa_vera:plot178']=Knowledge(actor_id='qa_vera',fact_id='plot178').model_dump()
    for op,text in [('bread','Купи хлеб'),('reveal','Я написала роман.')]:
        snap,h=apply(snap,dict(action='send',character_id='qa_kirill',content=text,operation_id='secret178-'+op),actor_id='qa_vera',autonomous=True)
        eid=max(snap['world_state']['remote_events'].values(),key=lambda e:e['ordinal'])['id']
        if op=='bread':
            snap,h=apply(snap,dict(action='read',event_id=eid,operation_id='secret178-read-bread'))
    s=snap['world_state']
    snap,h=resolve(snap,eid,dict(final_scene=dict(location_id=s['camera']['location_id'],present_character_ids=s['camera']['present_character_ids'],elapsed_minutes=0),
        secret_disclosures=[dict(source_event_id=eid,fact_id='plot178',assertion='confirmed',evidence='Я написала роман.')]))
    snap['campaign'].setdefault('sections',{})['knowledge']='RAW-HIDDEN-178'
    with repo.connect() as db:
        snap['history_head']=append_history(db,snap.get('history_head'),h)
        db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(snap,ensure_ascii=False),sid))
    return dict(world=selected['world'],save=sid,event=eid)
