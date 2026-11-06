import json
from copy import deepcopy
import pytest
from test_api import api
from secret183_fixture import start, SONYA, MAXIM, OWN, WORLD, PRIVATE
from backend.runtime_v3.secrets import projection, spoiler_projection


def test_start_handoff_own_knowledge_pov_and_readonly_spoilers(api):
    client,app=api;repo=app.state.repository
    selected=start(client,repo);sid=selected['save'];path=f'/api/saves/{sid}'
    before=repo.get_snapshot(sid)
    response=client.get(path);view=response.json();rev=view['revision']
    assert OWN in response.text
    for text in (SONYA, MAXIM, WORLD, PRIVATE,'fact_sonya_love','fact_maxim_sale','world183','private183'):
        assert text not in response.text
    own=view['state']['story_secrets']['personal']['ilya']
    own_row=next(r for r in own if r['status']=='known')
    assert own_row['category']=='own' and own_row['audience']=={'known':['ilya'],'suspected':[]}
    assert all(set(r)=={'id','status'} for r in own if r['status']=='hidden')
    assert not view['state']['notification_history']
    state=before['world_state']
    assert state['knowledge']['ilya:own181']['status']=='known'
    assert state['knowledge']['sonya:own181']['status']=='unknown'
    from backend.runtime_v3.context import build_context
    context=build_context(before, [], 'Вспоминаю свою музыку.', 'turn', 32768, 4096)
    context_text=json.dumps(context,ensure_ascii=False)
    assert OWN in context_text
    # Narrative authors NPCs too, with explicitly scoped Knowledge; reading spoilers
    # must not change any of these context inputs.
    for cid in ('ilya','sonya','maxim',None):
        query=f'?revision={rev}'+('&character_id='+cid if cid else '')
        response=client.get(path+'/story-secret-spoilers'+query)
        assert response.status_code==200,response.text
        assert response.headers['cache-control']=='no-store'
        rows=response.json()['rows'];text=response.text
        assert PRIVATE not in text
        assert not any(k in text for k in ('AUTHOR_EVIDENCE_181','PRIVATE_NOTEBOOK_181','source_event_id','fact_sonya_love'))
        assert (WORLD in text)==(cid is None)
        assert (SONYA in text)==(cid in (None,'ilya','sonya'))
        assert (MAXIM in text)==(cid in (None,'sonya','maxim'))
        assert len({r['id'] for r in rows})==len(rows)
        for r in rows:
            if r['text']==OWN:
                assert r['slot_id']==own_row['id']
            if r['text']==MAXIM:
                assert r['audience']=={'known':['maxim'],'suspected':['ilya']}
                assert {'id':r['slot_id'],'status':'hidden'} in view['state']['story_secrets']['personal']['sonya']
            if r['text'].startswith(WORLD):
                assert 'slot_id' not in r and r['audience']=={'known':[],'suspected':[]}
    assert repo.get_snapshot(sid)==before
    assert build_context(repo.get_snapshot(sid), [], 'Вспоминаю свою музыку.', 'turn', 32768, 4096)==context
    assert client.get(path).json()==view
    assert client.get(path+'/story-secret-spoilers').status_code==422
    assert client.get(path+f'/story-secret-spoilers?revision={rev+1}').status_code==409
    assert client.get(path+f'/story-secret-spoilers?revision={rev}&character_id=missing').status_code==409
    for index,(operation,cid) in enumerate([('temporary','sonya'),('temporary','ilya'),('observe','sonya'),('resume','ilya')]):
        rev=client.get(path).json()['revision']
        change=client.post(path+'/protagonist',json=dict(revision=rev,operation_id=f'switch183-{index}',operation=operation,actor_id=cid))
        assert change.status_code==200,change.text
        response=client.get(path);v=response.json()
        assert (SONYA in response.text)==(cid=='sonya' and operation=='temporary')
        assert (OWN in response.text)==(cid=='ilya')
        assert MAXIM not in response.text and WORLD not in response.text
        assert not v['state']['notification_history']
        if cid=='sonya' and operation=='temporary':
            rows=v['state']['story_secrets']['personal']['sonya']
            assert next(r for r in rows if r.get('text')==SONYA)['category']=='own'
            assert any(r['status']=='hidden' for r in rows)
        assert client.get(path+f'/story-secret-spoilers?revision={rev}').status_code==409
    from backend.api.app import create_app
    from fastapi.testclient import TestClient
    reopened=TestClient(create_app(repo.path,recover=False))
    assert reopened.get(path).json()['state']['story_secrets']==client.get(path).json()['state']['story_secrets']


