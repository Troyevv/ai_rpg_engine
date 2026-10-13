"""Issue #42: role/control identity, death, drafts, atomic lineage and agency."""
from copy import deepcopy
import json
from unittest.mock import patch
import pytest
from backend.runtime_v3.models import Character,Fact,Knowledge,WorldStateV3,Location
from backend.runtime_v3.protagonist import initialize,transition,reconcile
from backend.services.protagonist_creation import empty_draft,prepare,creation_context
from backend.runtime_v3.resolver import StateResolver


def snapshot():
    world=WorldStateV3(camera=dict(location_id='home',controlled_actor_id='a',present_character_ids=['a','b','child','baby']),
        characters={cid:Character(id=cid,display_name=cid,life_status='alive',location_id='home',
            developmental_stage='infant' if cid=='baby' else 'child' if cid=='child' else 'adult').model_dump() for cid in ('a','b','child','baby')},
        locations={'home':Location(id='home',name='Дом')}).model_dump()
    world['facts']['secret']=Fact(id='secret',text='Приватное письмо',visibility='secret',character_ids=['a']).model_dump()
    world['knowledge']['a:secret']=Knowledge(actor_id='a',fact_id='secret').model_dump()
    return initialize(dict(schema_version=3,world_state=world,character_cards=[dict(id=cid,name=cid,is_player=cid=='a',fields={}) for cid in world['characters']],campaign={'protagonist_id':'a'},history_head=None))


def draft(s,op='new-person'):
    d=empty_draft(s,op);d['card']['name']='Новая героиня';d['card']['fields']['Биография']='Приехала в город учиться.'
    d['character']['location_id']='home';d['starting_scene']='У двери дома, утро.'
    return d


def test_role_and_temporary_control_are_distinct_and_preserve_all_identities():
    s=snapshot();before=deepcopy(s['world_state']);temp,batch=transition(s,'temporary','b','temporary')
    assert temp['world_state']['meta']['current_protagonist_id']=='a'
    assert temp['world_state']['meta']['protagonist_periods']==before['meta']['protagonist_periods']
    final,batch=transition(temp,'permanent','child','permanent')
    assert final['world_state']['characters']==before['characters']
    assert final['world_state']['knowledge']==before['knowledge']
    assert final['world_state']['camera']['controlled_actor_id']=='child'
    assert final['world_state']['meta']['current_protagonist_id']=='child'
    assert len(final['world_state']['meta']['protagonist_periods'])==2
    from backend.runtime_v3.milestones import derive
    assert derive(batch)[0]['category']=='protagonist_transition'
    assert s['world_state']==before
    back,_=transition(final,'permanent','a','back')
    assert back['world_state']['characters']==before['characters']


def test_infant_observation_and_incapacity_do_not_require_succession():
    s=snapshot();s['world_state']['characters']['a']['capabilities']['conscious']=False
    observed,_=transition(s,'observe','a','observe')
    assert observed['world_state']['camera']['controlled_actor_id'] is None
    assert not observed['world_state']['meta']['protagonist_required']
    with pytest.raises(ValueError,match='способен'):transition(s,'resume',None,'resume')
    temp,_=transition(observed,'temporary','b','temporary')
    assert temp['world_state']['meta']['current_protagonist_id']=='a'
    temp['world_state']['characters']['a']['capabilities']['conscious']=True
    resumed,_=transition(temp,'resume',None,'resume')
    assert resumed['world_state']['camera']['controlled_actor_id']=='a'
    infant,_=transition(resumed,'permanent','baby','infant')
    assert infant['world_state']['camera']['controlled_actor_id'] is None
    assert infant['world_state']['camera']['pov_actor_id']=='baby'
    assert not infant['world_state']['meta']['protagonist_required']


