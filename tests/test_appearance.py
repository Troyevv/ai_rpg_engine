"""#74 canonical state, semantic boundaries, lineage and migration."""
from copy import deepcopy
import json
import pytest
from hypothesis import given, strategies as st
from backend.runtime_v3.models import AppearanceProfile, AppearanceFeature, Condition
from backend.runtime_v3.appearance import context_profile, project_card
from backend.runtime_v3.migration import migrate_v2
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.repository import committed_snapshot, read_history
from test_milestones import snapshot, db

TEXT='Мастер закончил татуировку: маленький маяк на плече.'


def change(cid='b',**extra):
    return dict(actor_id=cid,item_id='tattoo',operation='establish',category='modification',kind='tattoo',
        text='Маяк на плече',expected_revision=0,source_event_id='visual',fact_id='appearance_fact',
        assertion='established_visual_outcome',transition='voluntary',evidence=TEXT,**extra)


def payload(state,c=None):
    c=c or change()
    return dict(final_scene=dict(location_id=state['camera']['location_id'],present_character_ids=state['camera']['present_character_ids']),
        facts=[dict(id='appearance_fact',text=TEXT,character_ids=[c['actor_id']],evidence=TEXT)],
        events=[dict(id='visual',text=TEXT,participants=[c['actor_id']],witnesses=[],fact_ids=['appearance_fact'],evidence=TEXT)],
        appearance_deltas=[c])


def resolve(s,c=None,player='',**kwargs):
    return StateResolver(s,TEXT,player,**kwargs).resolve(payload(s,c))


def test_tattoo_canonical_history_and_no_knowledge_broadcast():
    s=migrate_v2(snapshot()).snapshot['world_state'];r=resolve(s)
    assert not r.warnings
    assert r.state['characters']['b']['appearance']['items']['tattoo']['text']=='Маяк на плече'
    assert r.state['knowledge']==s['knowledge']
    assert context_profile(r.state,'b',observer='a') is None
    assert context_profile(r.state,'b',observer='b')['items']['tattoo']
    change=next(x for x in r.history['state_changes'] if x.get('kind')=='appearance_delta')
    assert change['before'] is None and change['source_ids'] and change['source_record_id']


@pytest.mark.parametrize('field,value',[('assertion','planned'),('source_event_id','missing'),('fact_id','missing'),
    ('evidence','несуществующая цитата'),('expected_revision',2),('category','intrinsic'),('transition','established_trait')])
def test_invalid_optional_delta_is_local(field,value):
    s=migrate_v2(snapshot()).snapshot['world_state'];c=change();c[field]=value;r=resolve(s,c)
    assert r.warnings and not r.state['characters']['b']['appearance']['items']


def test_external_voluntary_requires_explicit_choice_but_scar_does_not():
    s=migrate_v2(snapshot()).snapshot['world_state']
    assert resolve(s,change('a')).warnings
    c=change('a',player_evidence='Сделай маяк.',player_assertion='explicit_choice')
    assert not resolve(s,c,player='Сделай маяк.').warnings
    assert resolve(s,c,player='Сделай маяк.',mode='background').warnings
    c.update(kind='scar',item_id='scar',transition='involuntary')
    assert not resolve(s,c).warnings


def test_haircut_partial_update_preserves_stable_traits_and_cas():
    s=migrate_v2(snapshot()).snapshot['world_state']
    s['characters']['b']['appearance']['items']['eyes']=AppearanceFeature(category='intrinsic',kind='eye_color',text='Серые').model_dump()
    c=change();c.update(kind='hairstyle',category='presentation',item_id='hair',text='Короткая стрижка')
    r=resolve(s,c);assert not r.warnings
    c.update(operation='update',expected_revision=1,text='Каре')
    after=resolve(r.state,c).state
    assert after['characters']['b']['appearance']['items']['eyes']==s['characters']['b']['appearance']['items']['eyes']
    assert after['characters']['b']['appearance']['items']['hair']['text']=='Каре'
    assert resolve(after,c).warnings