@pytest.mark.parametrize('extra', [False,True])
def test_create_protagonist_own_secret_empty_and_duplicate_holders(api,extra):
    from backend.services.protagonist_creation import empty_draft
    client,app=api;repo=app.state.repository
    sid=start(client,repo)['save'];path=f'/api/saves/{sid}'
    snap=repo.get_snapshot(sid);d=empty_draft(snap,'biography183');cid=d['character']['id']
    d['card']['name']='Новый герой';d['character']['location_id']=snap['world_state']['camera']['location_id'];d['starting_scene']='В гостиной.'
    d['secrets']=[dict(text='БИОГРАФИЧЕСКАЯ_ТАЙНА_183',holders=[cid,'sonya',cid] if extra else [],evidence='Подтверждённая биография',approved=True)]
    response=client.post(path+'/protagonist',json=dict(revision=client.get(path).json()['revision'],operation_id='biography183',operation='permanent',draft=d))
    assert response.status_code==200,response.text
    canonical=repo.get_snapshot(sid);s=canonical['world_state']
    fact=next(f for f in s['facts'].values() if f['text']=='БИОГРАФИЧЕСКАЯ_ТАЙНА_183');fid=fact['id']
    assert fact['story_secret'] and fact['secret_keeper_ids']==[cid] and fact['secret_subject_ids']==[cid]
    beliefs=[k for k in s['knowledge'].values() if k['fact_id']==fid]
    assert {k['actor_id'] for k in beliefs}==({cid,'sonya'} if extra else {cid})
    assert len(beliefs)==(2 if extra else 1) and all(k['status']=='known' for k in beliefs)
    game=client.get(path)
    assert fact['text'] in game.text and not game.json()['state']['notification_history']
    assert projection(s)['personal'][cid][0]['category']=='own'
    # Reproduce exactly the old bug in the saved snapshot, preserving its original
    # creation receipt/source events. Reads repair only this proven provenance.
    broken=deepcopy(canonical);bf=broken['world_state']['facts'][fid]
    bf.update(story_secret=False,secret_subject_ids=[]);bf.pop('secret_keeper_ids')
    broken['world_state']['knowledge'].pop(cid+':'+fid)
    with repo.connect() as db:
        db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(broken),sid))
        history_before=[tuple(r) for r in db.execute('SELECT * FROM world_history_v3')]
    repaired=repo.get_snapshot(sid)
    assert repaired['world_state']['knowledge'][cid+':'+fid]['status']=='known'
    assert fact['text'] in client.get(path).text
    with repo.connect() as db:
        assert json.loads(db.execute('SELECT state_json FROM saves WHERE id=?',(sid,)).fetchone()[0])==broken
        assert [tuple(r) for r in db.execute('SELECT * FROM world_history_v3')]==history_before
    # Actual engine preparation sees the same repaired canonical Knowledge,
    # including legacy saves whose raw row still lacks the owner's record.
    from unittest.mock import patch
    import engine
    from test_narrative_test_world import CONFIG
    from secret_handoff181_fixture import payload
    data=payload(repaired,False)
    def stream(**kw):yield json.dumps(data,ensure_ascii=False) if kw.get('response_format') else 'Вечер в гостиной.'
    jid=repo.begin_job(sid,'','start',CONFIG)
    assert json.loads(repo.get_job(jid)['before_json'])['world_state']['knowledge'][cid+':'+fid]['status']=='known'
    with patch('engine.find_loaded_model',return_value={'config':{'context_length':32768}}),patch('engine.chat_stream',side_effect=stream):
        engine.run_job(repo.path,jid,engine.Worker())
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    assert repo.get_snapshot(sid)['world_state']['knowledge'][cid+':'+fid]['status']=='known'
    assert not client.get(path).json()['state']['notification_history']
    # A later refutation wins, and ambiguous imported data is never guessed.
    broken['world_state']['knowledge'][cid+':'+fid]=dict(s['knowledge'][cid+':'+fid],status='refuted')
    with repo.connect() as db:db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(broken),sid))
    assert repo.get_snapshot(sid)['world_state']['knowledge'][cid+':'+fid]['status']=='refuted'
    assert fact['text'] not in client.get(path).text
    broken['history_head']=None;broken['world_state']['knowledge'].pop(cid+':'+fid)
    with repo.connect() as db:db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(broken),sid))
    assert cid+':'+fid not in repo.get_snapshot(sid)['world_state']['knowledge']


def test_ownership_not_inferred_and_runtime_never_regrants():
    from backend.runtime_v3.migration import migrate_v2
    from backend.services.draft_initial import inspect_candidate
    from secret183_fixture import candidate
    raw=candidate();fact=raw['world']['facts']['world183']
    fact.update(owner_id='ilya',secret_subject_ids=['ilya'],character_ids=['ilya'])
    prepared,report=inspect_candidate(raw)
    assert not report['errors'],report
    snap=migrate_v2(prepared).snapshot;s=snap['world_state']
    assert 'ilya:world183' not in s['knowledge']
    for status in ['unknown','suspected','refuted','outdated','superseded']:
        s['knowledge']['ilya:own181']['status']=status
        normalized=migrate_v2(snap).snapshot['world_state']
        assert normalized['knowledge']['ilya:own181']['status']==status
        assert all(r.get('text')!=OWN for r in projection(normalized)['personal'].get('ilya',[]))
    raw['world']['knowledge']['ilya:own181']=dict(actor_id='ilya',fact_id='own181',status='unknown')
    assert inspect_candidate(raw)[1]['errors']