def test_risk_seam_blocks_autonomous_death_but_allows_explicit_death_and_succession():
    s=snapshot();text='Персонаж погиб.'
    raw=dict(final_scene=dict(location_id='home',present_character_ids=['a','b']),
        life_changes=[dict(id='a',life_status='dead',assertion='established',evidence=text)])
    denied=StateResolver(s['world_state'],text,'').resolve(raw)
    assert denied.state['characters']['a']['life_status']=='alive'
    class Permitted:
        def permits_autonomous_death(self,state,actor): return True
    allowed=StateResolver(s['world_state'],text,'',death_policy=Permitted()).resolve(raw)
    assert allowed.state['meta']['protagonist_required']
    assert allowed.state['camera']['controlled_actor_id'] is None
    assert allowed.state['characters']['a']['life_status']=='dead'
    s['world_state']=allowed.state
    with pytest.raises(ValueError,match='выбери нового'):transition(s,'temporary','b','temporary')
    continued,_=transition(s,'permanent','b','permanent')
    assert not continued['world_state']['meta']['protagonist_required']
    assert continued['world_state']['characters']['a']['life_status']=='dead'
    assert 'b:secret' not in continued['world_state']['knowledge']
    raw['life_changes'][0].update(player_assertion='explicit_choice',player_evidence=text)
    explicit=StateResolver(snapshot()['world_state'],text,text).resolve(raw)
    assert explicit.state['meta']['protagonist_required']


def test_manual_creation_empty_knowledge_preserves_existing_characters_and_clock():
    s=snapshot();d=draft(s);before=deepcopy(s)
    created,cid,history=prepare(s,d,'new-person')
    assert s==before and cid in created['world_state']['characters']
    assert created['world_state']['meta']==s['world_state']['meta']
    assert {k:v for k,v in created['world_state']['characters'].items() if k!=cid}==s['world_state']['characters']
    assert created['world_state']['knowledge']==s['world_state']['knowledge']
    final,_=transition(created,'permanent',cid,'new-person')
    assert final['world_state']['camera']['controlled_actor_id']==cid
    assert final['world_state']['camera']['situation']==d['starting_scene']
    assert history['state_changes'][0]['kind']=='character_creation'


@pytest.mark.parametrize('mutation',[
    lambda d:d['character'].update(location_id='made-up'),
    lambda d:d['character'].update(id='b'),
    lambda d:d['character'].update(life_status='dead'),
    lambda d:d['knowledge'].append(dict(fact_id='not-real',evidence='Начальное знание',approved=True)),
    lambda d:d['knowledge'].append(dict(fact_id='secret',source_actor_id='b',evidence='Не знает',approved=True)),
    lambda d:d['secrets'].append(dict(text='Моя тайна',holders=['fake'],evidence='Биография',approved=True)),
    lambda d:d['proposals'].append(dict(kind='location',value=dict(id='home',name='Новое имя'),evidence='Изменение',approved=True)),
])
def test_creation_rejects_invalid_proposals_without_mutating_anything(mutation):
    s=snapshot();before=deepcopy(s);d=draft(s);mutation(d)
    with pytest.raises(ValueError):prepare(s,d,'new-person')
    assert s==before


def test_explicit_scoped_knowledge_and_personal_secrets():
    s=snapshot();d=draft(s);cid=d['character']['id']
    d['knowledge']=[dict(fact_id='secret',source_actor_id='a',evidence='А рассказал при знакомстве.',approved=True)]
    d['secrets']=[dict(text='У нового персонажа есть собственная тайна.',holders=[cid],evidence='Авторская биография.',approved=True)]
    result,_,_=prepare(s,d,'new-person');world=result['world_state']
    assert world['knowledge'][cid+':secret']['status']=='known'
    new_secret=next(fid for fid in world['facts'] if fid!='secret')
    assert cid+':'+new_secret in world['knowledge']
    assert not any(other+':'+new_secret in world['knowledge'] for other in ('a','b','child','baby'))
    assert 'Приватное письмо' not in json.dumps(creation_context(s),ensure_ascii=False)


