import json
from unittest.mock import patch
import pytest

from test_api import api, REMOTE, wait_job
from backend.repositories.preparation import Repository
from backend.services import draft_world
from review_actions_fixture import seed, reply, BIO, DEAD, UNKNOWN, SOURCE, FILLED


def submit(client,url,draft,action,key):
    return client.post(url+'/edits',json=dict(action=action,revision=draft['revision'],request_id=key,
        config=dict(REMOTE,context_length=131072,max_tokens=16000),api_key='offline'))


def provider(calls,transform=None):
    def stream(**kw):
        calls.append(kw['messages'])
        raw=reply(kw['messages'])
        kw['on_usage']({'prompt_tokens':120,'completion_tokens':60})
        kw['on_finish']('stop')
        yield transform(raw) if transform else raw
    return stream


def test_saved_review_fix_read_again_and_restore(api):
    client,app=api;repo=app.state.repository
    wid=seed(repo)['wid'];url=f'/api/workspaces/{wid}/draft'
    def current():return client.get(url+'?author=true').json()
    original=current();calls=[]
    with patch('backend.services.preparation.chat_stream',side_effect=provider(calls)):
        job=submit(client,url,original,'fix','fix1').json()
        assert wait_job(client,job['id'])['status']=='saved'
        assert submit(client,url,original,'fix','fix1').json()['id']==job['id']
        assert len(calls)==1 and current()['version_id']==original['version_id']
        context=json.loads(calls[0][-1]['content'])
        assert context['author_context']['original_idea']==SOURCE
        assert context['calendar_evidence']['character_2']['age']==36
        assert context['candidate']==original['state']
        assert {r['message'] for r in context['findings']} >= {BIO,DEAD,UNKNOWN}
        fresh=Repository(repo.path)
        edit=fresh.world_edits(wid,True)['edits'][0]
        assert edit['status']=='preview',edit.get('failure')
        assert edit['requests'][0]['input_tokens']==120
        assert fresh.world_edits(wid)['edits']==[]
        assert not submit(client,url,current(),'recheck','early').is_success
        body=dict(revision=current()['revision'],decision='accept')
        applied=client.post(url+'/edits/'+job['id'],json=body).json()
        assert client.post(url+'/edits/'+job['id'],json=body).json()['version_id']==applied['version_id']
        assert applied['review']['status']=='stale'
        assert applied['state']['characters'][1]['fields']['Возраст']=='36'
        assert applied['state']['characters'][1]['fields']['Биография']==FILLED
        assert original['state']['world']==applied['state']['world']
        assert not submit(client,url,original,'recheck','stale').is_success
        check=submit(client,url,applied,'recheck','check1').json()
        assert wait_job(client,check['id'])['status']=='saved'
        checked=current()
        assert checked['review']['status']=='completed'
        assert checked['state']==applied['state']
        assert [i['message'] for i in checked['review']['issues']]==[UNKNOWN]
        decisions=checked['review_decisions']
        assert any(d['message']==BIO and d['resolution']=='fixed' for d in decisions)
        assert any(d['message']==DEAD and d['resolution']=='disproved' for d in decisions)
        assert checked['review']['checked_revision']==checked['revision']
        assert len(calls)==2
        assert not client.get(url).json()['review_decisions']
    restored=client.patch(url,json=dict(revision=checked['revision'],operation='restore',source_id=original['version_id'])).json()
    assert restored['state']==original['state'] and restored['review']==original['review']
    assert len({original['version_id'],applied['version_id'],checked['version_id'],restored['version_id']})==4


@pytest.mark.parametrize('bad_path',[
    '/world/characters/character_2/birth_date','/world/facts/ownership/text',
    '/world/characters/character_1/intentions','/campaign/title','/world/events/meeting/minute',
    '/world/knowledge/character_2:meeting/status'])
def test_review_rejects_unsafe_package_and_records_paid_answer(api,bad_path):
    client,app=api;repo=app.state.repository;wid=seed(repo)['wid'];url=f'/api/workspaces/{wid}/draft'
    base=repo.draft(wid,True);calls=[]
    def corrupt(raw):
        packet=json.loads(raw);packet['changes'][-1]['path']=bad_path
        return json.dumps(packet)
    with patch('backend.services.preparation.chat_stream',side_effect=provider(calls,corrupt)):
        job=submit(client,url,base,'fix','unsafe').json()
        assert wait_job(client,job['id'])['status']=='saved'
        edit=repo.world_edits(wid,True)['edits'][0]
        assert edit['status']=='unapplied' and edit['failure']
        assert {o['outcome'] for o in edit['outcomes']}=={'unapplied','ambiguous','disproved'}
        assert not client.post(url+'/resume',json=dict(revision=repo.draft(wid)['revision'],api_key='offline')).is_success
        assert submit(client,url,base,'fix','unsafe').json()['id']==job['id'] and len(calls)==1
        assert repo.draft(wid,True)['state']==base['state']