def test_creative_and_manual_authoring_share_keeper_contract():
    from backend.services.draft_initial import inspect_candidate, prompt_schema
    from backend.services.draft_changes import apply_proposal
    from backend.services.draft_world import patch, dependencies
    from backend.repositories.drafts import candidate_hash
    from secret183_fixture import candidate
    state,report=inspect_candidate(candidate())
    assert not report['errors']
    assert 'secret_keeper_ids' in prompt_schema()['properties']['world']['properties']['facts']['additionalProperties']['properties']
    fact=dict(id='creative183',text='Соня скрывает своё авторство картины.',secret=True,story_secret=True,
        character_ids=['ilya'],secret_subject_ids=['ilya'],secret_keeper_ids=['sonya'],secret_existence='hidden',evidence=[])
    proposal=dict(candidate_hash=candidate_hash(state),rationale='Личное авторство, а не знание субъекта.',
        changes=[dict(op='add',path='/world/facts/creative183',value=fact,reason='Развить биографию Сони.')])
    changed,_=apply_proposal(state,json.dumps(proposal))
    assert changed['world']['knowledge']['sonya:creative183']['status']=='known'
    assert 'ilya:creative183' not in changed['world']['knowledge']
    assert 'creative183' not in state['world']['facts']
    # Manual authoring uses the same typed field and dependency graph; removal
    # must not leave dangling keeper references, including non-subject keepers.
    assert any('creative183' in str(d) for d in dependencies(changed,'character','sonya'))
    patched=patch(changed,'fact','creative183','secret_keeper_ids',['sonya','maxim'])
    assert patched['world']['knowledge']['maxim:creative183']['status']=='known'


def test_unknown_keeper_birth_cannot_leak_through_fact_metadata():
    from backend.runtime_v3.secrets import visible_fact_ids
    from backend.runtime_v3.migration import migrate_v2
    from backend.services.draft_initial import inspect_candidate
    from secret183_fixture import candidate
    from unittest.mock import patch
    snapshot=migrate_v2(inspect_candidate(candidate())[0]).snapshot
    s=snapshot['world_state']
    s['facts']['own181']['secret_keeper_ids'].append('sonya')
    # Reuse the canonical birth visibility predicate: the new reference must be
    # checked by BOTH slot and raw fact projections, not only the dossier.
    with patch('backend.runtime_v3.reproduction.known_birth',side_effect=lambda state,cid,actor:cid!='sonya'):
        assert 'own181' not in visible_fact_ids(s)
        assert not any(r.get('fact_id')=='own181' for rows in projection(s)['personal'].values() for r in rows)
        assert 'slot_id' not in next(r for r in spoiler_projection(snapshot,'ilya') if r['text']==OWN)


def test_audience_and_slot_follow_current_actor_and_beliefs():
    from backend.runtime_v3.migration import migrate_v2
    from backend.services.draft_initial import inspect_candidate
    from secret183_fixture import candidate
    snapshot=migrate_v2(inspect_candidate(candidate())[0]).snapshot
    s=snapshot['world_state']

    def spoiler():
        return next(r for r in spoiler_projection(snapshot,'ilya') if r['text']==OWN)

    def ordinary():
        return next(r for r in projection(s)['personal']['ilya'] if r.get('text')==OWN)

    # A subject is not a knower, and an actual knower need not be a keeper or subject.
    s['facts']['own181']['secret_subject_ids'].append('maxim')
    s['knowledge']['sonya:own181']['status']='known'
    s['characters']['sonya']['display_name']='Софья'
    ilya_slot=ordinary()['id']
    assert ordinary()['audience']=={'known':['ilya'],'suspected':[]}
    assert sorted(spoiler()['audience']['known'])==['ilya','sonya']
    assert spoiler()['audience']['suspected']==[]

    s['camera']['controlled_actor_id']='sonya'
    assert ordinary()['id']==spoiler()['slot_id']!=ilya_slot
    assert ordinary()['audience']=={'known':['sonya'],'suspected':[]}
    for status in ('suspected','refuted','superseded','outdated','unknown'):
        s['knowledge']['ilya:own181']['status']=status
        assert spoiler()['audience']=={'known':['sonya'],'suspected':['ilya'] if status=='suspected' else []}
        assert ordinary()['audience']=={'known':['sonya'],'suspected':[]}

    s['camera']['controlled_actor_id']=None
    assert projection(s)==dict(personal={},world=[])
    assert 'slot_id' not in spoiler()


