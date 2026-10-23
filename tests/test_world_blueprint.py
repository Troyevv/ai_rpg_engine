"""The default creative contract and canonical pipeline; no live provider calls."""
import json
from unittest.mock import patch
import pytest
from test_api import api, REMOTE
from test_world_generation import wait, fake_stages
from test_world_interpretation import interpretation, BRIEF
from backend.services import world_blueprint as blueprint


def blueprint_of(old):
    return {'entities':[{k:v for k,v in e.items() if k!='spans'} for e in old['entities']],
        'notes':[dict(origin='explicit' if c['classification'] in ('explicit','prohibition') else 'unknown',
            section=c['section'],text=c['description'],subject_key=c.get('subject_key'),
            related_keys=c.get('related_keys',[]),holder_keys=c.get('holder_keys',[]),
            time_scope=c.get('time_scope','')) for c in old['claims']]}


def creative_provider(calls, old=None, provider=None, conflict=False):
    provider=provider or fake_stages(calls)
    def stream(**kw):
        stage=kw['messages'][0]['content'].split('\nStage: ')[1].split('\n')[0]
        data=json.loads(kw['messages'][-1]['content'])
        if stage=='interpret':
            calls.append(stage)
            yield json.dumps(blueprint_of(old or interpretation()),ensure_ascii=False)
        elif stage=='review':
            calls.append(stage)
            yield json.dumps({'findings':[dict(claim_id=c['id'],verdict='conflict' if conflict else 'preserved',explanation='Авторское замечание, включая тайну') for c in data['claims']]})
        elif stage in ('ties','circumstances','background','knowledge'):
            from copy import deepcopy
            from backend.services.initial_world_stages import CREATIVE_PARTS
            forwarded={**kw,'messages':deepcopy(kw['messages'])};forwarded['messages'][0]['content']=forwarded['messages'][0]['content'].replace('Stage: '+stage,'Stage: '+('life' if stage in ('ties','circumstances') else 'lore'))
            raw=json.loads(''.join(provider(**forwarded)))
            yield json.dumps({k:v for k,v in raw.items() if k in CREATIVE_PARTS[stage].model_fields})
        else:yield from provider(**kw)
    return stream


def submit(client,text=BRIEF):
    wid=client.post('/api/workspaces',json={'name':'Blueprint'}).json()['id']
    r=client.post(f'/api/workspaces/{wid}/draft/generate',json=dict(task='world_staged',text=text,revision=0,config=REMOTE,api_key='fixture'))
    assert r.status_code==200,r.text
    return wid,r.json()['id']


def test_contract_has_no_quotes_rules_or_offsets_and_chunks_are_lossless():
    schema=json.dumps(blueprint.Blueprint.model_json_schema())
    for forbidden in ('SourceSpan','ConstraintRule','spans','quote','start','end','rules'):
        assert '"'+forbidden+'"' not in schema
    text=('Большой замысел с разными обстоятельствами.\n'*800)
    chunks=blueprint.fragments(text)
    assert len(chunks)>1 and ''.join(chunks)==text
    assert max(map(len,chunks))<=6000
    raw=blueprint_of(interpretation())
    accepted=blueprint.accept(raw,'A paraphrase need not occur in this text.','workspace',1)
    assert accepted['version']==2 and not accepted['blocking_ids']
    assert all('spans' not in c and not c['rules'] for c in accepted['claims'])
    assert blueprint.accept(raw,'Different source length','workspace',2)['entities']==accepted['entities']


def test_advisory_conflict_does_not_retry_or_block_start_and_stays_private(api):
    client,app=api;calls=[];repo=app.state.repository
    with patch('backend.services.preparation.chat_stream',side_effect=creative_provider(calls,conflict=True)):
        wid,jid=submit(client);done=wait(client,jid)
    assert done['status']=='saved',json.dumps(done,ensure_ascii=False)
    assert repo.generation_resources(jid,['prompt'])['prompt']['version']=='initial-world-stages-6'
    assert calls.count('interpret')==1
    draft=repo.draft(wid,True)
    assert any('Авторское замечание' in w for w in draft['validation']['warnings'])
    assert 'Авторское замечание' not in json.dumps(repo.draft(wid),ensure_ascii=False)
    saved=repo.confirm_draft(wid,draft['revision'],draft['version_id'])
    state=repo.get_snapshot(saved['save'])['world_state']
    assert state['meta']['world_time']==6120
    assert len(state['knowledge'])==2
    assert not state['characters'][state['camera']['controlled_actor_id']]['intentions']


