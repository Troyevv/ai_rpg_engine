"""#168 shared deterministic authoring and Extraction; real Runtime/commit/API."""
import json
from story_secrets_fixture import seed as base_seed
from backend.runtime_v3.models import Fact, Knowledge

TEXT='Вера призналась в авторстве романа. Вместе вы решили выяснить, кто подменил рукопись.'
LONG='Вера тайно написала роман. '+('Она работала над рукописью по вечерам и никому её не показывала. '*32)

def seed(repo):
    result=base_seed(repo);snap=repo.get_snapshot(result['save']);s=snap['world_state']
    s['facts']['plot178']['text']=LONG
    s['facts']['plot178']['secret_subject_ids']=['qa_vera','qa_timur']
    for i in range(8):
        fid=f'fog168-{i}'
        s['facts'][fid]=Fact(id=fid,text=f'NEVER-EXPOSE-168-{i}',visibility='secret',story_secret=True,
            secret_subject_ids=['qa_vera'],secret_existence='discoverable').model_dump()
    s['facts']['initial168']=Fact(id='initial168',text='Известно со старта: Вера хранит семейный архив.',story_secret=True,secret_subject_ids=['qa_vera']).model_dump()
    s['knowledge']['qa_kirill:initial168']=Knowledge(actor_id='qa_kirill',fact_id='initial168',status='known').model_dump()
    with repo.connect() as db:
        db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(snap,ensure_ascii=False),result['save']))
    from test_narrative_test_world import ordinary_job
    ordinary_job(repo, result['save'], 'start')
    return result


def payload(snap, reveal=True):
    s=snap['world_state']
    return dict(final_scene=dict(location_id=s['camera']['location_id'],present_character_ids=s['camera']['present_character_ids'],elapsed_minutes=1),
        facts=[dict(id='new168',text='Подмена рукописи связана с закрытым литературным обществом.',visibility='secret',story_secret=True,secret_subject_ids=[],secret_existence='hidden',character_ids=[],evidence=TEXT)],
        events=[dict(id='confession168',text=TEXT,evidence=TEXT,participants=['qa_kirill','qa_vera'],witnesses=['qa_kirill'],fact_ids=['plot178','new168'] if reveal else [],medium='conversation')],
        knowledge_gained=[dict(actor_id='qa_kirill',fact_id=fid,source_event_id='confession168',evidence=TEXT) for fid in (['plot178','new168'] if reveal else [])],
        thread_changes=[dict(id='thread168',description='Найти подлинную рукопись',character_ids=['qa_vera','qa_kirill'],source_event_id='confession168',evidence=TEXT)],
        choices=[dict(action=f'Рассмотреть деталь {i}',speech='') for i in range(6)])