def test_completed_reply_replayed_after_crash_and_preview_fenced(api):
    client,app=api;repo=app.state.repository;wid=seed(repo)['wid'];url=f'/api/workspaces/{wid}/draft'
    base=repo.draft(wid,True);calls=[]
    with patch('backend.services.preparation.chat_stream',side_effect=provider(calls)):
        with patch.object(repo,'finish_review_action',side_effect=RuntimeError('crash before commit')):
            job=submit(client,url,base,'fix','crash').json()
            assert wait_job(client,job['id'])['status']=='error'
        failed=repo.draft(wid,True)
        assert failed['job']['review_reply_saved']
        assert not submit(client,url,failed,'fix','second-submission').is_success
        with patch('backend.services.preparation.deepseek_key',side_effect=AssertionError('offline recovery')), \
             patch('backend.services.token_budget.prepare',side_effect=AssertionError('no provider preflight')):
            resumed=client.post(url+'/resume',json=dict(revision=failed['revision']))
            assert wait_job(client,job['id'])['status']=='saved'
        assert resumed.is_success and wait_job(client,job['id'])['status']=='saved'
    assert len(calls)==1
    updated=client.patch(url,json=dict(operation='patch',kind='campaign',field='title',value='Новая редакция',revision=repo.draft(wid)['revision'])).json()
    assert not client.post(url+'/edits/'+job['id'],json=dict(revision=updated['revision'],decision='accept')).is_success


def test_incomplete_paid_answer_never_starts_a_continuation(api):
    client,app=api;repo=app.state.repository;wid=seed(repo)['wid'];url=f'/api/workspaces/{wid}/draft'
    base=repo.draft(wid,True);calls=[]
    with patch('backend.services.preparation.chat_stream',side_effect=provider(calls,lambda raw:raw[:80])):
        jid=submit(client,url,base,'fix','short').json()['id']
        assert wait_job(client,jid)['status']=='saved'
    assert len(calls)==1 and repo.world_edits(wid,True)['edits'][0]['status']=='unapplied'
    assert repo.draft(wid,True)['version_id']==base['version_id']


def test_recheck_omissions_and_persistent_date_conflict_are_not_fixes(api):
    client,app=api;repo=app.state.repository;wid=seed(repo)['wid'];url=f'/api/workspaces/{wid}/draft'
    base=repo.draft(wid,True)
    def claims(raw):
        d=json.loads(raw)
        d['decisions']=[i for i in d['decisions'] if i['outcome']!='ambiguous']
        return json.dumps(d)
    with patch('backend.services.preparation.chat_stream',side_effect=provider([],claims)):
        job=submit(client,url,base,'recheck','read').json()
        assert wait_job(client,job['id'])['status']=='saved'
    current=repo.draft(wid,True)
    assert any('/birth_date' in i['message'] for i in current['review']['issues'])
    assert any(i['message']==UNKNOWN for i in current['review']['issues'])
    assert current['state']==base['state']
    assert not any('не задана цель' in m for m in draft_world.review_initial(base['state']))


def test_automatic_birthday_uses_calendar_owned_value_and_keeps_its_provenance(api):
    from backend.services.draft_calendar import complete
    from test_draft_creative import candidate, change
    client,app=api;repo=app.state.repository
    state=candidate()
    card=state['characters'][1]
    card['fields']['Возраст']='25'
    state=complete(state, seed='archive')
    card=state['characters'][1]
    actor=state['world']['characters'][card['id']]
    old=actor['birth_date']
    card['fields']['Возраст']='36'
    state['authoring']['manual_paths']=['/characters/1/fields/Возраст']
    wid=repo.create_workspace('Производная дата')['id']
    with repo.connect() as db:
        repo._write_draft(db,wid,state,'draft_world',source='Автору известно: Марине 36 лет.')
    base=repo.draft(wid,True)
    url=f'/api/workspaces/{wid}/draft'
    calls=[]
    def answer(**kwargs):
        payload=json.loads(kwargs['messages'][-1]['content'])
        target=payload['calendar_evidence'][card['id']]['recalculated_birth_date']
        assert target!=old
        calls.append(target)
        issue=next(i for i in payload['findings'] if '/birth_date' in i['message'])
        yield json.dumps(dict(candidate_hash=payload['candidate_hash'],rationale='Автор установил возраст.',
            changes=[change('/world/characters/'+card['id']+'/birth_date',target,'replace')],
            decisions=[dict(issue_id=issue['issue_id'],outcome='proposed',reason='Дата получена из календаря.',change_indices=[0])]))
    with patch('backend.services.preparation.chat_stream',side_effect=answer):
        job=submit(client,url,base,'fix','date').json()
        assert wait_job(client,job['id'])['status']=='saved'
    proposal=repo.world_edits(wid,True)['edits'][0]
    assert proposal['status']=='preview',proposal
    updated=client.post(url+'/edits/'+job['id'],json=dict(revision=repo.draft(wid)['revision'],decision='accept')).json()
    assert updated['state']['authoring']['calendar_completion']['birth_dates'][card['id']]['value']==calls[0]
    assert updated['state']['world']['characters'][card['id']]['birth_date']==calls[0]
    assert updated['state']['characters'][1]['fields']['Возраст']=='36'
    assert updated['state']['world']['events']==base['state']['world']['events']