def test_rich_blueprint_preserves_family_business_and_knowledge(api):
    from test_initial_world_rich_brief import interpreted,provider,BRIEF as RICH
    client,app=api;calls=[]
    with patch('backend.services.preparation.chat_stream',side_effect=creative_provider(calls,interpreted(),provider(calls))):
        wid,jid=submit(client,RICH);done=wait(client,jid)
    assert done['status']=='saved',json.dumps(done,ensure_ascii=False)
    repo=app.state.repository;draft=repo.draft(wid,True)
    save=repo.confirm_draft(wid,draft['revision'],draft['version_id'])
    state=repo.get_snapshot(save['save'])['world_state']
    assert len(state['characters'])==7 and len(state['organizations'])==6
    assert len(state['knowledge'])==3
    assert {r['kind'] for r in state['objective_relations'].values()}=={'adoptive_parent'}
    assert not state['pregnancies'] and state['meta']['world_time']==6120


def test_completed_fragment_is_reused_after_later_fragment_failure(api):
    client,app=api;calls=[];base=creative_provider(calls)
    def failed(**kw):
        data=json.loads(kw['messages'][-1]['content'])
        if data.get('known_entities'):raise RuntimeError('private provider failure')
        yield from base(**kw)
    with patch('backend.services.preparation.chat_stream',side_effect=failed):
        wid,jid=submit(client,BRIEF+'\n'+'Дополнительные подробности. '*300)
        assert wait(client,jid)['status']=='failed'
    repo=app.state.repository
    before=repo.inspect_generation_checkpoint(jid,'interpret_0',True)['artifact_version']
    with patch('backend.services.preparation.chat_stream',side_effect=base):
        r=client.post(f'/api/jobs/{jid}/generation/resume',json={'revision':repo.generation_status(jid)['revision'],'api_key':'fixture'})
        assert r.status_code==200,r.text
        done=wait(client,jid)
    assert done['status']=='saved',json.dumps(done,ensure_ascii=False)
    assert repo.inspect_generation_checkpoint(jid,'interpret_0',True)['artifact_version']==before


def test_new_pipeline_obeys_temporal_guard_and_history(api,monkeypatch):
    import test_world_generation as legacy
    original=legacy.fake_stages
    monkeypatch.setattr(legacy,'fake_stages',lambda calls:creative_provider(calls,provider=original(calls)))
    legacy.test_generated_world_obeys_merged_temporal_guard_through_history(api)


def test_author_repairs_family_knowledge_and_opening_with_canonical_forms(api):
    client,app=api;calls=[];repo=app.state.repository
    with patch('backend.services.preparation.chat_stream',side_effect=creative_provider(calls)):
        wid,jid=submit(client);assert wait(client,jid)['status']=='saved'
    endpoint=f'/api/workspaces/{wid}/draft'
    assert client.get(endpoint+'/canonical').status_code==409
    data=client.get(endpoint+'/canonical?author=true').json()
    assert {'organizations','objective_relations','knowledge','initial_history','calendar'}<=data['values'].keys()
    names={r['name']:r['id'] for r in data['references']}
    def edit(section,value):
        rev=repo.draft(wid,True)['revision']
        return client.patch(endpoint,json=dict(operation='patch',kind='canonical',field=section,value=value,revision=rev,warnings_ack=True))
    org={'institute':dict(id='institute',name='НИИ системных исследований')}
    assert edit('organizations',org).status_code==200
    relations=data['values']['objective_relations']
    relations['adoption']['kind']='parent'
    assert edit('objective_relations',relations).status_code==200
    knowledge=data['values']['knowledge'];knowledge.pop(names['Мира']+':adoption')
    assert edit('knowledge',knowledge).status_code==200
    camera=data['values']['camera'];camera['situation']='Мира ждёт на платформе.'
    assert edit('camera',camera).status_code==200
    before=repo.draft(wid,True)['version_id']
    bad={**knowledge,'missing:adoption':dict(actor_id='missing',fact_id='adoption',status='known')}
    assert edit('knowledge',bad).status_code==409
    assert repo.draft(wid,True)['version_id']==before
    draft=repo.draft(wid,True);saved=repo.confirm_draft(wid,draft['revision'],draft['version_id'])
    from backend.repositories.preparation import Repository
    state=Repository(repo.path).get_snapshot(saved['save'])['world_state']
    assert state['organizations']['institute']['name']=='НИИ системных исследований'
    assert state['objective_relations']['adoption']['kind']=='parent'
    assert names['Мира']+':adoption' not in state['knowledge']
    assert state['camera']['situation']=='Мира ждёт на платформе.'