def test_injury_is_not_automatic_scar_and_condition_is_single_owner():
    s=migrate_v2(snapshot()).snapshot['world_state']
    from backend.runtime_v3.models import Fact
    s['facts']['appearance_fact']=Fact(id='appearance_fact',text=TEXT,character_ids=['b']).model_dump()
    s['conditions']['injury']=Condition(id='injury',actor_id='b',description='Потеря левой кисти',duration='persistent',fact_id='appearance_fact').model_dump()
    raw=payload(s);raw['appearance_deltas']=[]
    r=StateResolver(s,TEXT,'').resolve(raw)
    assert not r.state['characters']['b']['appearance']['items']
    c=change();c.update(category='condition',kind='condition',condition_id='injury',transition='involuntary')
    r=resolve(s,c);assert not r.warnings
    assert context_profile(r.state,'b',observer='b')['items']['tattoo']['text']=='Потеря левой кисти'
    r.state['conditions']['injury']['status']='resolved'
    assert context_profile(r.state,'b',observer='b') is None
    assert resolve(r.state,c).warnings


def test_retry_replay_branch_rollback_and_read_only_legacy():
    snap=migrate_v2(snapshot()).snapshot;s=snap['world_state'];r=resolve(s)
    retry=resolve(r.state,turn_id=r.state['meta']['turn_id'])
    assert retry.state['characters']['b']['appearance']==r.state['characters']['b']['appearance']
    renamed=change();renamed['item_id']='renamed-by-extraction'
    retry=resolve(r.state,renamed,turn_id=r.state['meta']['turn_id'])
    assert retry.state['characters']['b']['appearance']==r.state['characters']['b']['appearance']
    conn=db();after=committed_snapshot(conn,snap,r)
    restored=migrate_v2(json.loads(json.dumps(after))).snapshot
    assert restored['world_state']==after['world_state']
    assert not snap['world_state']['characters']['b']['appearance']['items']
    branch=deepcopy(after);branch['world_state']['characters']['b']['appearance']['items'].clear()
    assert after['world_state']['characters']['b']['appearance']['items']
    assert read_history(conn,after['history_head'])[0]['state_changes']
    old=snapshot();old['world_state']['characters']['b'].pop('appearance');old['character_cards'][1]['fields']['Внешность']='Серые глаза. Сейчас в пальто.'
    frozen=deepcopy(old);migrated=migrate_v2(old).snapshot
    assert old==frozen
    p=migrated['world_state']['characters']['b']['appearance']
    assert p['legacy_text']=='Серые глаза. Сейчас в пальто.' and not p['items']


@given(st.integers(min_value=0,max_value=10080))
def test_elapsed_time_never_regenerates_physical_traits(minutes):
    s=migrate_v2(snapshot()).snapshot['world_state'];s=resolve(s).state
    raw=payload(s);raw['appearance_deltas']=[];raw['events']=[];raw['facts']=[];raw['final_scene']['elapsed_minutes']=minutes
    result=StateResolver(s,'Обычный день.','').resolve(raw)
    assert result.state['characters']['b']['appearance']==s['characters']['b']['appearance']


def test_newborn_uses_same_profile_and_preserves_explicit_text_without_genetics():
    from test_reproduction import state,conceive,deliver
    s=conceive(state()).state;r=deliver(s)
    for cid in set(r.state['characters'])-set(s['characters']):
        p=AppearanceProfile.model_validate(r.state['characters'][cid]['appearance'])
        assert not p.items
        assert p.legacy_text==next(c for c in r.cards if c['id']==cid)['fields'].get('Внешность','')
        r.state['characters'][cid]['developmental_stage']='adult'
        assert AppearanceProfile.model_validate(r.state['characters'][cid]['appearance'])==p