def test_two_workers_cannot_dispatch_the_same_paid_request(api):
    from backend.services.preparation import Preparation
    from threading import Event
    client,app=api;repo=app.state.repository
    wid=seed(repo)['wid'];url=f'/api/workspaces/{wid}/draft'
    base=repo.draft(wid,True);gate=Event();entered=Event();calls=[]
    def slow(**kw):
        entered.set()
        assert gate.wait(10)
        yield from provider(calls)(**kw)
    with patch('backend.services.preparation.chat_stream',side_effect=slow):
        try:
            jid=submit(client,url,base,'fix','same').json()['id']
            assert entered.wait(5)
            other=Preparation(Repository(repo.path))
            config=json.loads(repo.preparation_job(jid)['config_json'])
            assert other.submit(wid,'draft_editor',config['_draft_input'],config,base['revision'],'offline')==jid
            assert not other.live(jid)
        finally:
            gate.set()
        assert wait_job(client,jid)['status']=='saved'
    assert len(calls)==1


def test_draft_read_binds_terminal_job_to_its_own_revision(api):
    _,app=api;repo=app.state.repository;wid=seed(repo)['wid']
    from backend.repositories.drafts import candidate_hash
    writer=Repository(repo.path)
    with repo.connect() as db:
        db.execute('PRAGMA journal_mode=WAL')
    base=repo.draft(wid,True)
    cfg=dict(REMOTE,_draft_input='Проверить мир',_editor_request_id='read',_review_action='recheck')
    jid=repo.begin_preparation(wid,'draft_editor','',cfg,base['revision'])
    read_head=repo._draft_head
    def commit_after_read(db,workspace):
        head=read_head(db,workspace)
        writer.finish_review_action(jid,0,dict(status='reviewed',outcomes=[],review=dict(
            status='completed',advisory=True,candidate_hash=candidate_hash(base['state']),issues=[])))
        return head
    with patch.object(repo,'_draft_head',side_effect=commit_after_read):
        overlapping=repo.draft(wid,True)
    assert overlapping['version_id']==base['version_id'] and overlapping['job']['status']=='generating'
    after=repo.draft(wid,True)
    assert after['revision']>overlapping['revision'] and after['job']['status']=='saved'


def test_deceased_character_age_uses_death_date_and_no_goal_quota():
    from test_draft_creative import candidate
    from backend.services.draft_initial import inspect_candidate
    from backend.services.draft_review_actions import calendar_evidence
    state=candidate();card=state['characters'][-1]
    actor=state['world']['characters'][card['id']]
    actor.update(birth_date='1970-02-01',life_status='dead',death_date='2010-03-01')
    card['fields']['Возраст']='40'
    _,report=inspect_candidate(state,for_start=True)
    assert not report['errors'] and not report['semantic_warnings']
    assert calendar_evidence(state)[card['id']]['age']==40
    del actor['death_date']
    assert calendar_evidence(state)[card['id']]['age'] is None
    assert not any('не задана цель' in warning for warning in draft_world.review_initial(state))


def test_record_missing_established_friendship_without_rewriting_evidence(api):
    from backend.services.draft_review_actions import proposal_result
    from test_draft_creative import change
    from backend.repositories.drafts import candidate_hash
    _,app=api;repo=app.state.repository;wid=seed(repo)['wid']
    base=repo.draft(wid,True)['state'];fingerprint=candidate_hash(base)
    packet=dict(candidate_hash=fingerprint,rationale='В авторской истории они давно дружат.',
        decisions=[dict(issue_id='friends',outcome='proposed',reason='Знакомы с детства.',change_indices=[0])],
        changes=[change('/world/objective_relations/friends',dict(id='friends',kind='friend',source_id='character_2',target_id='character_3'))])
    edit=dict(base=dict(state=base),findings=[dict(issue_id='friends',message='Пропущена связь.',paths=[])])
    result=proposal_result(edit,json.dumps(packet))
    assert result['status']=='preview' and 'friends' in result['candidate']['world']['objective_relations']
    assert result['candidate']['world']['knowledge']==base['world']['knowledge']
    assert result['candidate']['world']['events']==base['world']['events']
    assert candidate_hash(base)==fingerprint