def test_exhausted_budget_requires_explicit_reset_and_retains_checkpoints(api):
    client,app=api;repo=app.state.repository;calls=[];base=creative_provider(calls)
    def broken(**kw):
        if '\nStage: places' in kw['messages'][0]['content']:
            yield '{broken json';return
        yield from base(**kw)
    with patch('backend.services.preparation.chat_stream',side_effect=broken):
        wid,jid=submit(client);assert wait(client,jid)['status']=='failed'
        rev=repo.generation_status(jid)['revision']
        assert client.post(f'/api/jobs/{jid}/generation/resume',json={'revision':rev,'api_key':'fixture'}).status_code==200
        assert wait(client,jid)['status']=='failed'
    status=repo.generation_status(jid)
    assert not status['can_resume'] and status['exhausted_units']==['places']
    unchanged=repo.inspect_generation_checkpoint(jid,'setting',True)['artifact_version']
    assert client.post(f'/api/jobs/{jid}/generation/resume',json={'revision':status['revision'],'api_key':'fixture'}).status_code==409
    with patch('backend.services.preparation.chat_stream',side_effect=base):
        response=client.post(f'/api/jobs/{jid}/generation/retry',json={'revision':status['revision'],'api_key':'fixture'})
        assert response.status_code==200,response.text
        assert wait(client,jid)['status']=='saved'
    assert repo.inspect_generation_checkpoint(jid,'setting',True)['artifact_version']==unchanged
    unit=next(u for u in repo.generation_status(jid)['units'] if u['unit_id']=='places')
    assert unit['attempts']==4 and unit['retry_attempts']==1
    with repo.connect() as db:
        assert db.execute("SELECT count(*) FROM document_versions WHERE kind='generation_retry' AND owner=?",(jid,)).fetchone()[0]==1


def test_pause_edit_split_family_stage_invalidates_dependents_not_characters(api):
    from test_generation_edits import checkpoint_body
    client,app=api;repo=app.state.repository;calls=[];base=creative_provider(calls)
    original=repo.commit_generation_unit
    def pause(jid,token,unit,payload):
        value=original(jid,token,unit,payload)
        if unit=='opening':repo.generation_control(jid,'pause')
        return value
    with patch('backend.services.preparation.chat_stream',side_effect=base),patch.object(repo,'commit_generation_unit',side_effect=pause):
        wid,jid=submit(client);assert wait(client,jid)['status']=='paused'
    unchanged=repo.inspect_generation_checkpoint(jid,'core_0',True)['artifact_version']
    body=checkpoint_body(repo,jid,'life_ties','/objective_relations/adoption/kind','parent')
    response=client.patch(f'/api/workspaces/{wid}/draft',json=body)
    assert response.status_code==200,response.text
    with patch('backend.services.preparation.chat_stream',side_effect=base):
        r=client.post(f'/api/jobs/{jid}/generation/resume',json={'revision':repo.generation_status(jid)['revision'],'api_key':'fixture'})
        assert r.status_code==200,r.text
        done=wait(client,jid)
    assert done['status']=='saved',json.dumps(done)
    assert repo.inspect_generation_checkpoint(jid,'core_0',True)['artifact_version']==unchanged
    assert repo.generation_resources(jid,['life'])['life']['objective_relations']['adoption']['kind']=='parent'