def test_per_field_generation_isolated_and_instrumented(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    from backend.services.protagonist_generation import generate
    from test_narrative_test_world import CONFIG
    repo=Repository(tmp_path/'test.sqlite');sid=load_fixture(repo)['save'];s=repo.get_snapshot(sid)
    d=empty_draft(s,'generation');d['card']['name']='Имя';d['starting_scene']='До'
    with patch('llm.chat_stream',return_value=iter([json.dumps({'value':'После'})])):
        result=generate(repo,sid,d,'starting_scene','',dict(CONFIG,provider='local'),None)
    assert result==dict(d,starting_scene='После')
    assert repo.get_snapshot(sid)==s
    log=repo.request_log(save_id=sid)
    assert len(log)==1 and log[0]['stage']=='character_draft' and log[0]['status']=='complete'


def test_atomic_repository_preview_retry_failure_reload_and_rollback(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture,ACTOR_ID
    from test_narrative_test_world import ordinary_job
    repo=Repository(tmp_path/'test.sqlite');sid=load_fixture(repo)['save'];ordinary_job(repo,sid,'start')
    before=repo.get_snapshot(sid);revision=repo.get_save(sid)['revision'];op='manual-new-person'
    d=empty_draft(before,op);d['card']['name']='Анна';d['character']['location_id']=before['world_state']['camera']['location_id'];d['starting_scene']='Анна у двери.'
    repo.transition_protagonist(sid,revision,op,'permanent',draft=d,preview=True)
    assert repo.get_snapshot(sid)==before and repo.get_save(sid)['revision']==revision
    with patch('backend.runtime_v3.protagonist.transition',side_effect=ValueError('fail')):
        with pytest.raises(ValueError):repo.transition_protagonist(sid,revision,op,'permanent',draft=d)
    assert repo.get_snapshot(sid)==before
    after=repo.transition_protagonist(sid,revision,op,'permanent',draft=d)
    assert repo.transition_protagonist(sid,revision,op,'permanent',draft=d)==after
    assert repo.get_save(sid)['revision']==revision+1
    reloaded=Repository(repo.path);assert reloaded.get_snapshot(sid)==after
    from runtime_v3_fixture import execute
    from test_narrative_test_world import CONFIG
    camera=after['world_state']['camera'];raw=dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids']))
    job=repo.begin_job(sid,'Смотрю вокруг.','turn',CONFIG);execute(repo,job,raw,'У двери тихо.')
    assert repo.get_job(job)['status']=='saved',repo.get_job(job)['error']
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)==after
    repo.rollback_last(sid)
    assert d['character']['id'] not in repo.get_snapshot(sid)['world_state']['characters']


@pytest.mark.parametrize('checkpoint',['protagonist','protagonist-infant'])
def test_shared_qa_checkpoints_child_and_born_in_world_observation(tmp_path,checkpoint):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture,ACTOR_ID
    from test_narrative_test_world import CONFIG,ordinary_job
    from runtime_v3_fixture import execute
    repo=Repository(tmp_path/'qa.sqlite');sid=load_fixture(repo,checkpoint)['save']
    s=repo.get_snapshot(sid);world=s['world_state']
    if checkpoint=='protagonist':
        ordinary_job(repo,sid,'start')
        previous=repo.get_snapshot(sid)
        repo.transition_protagonist(sid,repo.get_save(sid)['revision'],'qa-child-switch','permanent','qa_asya')
        s=repo.get_snapshot(sid);world=s['world_state']
        assert world['characters']==previous['world_state']['characters']
        assert world['knowledge']==previous['world_state']['knowledge']
        from backend.runtime_v3.life import capabilities
        assert capabilities(world,'qa_asya')['can_act']
        action='Рассматриваю рисунки.';config=CONFIG
    else:
        cid=world['meta']['current_protagonist_id']
        assert world['characters'][cid]['birth_provenance']
        assert world['camera']['controlled_actor_id'] is None
        action='';config=dict(CONFIG,time_skip={'duration':10,'reason':'Наблюдение за окружающими'})
    camera=world['camera'];raw=dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids'],elapsed_minutes=10 if checkpoint.endswith('infant') else 1))
    jid=repo.begin_job(sid,action,'turn',config);execute(repo,jid,raw,'В доме спокойно. Вера разговаривает с Кириллом.')
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    reloaded=Repository(repo.path).get_snapshot(sid)
    assert reloaded['world_state']['meta']['current_protagonist_id']==world['meta']['current_protagonist_id']
    if checkpoint.endswith('infant'): assert repo.list_turns(sid)[-1]['choices_json']=='[]'
    repo.rollback_last(sid);assert repo.get_snapshot(sid)==s


def test_observation_pov_is_not_external_and_does_not_inherit_parent_history():
    from backend.runtime_v3.context import build_context
    s=snapshot();s['character_cards'][0]['fields']={'Характер':'Сдержанный'}
    observed,_=transition(s,'observe','child','observe-child')
    turns=[dict(kind='turn',pov_actor_id='a',audience_json='["a"]',assistant_text='Родитель прочитал секретное письмо.',user_text='Читаю письмо.')]
    messages=build_context(observed,turns,'','background',32768,2000)
    pov=json.loads(next(m['content'].split('\n',1)[1] for m in messages if m['content'].startswith('Знания POV\n')))
    assert not pov
    assert not any('Родитель прочитал секретное письмо.' in m['content'] for m in messages)
    assert 'controlled_actor_id=None' in messages[0]['content']


def test_legacy_read_and_dead_protagonist_block_before_provider(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture,ACTOR_ID
    from test_narrative_test_world import CONFIG,ordinary_job
    repo=Repository(tmp_path/'legacy.sqlite');sid=load_fixture(repo)['save'];ordinary_job(repo,sid,'start')
    s=repo.get_snapshot(sid);world=s['world_state']
    for key in ('current_protagonist_id','protagonist_required','protagonist_periods'):world['meta'].pop(key,None)
    world['characters'][ACTOR_ID]['life_status']='dead'
    world['camera']['present_character_ids'].remove(ACTOR_ID)
    with repo.connect() as db:db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(s),sid))
    with pytest.raises(ValueError,match='умер'):repo.begin_job(sid,'Иду.','turn',CONFIG)
    current=repo.get_snapshot(sid)
    assert current['world_state']['meta']['protagonist_required']
    repo.transition_protagonist(sid,repo.get_save(sid)['revision'],'legacy-successor','permanent','qa_vera')
    assert not repo.get_snapshot(sid)['world_state']['meta']['protagonist_required']