def test_archived_candidate_review_and_rollback(api):
    import os
    from pathlib import Path

    archive_path = os.getenv('RPG_GENERATION266_EXPORT')
    if not archive_path:
        pytest.skip('private original supplied separately')
    archive = json.loads(Path(archive_path).read_bytes())
    state = archive['candidate_snapshot']
    report = archive['recovery']['review']
    source = archive['author_input']['source_text']
    client, app = api
    repo = app.state.repository
    wid = repo.create_workspace('Проверка сохранённого кандидата')['id']
    with repo.connect() as db:
        record = dict(state=state, review=report, source=source, generated=True, outline=archive['author_input']['outline'])
        repo._record_document(db, 'world_draft', wid, json.dumps(record, ensure_ascii=False), True, 'draft_world')
        db.execute('UPDATE preparation_workspaces SET revision=revision+1 WHERE id=?', (wid,))
    url = f'/api/workspaces/{wid}/draft'
    original = repo.draft(wid, True)
    reported = {i['message']: i['record_match'] for i in report['issues'][:3]}
    calls = []

    def answer(**kwargs):
        payload = json.loads(kwargs['messages'][-1]['content'])
        assert payload['author_context']['original_idea'] == source
        fix = 'response_schema' in payload
        calls.append(fix)
        changes, decisions = [], []
        for note in payload['findings']:
            if note['message'] not in reported:
                continue
            match = reported[note['message']]
            rid = 'school_' + match['source_id'] + '_' + match['target_id']
            value = dict(id=rid, **match)
            reason = 'Школьная дружба уже записана в биографиях и отношениях.'
            decision = dict(issue_id=note['issue_id'], reason=reason, outcome='fixed')
            if fix:
                assert note['reported_match'] == match
                decision.update(outcome='proposed', change_indices=[len(changes)])
                changes.append(dict(op='add', path='/world/objective_relations/'+rid, value=value, reason=reason))
            else:
                assert all(payload['candidate']['world']['objective_relations'][rid][k]==v for k,v in value.items())
            decisions.append(decision)
        assert len(decisions)==3
        if fix:
            yield json.dumps(dict(candidate_hash=payload['candidate_hash'], rationale=reason, changes=changes, decisions=decisions))
        else:
            yield json.dumps(dict(issues=[], decisions=decisions))

    with patch('backend.services.preparation.chat_stream', side_effect=answer):
        job = submit(client, url, original, 'fix', 'archive-fix').json()
        assert wait_job(client, job['id'])['status']=='saved'
        edit = repo.world_edits(wid, True)['edits'][0]
        assert edit['status']=='preview', edit.get('failure')
        accepted = client.post(url+'/edits/'+job['id'], json=dict(revision=repo.draft(wid)['revision'], decision='accept')).json()
        for key in ('knowledge','events','facts'):
            assert accepted['state']['world'][key] == state['world'][key]
        check = submit(client, url, accepted, 'recheck', 'archive-recheck').json()
        assert wait_job(client, check['id'])['status']=='saved'
        reviewed = repo.draft(wid, True)
        assert reviewed['state']==accepted['state']
        fixed = {d['message'] for d in reviewed['review_decisions'] if d['resolution']=='fixed'}
        assert fixed==set(reported)
        assert set(reported).isdisjoint(i['message'] for i in reviewed['review']['issues'])
        assert len(reviewed['review']['issues']) >= len(report['issues'])-len(reported)
    restored = client.patch(url, json=dict(revision=reviewed['revision'], operation='restore', source_id=original['version_id'])).json()
    assert restored['state']==state and restored['review']==original['review']
    assert calls==[True,False]


def test_still_open_findings_keep_their_original_targets_on_reread():
    from backend.services.draft_review_actions import findings, review_result
    match = dict(kind='friend', source_id='a', target_id='b')
    path = '/world/objective_relations'
    base = dict(state={}, review=dict(issues=[dict(message='Пропущена связь.', path=path, record_match=match),
                                              dict(message='Проверить карточку.', path='/characters/1')]))
    notes = findings(base, {})
    edit = dict(findings=notes, base=base, current_hints=[], calendar_conflicts=[], before_hash='initial')
    # The reviewer repeats one note in prose and omits the other entirely.
    reply = json.dumps(dict(issues=[dict(message=notes[0]['message'])], decisions=[]))
    report = review_result(edit, reply)['review']
    assert findings(dict(state={}, review=report), {}) == notes