def short_provider(calls):
    def stream(**kw):
        stage=kw['messages'][0]['content'].split('\nStage: ')[1].split('\n')[0]
        data=json.loads(kw['messages'][-1]['content']);calls.append(stage)
        if stage=='interpret':result=dict(entities=[dict(key='ilya',kind='character',name='Илья',tier='protagonist')],notes=[dict(section='setting',text='Переезд в Москву и работа в НИИ; повседневность, романтика, юмор, драма.')])
        elif stage=='setting':result=dict(campaign={'title':'Новая жизнь','setting':'Москва, будни научного института'},entities=[dict(key='ilya',existing_id=data['interpretation']['entities'][0]['id'],kind='character',name='Илья',tier='protagonist'),dict(key='vera',kind='character',name='Вера',tier='core'),dict(key='oleg',kind='character',name='Олег',tier='secondary'),dict(key='institute',kind='organization',name='НИИ городских систем'),dict(key='lab',kind='location',name='Лаборатория'),dict(key='cafe',kind='location',name='Кафе рядом с НИИ')])
        elif stage=='review':result={'findings':[dict(claim_id=c['id'],verdict='preserved',explanation='Соответствует замыслу') for c in data['claims']]}
        else:
            ids={r['key'] if 'key' in r else r['name']:r['id'] for r in data['registry']}
            names={r['name']:r['id'] for r in data['registry']};lab=names['Лаборатория']
            if stage=='places':result=dict(locations={names[n]:dict(id=names[n],name=n) for n in ('Лаборатория','Кафе рядом с НИИ')},organizations={names['НИИ городских систем']:dict(id=names['НИИ городских систем'],name='НИИ городских систем')})
            elif stage=='characters':
                result={'characters':{},'cards':{}}
                for row in data['registry']:
                    cid=row['id'];name=row['name']
                    if cid not in data['assigned_ids']:continue
                    actor=dict(id=cid,display_name=name,location_id=lab)
                    if name!='Илья':actor.update(personality={'items':{'voice':dict(field='communication',text='Сухой юмор и точность' if name=='Вера' else 'Общительный и нетерпеливый')}},goals=[dict(id='goal_'+cid,text='Защитить свой исследовательский проект' if name=='Вера' else 'Освоить новый метод анализа')])
                    result['characters'][cid]=actor
                    result['cards'][cid]=dict(id=cid,name=name,fields={'Предыстория':'Несколько лет изучает транспортные системы' if name=='Вера' else 'Недавно окончил аспирантуру' if name=='Олег' else 'Переехал в Москву'})
            elif stage in ('ties','circumstances','background','knowledge'):result={}
            elif stage=='opening':result=dict(world_time=540,camera=dict(mode='actor',controlled_actor_id=names['Илья'],pov_actor_id=names['Илья'],location_id=lab,present_character_ids=[names['Илья'],names['Вера']],situation='Утро в лаборатории. Вера разбирает распечатки рядом со свободным столом.'))
            else:raise AssertionError(stage)
        yield json.dumps(result,ensure_ascii=False)
    return stream


def test_short_idea_expands_to_distinct_cast_and_playable_world(api):
    client,app=api;repo=app.state.repository;calls=[]
    with patch('backend.services.preparation.chat_stream',side_effect=short_provider(calls)):
        wid,jid=submit(client,'Молодой парень Илья переезжает в Москву, устраивается в НИИ и пытается начать новую жизнь. Повседневность, романтика, юмор и драма.')
        done=wait(client,jid)
    assert done['status']=='saved',json.dumps(done,ensure_ascii=False)
    draft=repo.draft(wid,True);save=repo.confirm_draft(wid,draft['revision'],draft['version_id'])['save']
    initial=repo.get_snapshot(save);state=initial['world_state'];hero=state['camera']['controlled_actor_id']
    assert len(state['characters'])==3 and len(state['locations'])==2 and len(state['organizations'])==1
    npcs=[a for cid,a in state['characters'].items() if cid!=hero]
    assert len({a['personality']['items']['voice']['text'] for a in npcs})==2
    assert len({a['goals'][0]['text'] for a in npcs})==2
    assert not state['characters'][hero]['intentions'] and not state['scheduled_events']
    assert 'spans' not in json.dumps(initial['campaign']['initial_world'])
    from test_temporal_guard import run
    assert run(repo,save,1,kind='start')[0]['status']=='saved'
    assert run(repo,save,2)[0]['status']=='saved'
    from backend.repositories.preparation import Repository
    assert Repository(repo.path).get_snapshot(save)==repo.get_snapshot(save)