def test_semantic_scope_and_stable_audience_ids():
    from backend.runtime_v3.migration import migrate_v2
    from backend.services.draft_initial import inspect_candidate
    from secret183_fixture import candidate
    raw=candidate()
    snapshot=migrate_v2(inspect_candidate(raw)[0]).snapshot
    rows=spoiler_projection(snapshot,'ilya')
    love=next(r for r in rows if r['text']==SONYA)
    assert love['category']=='related'
    assert love['audience']['known']==['sonya']
    s=snapshot['world_state']
    s['knowledge']['ilya:fact_sonya_love']['status']='known'
    assert next(r for r in spoiler_projection(snapshot,'ilya') if r['text']==SONYA)['category']=='known'


def test_biography_authoring_api_scope_and_pov(api):
    from secret183_fixture import BIO, KNOWN
    from backend.services.draft_world import patch, dependencies
    from backend.services.draft_initial import inspect_candidate
    from secret183_fixture import candidate
    client,app=api;repo=app.state.repository
    sid=start(client,repo,semantic=True)['save'];path=f'/api/saves/{sid}'
    snapshot=repo.get_snapshot(sid);s=snapshot['world_state']
    assert s['facts']['circumstance183']['secret_biography_ids']==['ilya']
    assert 'ilya:circumstance183' not in s['knowledge']
    view=client.get(path);v=view.json();rev=v['revision']
    assert BIO not in view.text and 'circumstance183' not in view.text
    personal=v['state']['story_secrets']['personal']
    assert next(r for r in personal['ilya'] if r.get('text')==KNOWN)['category']=='known'
    assert all(set(r)=={'id','status'} for rows in personal.values() for r in rows if r['status']=='hidden')
    rows=client.get(path+f'/story-secret-spoilers?revision={rev}&character_id=ilya').json()['rows']
    categories={r['text']:r['category'] for r in rows}
    assert {k:categories[k] for k in [OWN,KNOWN,SONYA,BIO]}=={OWN:'own',KNOWN:'known',SONYA:'related',BIO:'biography'}
    assert next(r for r in rows if r['text']==KNOWN)['audience']['known']==['ilya','maxim']
    assert repo.get_snapshot(sid)==snapshot
    changed=client.post(path+'/protagonist',json=dict(revision=rev,operation='temporary',actor_id='sonya',operation_id='semantic183'))
    assert changed.status_code==200,changed.text
    v=client.get(path).json();rev=v['revision']
    rows=client.get(path+f'/story-secret-spoilers?revision={rev}&character_id=ilya').json()['rows']
    # Dossier classification is about Ilya; the spoiler status is about current POV Sonya.
    known=next(r for r in rows if r['text']==KNOWN)
    assert known['category']=='known' and known['status']=='spoiler'
    assert KNOWN not in client.get(path).text and BIO not in client.get(path).text
    raw,_=inspect_candidate(candidate(semantic=True))
    assert any('circumstance183' in str(d) for d in dependencies(raw,'character','ilya'))
    modified=patch(raw,'fact','circumstance183','secret_biography_ids',['sonya'])
    assert modified['world']['facts']['circumstance183']['secret_biography_ids']==['sonya']
    assert 'sonya:circumstance183' not in modified['world']['knowledge']
    from backend.services.draft_world import validate
    for invalid in [['missing'],['ilya','ilya']]:
        # Draft edits may be incomplete; confirmation validation must reject them.
        assert validate(patch(raw,'fact','circumstance183','secret_biography_ids',invalid))['errors']
    with pytest.raises(ValueError):patch(raw,'fact','circumstance183','secret_biography_ids','ilya')


def test_spoiler_audience_filters_unavailable_characters_and_preserves_ids():
    from backend.runtime_v3.migration import migrate_v2
    from backend.services.draft_initial import inspect_candidate
    from secret183_fixture import candidate
    from unittest.mock import patch
    snapshot=migrate_v2(inspect_candidate(candidate())[0]).snapshot
    s=snapshot['world_state']
    s['characters']['sonya']['display_name']='Илья'  # Deliberate homonyms cannot redirect navigation.
    s['knowledge']['sonya:own181']['status']='known'
    row=next(r for r in spoiler_projection(snapshot,'ilya') if r['text']==OWN)
    assert sorted(row['audience']['known'])==['ilya','sonya']
    with patch('backend.runtime_v3.reproduction.known_birth',side_effect=lambda state,cid,actor:cid!='sonya'):
        row=next(r for r in spoiler_projection(snapshot,'ilya') if r['text']==OWN)
        assert row['audience']['known']==['ilya']
        with pytest.raises(ValueError):spoiler_projection(snapshot,'sonya')