def test_branch_and_regeneration_use_original_control_context(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture,ACTOR_ID
    from test_narrative_test_world import CONFIG,ordinary_job
    from runtime_v3_fixture import execute
    repo=Repository(tmp_path/'lineage.sqlite');result=load_fixture(repo);sid=result['save'];ordinary_job(repo,sid,'start')
    s=repo.transition_protagonist(sid,repo.get_save(sid)['revision'],'first-successor','permanent','qa_vera')
    def play(kind='turn'):
        camera=s['world_state']['camera'];raw=dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids']))
        jid=repo.begin_job(sid,'Слушаю.' if kind=='turn' else '',kind,CONFIG);execute(repo,jid,raw,'В доме тихо.')
        assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
        return jid
    play();original=repo.get_snapshot(sid);turn=repo.list_turns(sid)[-1]
    repo.transition_protagonist(sid,repo.get_save(sid)['revision'],'second-successor','permanent','qa_timur')
    jid=play('regenerate')
    assert repo.get_snapshot(sid)['world_state']['meta']['current_protagonist_id']=='qa_vera'
    memory=json.loads(repo.get_job(jid)['memory_before_json']);assert memory['world_state']['camera']['controlled_actor_id']=='qa_vera'
    repo.select_variant(sid,turn['id'],turn['active_variant_id'],repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)==original


def test_child_profile_is_not_reset_by_repeated_control_or_aging():
    from backend.runtime_v3.personality import initialize_profiles
    from backend.runtime_v3.life import capabilities
    s=snapshot();next(c for c in s['character_cards'] if c['id']=='child')['fields']['Характер']='Любознательна'
    initialize_profiles(s);actor=s['world_state']['characters']['child']
    actor['personality']['items']['traits']['revision']=3
    actor['personality']['applied']=['established-child-development'];profile=deepcopy(actor['personality'])
    for i,target in enumerate(('child','a','child','b','child')):
        s,_=transition(s,'permanent',target,'phase-'+str(i))
        assert s['world_state']['characters']['child']['personality']==profile
    s['world_state']['characters']['child']['birth_date']='2016-10-05'
    s['world_state']['meta']['calendar']=dict(start_minute=0,start_weekday=0,start_date='2026-10-05',profile={})
    s['world_state']['meta']['world_time']+=365*11*1440
    s['world_state']['characters']['child']['developmental_stage']='adult'
    s,_=transition(s,'temporary','a','grown-child-background');s,_=transition(s,'resume',None,'grown-child-resume')
    assert capabilities(s['world_state'],'child')['adult_eligible']
    assert s['world_state']['characters']['child']['personality']==profile
    assert 'child:secret' not in s['world_state']['knowledge']


def test_relation_proposals_grounded_and_directional():
    s=snapshot();d=draft(s);cid=d['character']['id'];d['character']['developmental_stage']='adult'
    d['proposals']=[dict(kind='objective_relation',value=dict(id='connection',kind='friend',source_id=cid,target_id='b'),evidence='Познакомились ранее.',approved=True),
        dict(kind='relationship',value=dict(source_id=cid,target_id='b',dimensions={'trust':15},context='Уважает собеседника.'),evidence='Биография нового персонажа.',approved=True)]
    result,_,_=prepare(s,d,'new-person')
    assert result['world_state']['relationships'][cid+':b']['dimensions']=={'trust':15}
    assert 'b:'+cid not in result['world_state']['relationships']
    d['proposals'][1]['value'].update(source_id='b',target_id=cid)
    with pytest.raises(ValueError,match='чувства'):prepare(s,d,'new-person')


def test_event_reference_and_secret_authorization_are_pov_scoped():
    from backend.services.protagonist_creation import editor_context
    s=snapshot();d=draft(s)
    d['knowledge']=[dict(fact_id='secret',source_actor_id='a',source_event_id='letter',evidence='Рассказ о письме.',approved=True)]
    history={'events':[dict(id='letter',text='Письмо',witnesses=['a'],fact_ids=['secret'])]}
    result,cid,batch=prepare(s,d,'new-person',history)
    assert batch['knowledge_acquisitions'][0]['origin_event_id']=='letter'
    assert cid+':secret' in result['world_state']['knowledge']
    with pytest.raises(ValueError,match='source_event_id'):prepare(s,d,'new-person')
    observed,_=transition(s,'observe','child','observe-child')
    assert not editor_context(observed,history)['knowledge_facts']
    assert not editor_context(observed,history)['events']
    with pytest.raises(ValueError,match='POV'):prepare(observed,d,'new-person',history)


def test_separate_secret_events_never_cross_reveal_holders():
    s=snapshot();d=draft(s)
    d['secrets']=[dict(text='Первая тайна',holders=['a'],evidence='Первое свидетельство',approved=True),
                  dict(text='Вторая тайна',holders=['b'],evidence='Второе свидетельство',approved=True)]
    _,_,history=prepare(s,d,'new-person')
    assert len(history['events'])==2
    assert history['events'][0]['witnesses']==['a'] and history['events'][1]['witnesses']==['b']
    assert set(history['events'][0]['fact_ids']).isdisjoint(history['events'][1]['fact_ids'])


def test_full_and_section_generation_preserve_identity_and_require_approval(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    from backend.services.protagonist_generation import generate
    from test_narrative_test_world import CONFIG
    repo=Repository(tmp_path/'generation.sqlite');sid=load_fixture(repo)['save'];s=repo.get_snapshot(sid)
    d=empty_draft(s,'full-generation');complete=deepcopy(d)
    complete['card']['name']='Анна';complete['character']['location_id']=s['world_state']['camera']['location_id'];complete['starting_scene']='У двери.'
    complete['secrets']=[dict(text='Своя тайна',holders=[d['character']['id']],evidence='Своя биография',approved=True)]
    cfg=dict(CONFIG,provider='local')
    with patch('llm.chat_stream',return_value=iter([json.dumps({'value':complete})])):
        result=generate(repo,sid,d,'','',cfg,None)
    assert not result['secrets'][0]['approved']
    assert repo.get_snapshot(sid)==s
    result['secrets'][0]['approved']=True
    with patch('llm.chat_stream',return_value=iter([json.dumps({'value':'Другая сцена'})])) as request:
        changed=generate(repo,sid,result,'starting_scene','',cfg,None)
    assert changed==dict(result,starting_scene='Другая сцена')
    message=json.loads(request.call_args.kwargs['messages'][-1]['content'])
    assert message['schema']['type']=='string' and '$defs' not in message['schema']
    for malformed in ({'value':{'character':[]}}, {'value':None}, [], {'value':dict(complete,character={'id':'fake'})}):
        with patch('llm.chat_stream',return_value=iter([json.dumps(malformed)])):
            with pytest.raises(ValueError):generate(repo,sid,result,'','',cfg,None)
    assert repo.get_snapshot(sid)==s


def test_creation_receipts_are_isolated_between_history_branches(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    from backend.runtime_v3.repository import read_history
    repo=Repository(tmp_path/'branches.sqlite');seed=load_fixture(repo);sid=seed['save']
    before=repo.get_snapshot(sid);op='branch-character';d=empty_draft(before,op)
    d['card']['name']='Первая ветка';d['character']['location_id']=before['world_state']['camera']['location_id'];d['starting_scene']='У двери.'
    first=repo.transition_protagonist(sid,repo.get_save(sid)['revision'],op,'permanent',draft=d)
    sibling=repo.create_save(seed['world'],'Другая ветка')
    with repo.connect() as db: db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(before),sibling))
    d['card']['name']='Вторая ветка'
    second=repo.transition_protagonist(sibling,repo.get_save(sibling)['revision'],op,'permanent',draft=d)
    assert first['history_head']!=second['history_head']
    assert repo.get_snapshot(sid)==first
    for after,name in ((first,'Первая ветка'),(second,'Вторая ветка')):
        assert next(c['name'] for c in after['character_cards'] if c['id']==d['character']['id'])==name
        with repo.connect() as db: history,_=read_history(db,after['history_head'])
        assert len([r for r in history['state_changes'] if r.get('kind')=='character_creation'])==1


def test_approved_relation_uses_canonical_facts_and_explicit_audience():
    from backend.runtime_v3.kinship import visible_relations
    s=snapshot();d=draft(s);cid=d['character']['id']
    d['proposals']=[dict(kind='objective_relation',value=dict(id='new-friend',kind='friend',source_id=cid,target_id='b'),
        holders=[cid,'b'],evidence='Оба знакомы по учёбе.',approved=True)]
    created,_,history=prepare(s,d,'new-person');world=created['world_state']
    assert visible_relations(world,cid)[0]['id']=='new-friend'
    assert visible_relations(world,'b')[0]['id']=='new-friend'
    assert not visible_relations(world,'a')
    assert len(history['events'])==1
    d['proposals'][0]['value']['since']=world['meta']['world_time']+1
    with pytest.raises(ValueError,match='ещё не произошло'):prepare(s,d,'new-person')


def test_legacy_preview_rolls_back_migration_history_and_cache(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    from world_parser import parse_summary
    from test_worlds import summary
    repo=Repository(tmp_path/'preview.sqlite');sid=load_fixture(repo)['save']
    legacy=parse_summary(summary());raw=json.dumps(legacy)
    with repo.connect() as db:
        db.execute('UPDATE saves SET state_json=? WHERE id=?',(raw,sid))
        before=list(db.execute('SELECT id FROM world_history_v3'))
        migrations=list(db.execute('SELECT source_hash FROM world_migrations_v3'))
        revision=db.execute('SELECT revision FROM saves WHERE id=?',(sid,)).fetchone()[0]
    preview=repo.transition_protagonist(sid,revision,'legacy-preview','permanent','character_2',preview=True)
    assert preview['world_state']['meta']['current_protagonist_id']=='character_2'
    with repo.connect() as db:
        assert [tuple(r) for r in db.execute('SELECT id FROM world_history_v3')]==[tuple(r) for r in before]
        assert [tuple(r) for r in db.execute('SELECT source_hash FROM world_migrations_v3')]==[tuple(r) for r in migrations]
        row=db.execute('SELECT state_json,revision FROM saves WHERE id=?',(sid,)).fetchone()
        assert tuple(row)==(raw,revision)