def test_standalone_interpretation_uses_blueprint_without_source_anchors(api):
    client,app=api
    wid=client.post('/api/workspaces',json={'name':'Preview'}).json()['id']
    raw=blueprint_of(interpretation())
    with patch('backend.services.preparation.chat_stream',return_value=iter([json.dumps(raw)])):
        response=client.post(f'/api/workspaces/{wid}/draft/generate',json=dict(task='interpret',text=BRIEF,revision=0,config=REMOTE,api_key='fixture'))
        done=wait(client,response.json()['id'])
    assert done['status']=='saved',done
    plan=app.state.repository.interpretation(wid,True)['plan']
    assert plan['version']==2 and plan['brief']==BRIEF
    assert 'spans' not in json.dumps(plan)


def test_blueprint_circumstance_revision_preserves_original_and_scoped_work(api):
    from test_generation_edits import checkpoint_body
    client,app=api;repo=app.state.repository;calls=[];base=creative_provider(calls)
    commit=repo.commit_generation_unit
    def pause(jid,token,unit,payload):
        result=commit(jid,token,unit,payload)
        if unit=='opening':repo.generation_control(jid,'pause')
        return result
    with patch('backend.services.preparation.chat_stream',side_effect=base),patch.object(repo,'commit_generation_unit',side_effect=pause):
        wid,jid=submit(client);assert wait(client,jid)['status']=='paused'
    plan=repo.generation_resources(jid,['interpretation'])['interpretation']
    index=next(i for i,c in enumerate(plan['claims']) if c['section']=='knowledge')
    invalid=checkpoint_body(repo,jid,'interpret',f'/claims/{index}/classification','invalid',warnings_ack=True)
    assert client.patch(f'/api/workspaces/{wid}/draft',json=invalid).status_code==409
    body=checkpoint_body(repo,jid,'interpret',f'/claims/{index}/description','Мира узнала только сегодня.',warnings_ack=True)
    before=repo.inspect_generation_checkpoint(jid,'core_0',True)['artifact_version']
    response=client.patch(f'/api/workspaces/{wid}/draft',json=body)
    assert response.status_code==200,response.text
    after=repo.generation_resources(jid,['interpretation'])['interpretation']
    assert after['brief']==BRIEF and after['amendments'][-1]['value']=='Мира узнала только сегодня.'
    assert repo.inspect_generation_checkpoint(jid,'core_0',True)['artifact_version']==before
    assert repo.inspect_generation_checkpoint(jid,'core_0',True)['status']=='completed'


def test_schema_diagnostics_do_not_echo_secret_input(api):
    client,app=api;calls=[];base=creative_provider(calls)
    def invalid(**kw):
        if '\nStage: ties' in kw['messages'][0]['content']:
            yield json.dumps({'objective_relations':{'bad':{'id':'bad','kind':'private-secret-api-key'}}});return
        yield from base(**kw)
    with patch('backend.services.preparation.chat_stream',side_effect=invalid):
        wid,jid=submit(client);done=wait(client,jid)
    assert done['status']=='failed'
    assert 'private-secret-api-key' not in json.dumps(done)
    unit=next(u for u in done['generation']['units'] if u['unit_id']=='life_ties')
    assert unit['error_kind']=='schema'
    assert 'literal_error' in unit['error']


