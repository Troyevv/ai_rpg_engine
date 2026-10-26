from copy import deepcopy
from test_calendar_v2 import state, snapshot
from backend.runtime_v3.player_calendar import player_calendar
from backend.runtime_v3.kinship import genealogy, genealogy_roots
from test_life_social import family


def test_birthdays_public_without_knowledge_or_control():
    s=state();s['characters']['sonya']['birth_date']='2000-10-09';s['knowledge']={}
    before=deepcopy(s)
    expected=player_calendar(s,'2026-10-01','2026-10-31')['events']
    assert any('sonya' in e['character_ids'] for e in expected)
    assert s==before
    s['camera']['controlled_actor_id']=None
    assert player_calendar(s,'2026-10-01','2026-10-31')['events']==expected


def test_family_public_but_not_relation_private_context():
    s=family();s['knowledge']={};s['camera']['controlled_actor_id']=None
    before=deepcopy(s)
    roots=genealogy_roots(snapshot(s))
    assert {r['id'] for r in roots}==set(s['characters'])
    for root in roots:
        g=genealogy(snapshot(s),root['id'])
        assert g['nodes'] and all(e['certainty']=='known' for e in g['edges'])
        assert all('fact_id' not in e and 'context' not in e for e in g['edges'])
    assert s==before


def test_birthdays_are_complete_beyond_preview_and_scheduled_page_limits():
    s=state();s['knowledge']={}
    for index in range(510):
        cid=f'directory_{index}'
        s['characters'][cid]=dict(deepcopy(s['characters']['sonya']),id=cid,birth_date='2000-10-09')
    result=player_calendar(s,'2026-10-09','2026-10-09')
    ids={cid for e in result['events'] for cid in e['character_ids']}
    assert {f'directory_{i}' for i in range(510)}<=ids


def test_birthday_recurrence_respects_birth_boundary_and_leap_day():
    s=state();s['characters']['sonya']['birth_date']='2024-02-29';s['knowledge']={}
    for year,count in [(2020,0),(2023,0),(2024,1),(2025,0),(2028,1)]:
        result=player_calendar(s,f'{year}-02-01',f'{year}-03-01')
        assert sum(e['character_ids']==['sonya'] for e in result['events'])==count


def test_dead_character_dob_remains_public_and_missing_dob_is_not_invented():
    s=state();s['knowledge']={}
    s['characters']['sonya']['birth_date']='2000-10-09'
    s['characters']['sonya']['life_status']='dead'
    result=player_calendar(s,'2026-10-01','2026-10-31')
    assert any(e['character_ids']==['sonya'] for e in result['events'])
    s['characters']['sonya']['birth_date']=None
    assert not any(e['character_ids']==['sonya'] for e in player_calendar(s,'2026-10-01','2026-10-31')['events'])