def test_appearance_qa_real_job_cycle(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    from test_narrative_test_world import ordinary_job
    repo=Repository(tmp_path/'qa.sqlite');sid=load_fixture(repo,'appearance')['save']
    before=repo.get_snapshot(sid)['world_state']['characters']['qa_vera']['appearance']
    assert before['items']
    ordinary_job(repo,sid,'start');ordinary_job(repo,sid)
    repo=Repository(repo.path);ordinary_job(repo,sid)
    assert repo.get_snapshot(sid)['world_state']['characters']['qa_vera']['appearance']==before


def test_real_engine_portrait_and_appearance_regenerate_variant_and_rollback(tmp_path):
    from backend.repositories.preparation import Repository
    from backend.repositories.portraits import edit,asset
    from backend.services.portrait_assets import decode_image
    from test_portraits import image
    from devtools.narrative_test_world import load_fixture
    from test_narrative_test_world import CONFIG
    from runtime_v3_fixture import execute
    from unittest.mock import patch
    repo=Repository(tmp_path/'variants.sqlite');sid=load_fixture(repo,'appearance')['save']
    from test_narrative_test_world import ordinary_job
    ordinary_job(repo,sid,'start')
    cid='qa_vera';p=edit(repo,sid,cid,repo.get_save(sid)['revision'],image=decode_image(image(),'image/png'))['portrait']
    before=repo.get_snapshot(sid);raw=payload(before['world_state'],change(cid))
    with patch('backend.runtime_v3.simulation.background_candidate',return_value=None):
        jid=repo.begin_job(sid,'Смотрю.','turn',CONFIG);execute(repo,jid,raw,TEXT)
        assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
        after=repo.get_snapshot(sid);turn=repo.list_turns(sid)[-1]
        jid=repo.begin_job(sid,'','regenerate',CONFIG);execute(repo,jid,raw,TEXT)
        assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    assert repo.get_snapshot(sid)['world_state']==after['world_state']
    repo.select_variant(sid,turn['id'],turn['active_variant_id'],repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)==after
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)==before
    assert asset(repo,sid,cid,p['asset_id'])


def test_structured_import_and_local_optional_salvage():
    from devtools.narrative_test_world import build_fixture
    from backend.runtime_v3.models import assert_world_state_v3_invariants
    legacy=build_fixture();feature=AppearanceFeature(category='intrinsic',kind='eye_color',text='Зелёные глаза').model_dump()
    legacy['world']['characters']['qa_vera']['appearance']=AppearanceProfile(items={'eyes':feature}).model_dump()
    migrated=migrate_v2(legacy).snapshot
    assert migrated['world_state']['characters']['qa_vera']['appearance']['items']=={'eyes':feature}
    bad=deepcopy(migrated['world_state']);p=bad['characters']['qa_vera']['appearance'];p['items']['broken']={'unrecognized':True}
    bad['characters']['qa_vera']['portraits']=[{'asset_id':'../../etc/passwd'}]
    clean=assert_world_state_v3_invariants(bad)
    assert clean['characters']['qa_vera']['appearance']['items']=={'eyes':feature}
    assert clean['characters']['qa_vera']['portraits']==[]
    assert 'broken' in bad['characters']['qa_vera']['appearance']['items']


def test_legacy_save_without_appearance_is_playable(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    from test_narrative_test_world import ordinary_job
    repo=Repository(tmp_path/'legacy.sqlite');sid=load_fixture(repo)['save'];snap=repo.get_snapshot(sid)
    for c in snap['world_state']['characters'].values():c.pop('appearance',None);c.pop('portraits',None)
    snap['character_cards'][0]['fields']['Внешность']='Серые глаза; сегодня в куртке.'
    with repo.connect() as db:db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(snap),sid))
    ordinary_job(repo,sid,'start');ordinary_job(repo,sid);repo=Repository(repo.path);ordinary_job(repo,sid)
    p=repo.get_snapshot(sid)['world_state']['characters'][snap['character_cards'][0]['id']]['appearance']
    assert p['legacy_text']=='Серые глаза; сегодня в куртке.' and not p['items']