def test_blueprint_identity_and_origin_do_not_depend_on_quote_matching():
    raw=dict(entities=[dict(key='one',kind='character',name='Саша'),dict(key='two',kind='character',name='Саша')],notes=[dict(origin=origin,section='personality',text='Свободное описание',subject_key='one') for origin in ('explicit','generated','unknown')])
    plan=blueprint.accept(raw,'Саша встречает другого Сашу.','workspace',1)
    assert len({e['id'] for e in plan['entities']})==2
    assert [n['classification'] for n in plan['claims']]==['explicit','inferred','open']
    raw['notes'][0]['holder_keys']=['missing']
    with pytest.raises(ValueError,match='unknown entity reference'):
        blueprint.accept(raw,'Любой текст','workspace',1)


def test_medium_idea_keeps_multiple_organizations_ties_and_backstory(api):
    client,app=api;repo=app.state.repository;calls=[];base=short_provider(calls)
    brief='Илья переехал в Москву. Вера и Олег — коллеги в НИИ городских систем. Олег также сотрудничает с Городским университетом. В прошлом году Вера и Олег вместе провели исследование транспорта.'
    def provider(**kw):
        stage=kw['messages'][0]['content'].split('\nStage: ')[1].split('\n')[0]
        data=json.loads(kw['messages'][-1]['content'])
        raw=json.loads(''.join(base(**kw)))
        if stage=='interpret':
            raw['notes'] += [dict(section='relationship',text='Вера и Олег — коллеги.'),dict(section='history',text='В прошлом году Вера и Олег вместе исследовали транспорт.',time_scope='В прошлом году')]
        elif stage=='setting':raw['entities'].append(dict(key='university',kind='organization',name='Городской университет'))
        elif stage in ('places','ties','background','knowledge'):
            names={r['name']:r['id'] for r in data['registry']}
            if stage=='places':raw['organizations'][names['Городской университет']]=dict(id=names['Городской университет'],name='Городской университет')
            elif stage=='ties':raw={'objective_relations':{'colleagues':dict(id='colleagues',kind='coworker',source_id=names['Вера'],target_id=names['Олег'])}}
            elif stage=='background':raw={'facts':{'research':dict(id='research',text='В прошлом году Вера и Олег вместе провели исследование транспорта.',character_ids=[names['Вера'],names['Олег']])}}
            else:raw={'knowledge':{names[n]+':research':dict(actor_id=names[n],fact_id='research',status='known',evidence='Участник исследования') for n in ('Вера','Олег')}}
        yield json.dumps(raw,ensure_ascii=False)
    with patch('backend.services.preparation.chat_stream',side_effect=provider):
        wid,jid=submit(client,brief);done=wait(client,jid)
    assert done['status']=='saved',json.dumps(done,ensure_ascii=False)
    draft=repo.draft(wid,True);saved=repo.confirm_draft(wid,draft['revision'],draft['version_id'])
    state=repo.get_snapshot(saved['save'])['world_state']
    assert len(state['characters'])==3 and len(state['organizations'])==2
    assert state['objective_relations']['colleagues']['kind']=='coworker'
    assert len(state['knowledge'])==2
    assert state['facts']['research']['text'].startswith('В прошлом году')
    assert not state['scheduled_events']


def test_periodic_recovery_cannot_steal_locally_dispatched_unleased_job(api):
    import threading
    from backend.services.credentials import Credentials
    client,app=api;repo=app.state.repository;calls=[]
    entered=threading.Event();proceed=threading.Event();claim=repo.claim_generation
    def delayed_claim(*args,**kwargs):
        entered.set()
        assert proceed.wait(5)
        return claim(*args,**kwargs)
    with patch('backend.services.preparation.chat_stream',side_effect=creative_provider(calls)),patch.object(repo,'claim_generation',side_effect=delayed_claim):
        wid,jid=submit(client)
        try:
            assert entered.wait(5)
            app.state.preparation.recover_generations(Credentials(repo))
            assert repo.preparation_job(jid)['status']=='generating'
            assert repo.generation_status(jid)['revision']==0
        finally:proceed.set()
        done=wait(client,jid)
    assert done['status']=='saved',done
    assert repo.generation_status(jid)['revision']==0
    assert calls.count('interpret')==1
