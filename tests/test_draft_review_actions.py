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
    '/world/characters/character_2/birth_date','/world/facts/ownership/not_a_field',
    '/world/characters/character_1/intentions','/world_clock/minute','/world/events/meeting/minute',
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


@pytest.mark.parametrize('basis,expected', [
    (dict(kind='birthday_at_start',quote='Сегодня у Марины день рождения',age_quote='Марине 36 лет'), '1990-10-23'),
    (dict(kind='month_day',month=11,day=27,quote='Её день рождения 27 ноября',age_quote='Марине 36 лет'), '1989-11-27'),
    (dict(kind='year_only',quote='Марина родилась в 1990 году',year=1990), '1990-05-29'),
])
def test_automatic_birthday_resolved_by_author_evidence(api, basis, expected):
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
        repo._write_draft(db,wid,state,'draft_world',source='Марине 36 лет. '+basis['quote']+'.')
    base=repo.draft(wid,True)
    url=f'/api/workspaces/{wid}/draft'
    calls=[]
    def answer(**kwargs):
        payload=json.loads(kwargs['messages'][-1]['content'])
        assert 'recalculated_birth_date' not in payload['calendar_evidence'][card['id']]
        calls.append(payload)
        issue=next(i for i in payload['findings'] if '/birth_date' in i['message'])
        yield json.dumps(dict(candidate_hash=payload['candidate_hash'],rationale='Автор уточнил дату.',
            changes=[dict(change('/world/characters/'+card['id']+'/birth_date',None,'replace'),date_basis=basis)],
            decisions=[dict(issue_id=issue['issue_id'],outcome='proposed',reason='Дата получена из календаря.',change_indices=[0])]))
    with patch('backend.services.preparation.chat_stream',side_effect=answer):
        job=submit(client,url,base,'fix','date').json()
        assert wait_job(client,job['id'])['status']=='saved'
    proposal=repo.world_edits(wid,True)['edits'][0]
    assert proposal['status']=='preview',proposal
    updated=client.post(url+'/edits/'+job['id'],json=dict(revision=repo.draft(wid)['revision'],decision='accept')).json()
    assert len(calls)==1 and old!=expected
    resolution=updated['state']['authoring']['calendar_completion']['birth_dates'][card['id']]
    assert resolution['value']==expected and resolution['basis']==basis
    if basis['kind']=='year_only':
        assert resolution['known_year']==1990
    assert updated['state']['world']['characters'][card['id']]['birth_date']==expected
    assert complete(updated['state'])['world']['characters'][card['id']]['birth_date']==expected
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


def test_review_empty_conflicts_persist_without_applying_or_retrying(api):
    from backend.services.draft_changes import apply_proposal
    from backend.repositories.drafts import candidate_hash
    client,app=api
    repo=app.state.repository
    wid=seed(repo)['wid']
    url=f'/api/workspaces/{wid}/draft'
    base=repo.draft(wid,True)
    calls=[]
    conflicts=['Известен только год.', 'Источники расходятся.']
    def answer(**kwargs):
        calls.append(1)
        payload=json.loads(kwargs['messages'][-1]['content'])
        yield json.dumps(dict(candidate_hash=payload['candidate_hash'],rationale='Точных сведений недостаточно.',
            changes=[],conflicts=conflicts,decisions=[dict(issue_id=n['issue_id'],outcome='ambiguous',
            category='uncertainty',reason='Нужны сведения автора.') for n in payload['findings']]))
    with patch('backend.services.preparation.chat_stream',side_effect=answer):
        job=submit(client,url,base,'fix','assessment').json()
        assert wait_job(client,job['id'])['status']=='saved'
        assert submit(client,url,base,'fix','assessment').json()['id']==job['id']
    item=Repository(repo.path).world_edits(wid,True)['edits'][0]
    assert item['status']=='assessed' and not item['failure'] and item['proposal']['conflicts']==conflicts
    assert len(item['requests'])==len(calls)==1
    assert all(r['outcome']=='ambiguous' and r['category']=='uncertainty' for r in item['outcomes'])
    current=repo.draft(wid,True)
    assert current['version_id']==base['version_id'] and current['state']==base['state']
    assert not client.post(url+'/edits/'+job['id'],json=dict(revision=current['revision'],decision='accept')).is_success
    with pytest.raises(ValueError,match='нерешённые авторские конфликты'):
        apply_proposal(base['state'],json.dumps(item['proposal']))
    # Simulate the exact journal shape left by the prior release.
    with repo.connect() as db:
        journal=json.loads(repo.preparation_job(job['id'])['response_journal'])
        journal['editor'].update(status='unapplied',failure='Творческое предложение содержит нерешённые авторские конфликты.')
        stored=json.dumps(journal)
        db.execute('UPDATE preparation_jobs SET response_journal=? WHERE id=?',(stored,job['id']))
    reopened=Repository(repo.path).world_edits(wid,True)['edits'][0]
    assert reopened['status']=='assessed' and not reopened['failure'] and reopened['outcomes']==item['outcomes']
    assert repo.preparation_job(job['id'])['response_journal']==stored
    from backend.services.draft_review_actions import proposal_result
    unsafe=dict(item['proposal'],changes=[dict(op='replace',path='/campaign/description',value='Новый текст',reason='Правка.')],
                decisions=[dict(issue_id=item['outcomes'][0]['issue_id'],outcome='proposed',reason='Правка.',change_indices=[0])])
    assert proposal_result(journal['editor'],json.dumps(unsafe))['status']=='preview'
    with pytest.raises(ValueError,match='другой версии'):
        proposal_result(journal['editor'],json.dumps(dict(unsafe,changes=[],decisions=[],candidate_hash=candidate_hash('other'))))


def test_original_world_edit_analysis():
    import hashlib
    import os
    from pathlib import Path
    from backend.services.draft_review_actions import historical_assessment, proposal_result
    path=os.getenv('RPG_WORLD_EDIT_EXPORT')
    if not path:
        pytest.skip('private original supplied separately')
    raw=Path(path).read_bytes()
    assert hashlib.sha256(raw).hexdigest()=='8bc8b315986e09cfbe83babdfbcf15a8393588fec14cc06fe81c174b9cdb4da9'
    export=json.loads(raw)
    proposal=export['proposal']
    # The export contains the response and frozen fingerprint, not the candidate itself.
    notes=[{k:row[k] for k in ('issue_id','message','paths')} for row in export['outcomes']]
    decisions=[{k:row[k] for k in ('issue_id','reason','outcome','change_indices')} for row in export['outcomes']]
    edit=dict(base=dict(state=None),before_hash=proposal['candidate_hash'],findings=notes)
    result=proposal_result(edit,json.dumps(dict(proposal,decisions=decisions)))
    assert result['status']=='assessed' and not result['diff'] and 'candidate' not in result
    assert len(result['outcomes'])==3 and all(r['outcome']=='ambiguous' for r in result['outcomes'])
    assert result['proposal']==proposal and len(proposal['conflicts'])==2
    assert historical_assessment(dict(export,before_hash=edit['before_hash']))
    assert export['requests'][0]['input_tokens']==29130 and export['requests'][0]['output_tokens']==8442


def test_live_calendar_examples_use_cited_day_and_age_and_preserve_year_precision():
    from backend.services.draft_calendar import review_birth_date
    quote = 'Сегодня у Ильи день рождения'
    idea = quote + '. Илья Волков, 30 лет. Мёрфи родилась в 2015 году.'
    actors = {cid:dict(birth_date=day,birth_date_provenance=dict(source='authoring_automatic'))
              for cid,day in [('ilya','1995-11-27'),('murphy','2014-09-27')]}
    ledger = {cid:dict(source='automatic',value=a['birth_date']) for cid,a in actors.items()}
    state = dict(world=dict(characters=actors), authoring=dict(calendar_completion=dict(birth_dates=ledger)),
        characters=[dict(id='ilya',fields={'Возраст':'30 лет'}),dict(id='murphy',fields={'Возраст':'11 лет'})],
        world_clock=dict(minute=0,calendar=dict(start_minute=0,start_date='2026-07-10',start_weekday=4)))
    base = dict(state=state,source=idea)
    exact = dict(kind='birthday_at_start',quote=quote,age_quote='Илья Волков, 30 лет')
    path = '/world/characters/ilya/birth_date'
    assert review_birth_date(base,path,exact)['value']=='1996-07-10'
    murphy = '/world/characters/murphy/birth_date'
    year = dict(kind='year_only',quote='Мёрфи родилась в 2015 году',year=2015)
    # Auxiliary old quotes do not grant or deny editorial authority.
    assert review_birth_date(base,path,dict(exact,quote='',age_quote=''))['value']=='1996-07-10'
    with pytest.raises(ValueError):
        review_birth_date(base,'/world/objective_relations/marriage/until_date',year)
    actors['ilya']['birth_date_provenance']['source']='manual'
    assert review_birth_date(base,path,exact)['value']=='1996-07-10'


@pytest.mark.parametrize('both_nineteen,expected,choices',[(False,'2015-06-12',191),(True,'2015-07-10',1)])
def test_family_chronology_is_previewed_and_committed_atomically(api,both_nineteen,expected,choices):
    from review_actions_fixture import seed_family,family_reply
    from backend.runtime_v3.calendar import age_on
    client,app=api;repo=app.state.repository
    wid=seed_family(repo,both_nineteen=both_nineteen)['wid']
    url=f'/api/workspaces/{wid}/draft'
    base=repo.draft(wid,True)
    def answer(**kw):
        yield json.dumps(family_reply(json.loads(kw['messages'][-1]['content'])))
    with patch('backend.services.preparation.chat_stream',side_effect=answer) as transport:
        job=submit(client,url,base,'fix','family').json()
        assert 'id' in job,job
        assert wait_job(client,job['id'])['status']=='saved'
        assert transport.call_count==1
    preview=Repository(repo.path).world_edits(wid,True)['edits'][0]
    assert preview['status']=='preview',preview['failure']
    if both_nineteen:
        # The model explicitly chose June. Preserve its choice and show the disagreement.
        assert preview['proposal']['conflicts']
        assert any(c['path'].endswith('/'+base['state']['characters'][1]['id']+'/birth_date') and
                   c['value']=='2015-06-12' for c in preview['proposal']['changes'])
        fresh=repo.draft(wid,True)
        assert fresh['state']==base['state']
        applied=client.post(url+'/edits/'+job['id'],json=dict(revision=fresh['revision'],decision='accept')).json()
        assert applied['state']['world']['characters'][base['state']['characters'][1]['id']]['birth_date']=='2015-06-12'
        restored=client.patch(url,json=dict(revision=applied['revision'],operation='restore',source_id=base['version_id'])).json()
        assert restored['state']==base['state']
        return
    report=preview['chronologies'][0]
    assert report['options']==choices and report['date']==expected
    assert report['inventions']
    paths=[d['path'] for d in preview['proposal']['changes']]
    assert len(paths)==len(set(paths))==5
    assert repo.draft(wid,True)['state']==base['state']
    fresh=repo.draft(wid,True)
    accepted=client.post(url+'/edits/'+job['id'],json=dict(revision=fresh['revision'],decision='accept'))
    assert accepted.is_success,accepted.text
    final=accepted.json()
    father,child,mother=[final['state']['world']['characters'][k['id']] for k in base['state']['characters'][:3]]
    assert father['birth_date']=='1996-07-10'
    assert child['birth_date']==mother['death_date']==expected
    assert age_on(child['birth_date'],'2026-07-10')==11
    assert age_on(mother['birth_date'],expected)==19
    assert age_on(father['birth_date'],expected)==(19 if both_nineteen else 18)
    assert final['state']['world']['objective_relations']['old_marriage']['until_date']==expected
    for group in ('knowledge','events','facts'):
        assert final['state']['world'][group]==base['state']['world'][group]
    restored=client.patch(url,json=dict(operation='restore',revision=final['revision'],source_id=base['version_id'])).json()
    assert restored['state']==base['state']


def test_family_chronology_protects_manual_and_dated_records(api):
    from review_actions_fixture import seed_family,family_reply
    from backend.repositories.drafts import candidate_hash
    from backend.services.draft_review_actions import proposal_result
    from copy import deepcopy
    _,app=api;repo=app.state.repository
    base=repo.draft(seed_family(repo,both_nineteen=True)['wid'],True)['state']
    from review_actions_fixture import FAMILY_SOURCE
    source=FAMILY_SOURCE+' Илье при рождении дочери было 19 лет.'
    notes=[dict(issue_id='family',message='Противоречие дат',paths=[])]
    for case in ('manual_marriage','fixed_death','manual_mother','event'):
        state=deepcopy(base)
        mother=state['characters'][2]['id']
        if case=='manual_marriage':
            state['authoring'].setdefault('manual_paths',[]).append('/world/objective_relations/old_marriage/until_date')
        elif case=='manual_mother':
            state['world']['characters'][mother]['birth_date_provenance']={'source':'manual'}
        elif case=='fixed_death':
            state['world']['characters'][mother]['death_date']='2015-01-01'
        packet=family_reply(dict(candidate=state,candidate_hash=candidate_hash(state),findings=notes,author_context=dict(original_idea=source)))
        if case=='event':
            eid=next(iter(state['world']['events']))
            state['world']['events'][eid].update(participants=[mother],minute=state['world_clock']['minute'])
            packet['candidate_hash']=candidate_hash(state)
            packet['changes'][0]['date_basis']['event_ids']=[eid]
        result=proposal_result(dict(base=dict(state=state,source=source),findings=notes),json.dumps(packet))
        assert result['status']=='preview',case
        assert result['proposal']['conflicts'] and candidate_hash(state)==packet['candidate_hash']
        if case=='manual_marriage':
            assert result['conflicts']==['/world/objective_relations/old_marriage/until_date']


def test_previous_year_only_assessment_can_receive_a_coherent_date(api):
    from review_actions_fixture import FAMILY_SOURCE, seed_family, family_reply
    from backend.repositories.drafts import candidate_hash
    from backend.services.draft_review_actions import proposal_result
    _,app=api;repo=app.state.repository
    state=repo.draft(seed_family(repo)['wid'],True)['state']
    child=state['characters'][1]['id']
    actor=state['world']['characters'][child]
    actor.update(birth_date=None,birth_date_provenance=dict(source='unknown'))
    state['authoring']['calendar_completion']['birth_dates'][child]=dict(source='unknown',value=None,known_year=2015)
    father=state['characters'][0]['id']
    state['world']['characters'][father].update(birth_date='1996-07-10',birth_date_provenance=dict(source='explicit'))
    notes=[dict(issue_id='review',message='Восстановить хронологию',paths=[])]
    packet=family_reply(dict(candidate=state,candidate_hash=candidate_hash(state),findings=notes,
                             author_context=dict(original_idea=FAMILY_SOURCE)))
    packet['changes']=packet['changes'][:1]
    packet['decisions'][0]['change_indices']=[0]
    result=proposal_result(dict(base=dict(state=state,source=FAMILY_SOURCE),findings=notes),json.dumps(packet))
    assert result['status']=='preview',result.get('failure')
    assert result['candidate']['world']['characters'][child]['birth_date']=='2015-06-12'
    assert not result['chronologies'][0]['parents'][0]['quote']


def test_old_pending_null_preview_recalculates_offline_and_fences_previous_tab(api):
    from review_actions_fixture import seed_family,legacy_year_packet,legacy_year_result
    client,app=api;repo=app.state.repository
    wid=seed_family(repo)['wid'];url=f'/api/workspaces/{wid}/draft'
    base=repo.draft(wid,True)
    def answer(**kw):
        yield json.dumps(legacy_year_packet(json.loads(kw['messages'][-1]['content'])))
    with patch('backend.services.preparation.chat_stream',side_effect=answer) as provider:
        with patch('backend.services.draft_review_actions.proposal_result',side_effect=legacy_year_result):
            job=submit(client,url,base,'fix','oldpreview').json()
            assert wait_job(client,job['id'])['status']=='saved'
        receipts=repo.world_edits(wid,True)['edits'][0]['requests']
        child=base['state']['characters'][1]['id']
        mother=base['state']['characters'][2]['id']
        previous=repo.draft(wid,True)
        decision=url+'/edits/'+job['id']
        calc=dict(revision=previous['revision'],decision='recalculate_dates')
        calc['family']=[dict(child=child,parent=mother,died_at_birth=True,age=19,birth_year=1996,
                             conditional_marriages=['old_marriage'])]
        response=client.post(decision,json=calc)
        assert response.is_success,response.text
        assert client.post(decision,json=calc).is_success
        assert provider.call_count==1
        updated=repo.draft(wid,True)
        assert updated['version_id']==previous['version_id'] and updated['state']==base['state']
        preview=repo.world_edits(wid,True)['edits'][0]
        assert preview['status']=='preview' and preview['chronologies'][0]['options']==191
        assert preview['requests']==receipts


def test_manual_child_date_anchors_the_other_family_changes(api):
    from review_actions_fixture import seed_family,FAMILY_SOURCE,family_reply
    from backend.repositories.drafts import candidate_hash
    from backend.services.draft_review_actions import proposal_result
    _,app=api;repo=app.state.repository
    state=repo.draft(seed_family(repo)['wid'],True)['state']
    child=state['characters'][1]['id']
    state['world']['characters'][child].update(birth_date='2015-04-10',birth_date_provenance=dict(source='manual'))
    notes=[dict(issue_id='family',message='Проверить даты',paths=[])]
    packet=family_reply(dict(candidate=state,candidate_hash=candidate_hash(state),findings=notes,author_context=dict(original_idea=FAMILY_SOURCE)))
    result=proposal_result(dict(base=dict(state=state,source=FAMILY_SOURCE),findings=notes),json.dumps(packet))
    assert result['status']=='preview',result.get('failure')
    assert result['candidate']['world']['characters'][child]['birth_date']=='2015-06-12'
    assert state['world']['characters'][child]['birth_date']=='2015-04-10'
    assert '/world/characters/'+child+'/birth_date' in result['conflicts']


def test_childbirth_age_without_an_authorial_birth_year(api):
    from backend.repositories.drafts import candidate_hash
    from backend.runtime_v3.calendar import age_on
    from backend.services.draft_review_actions import proposal_result
    from review_actions_fixture import FAMILY_SOURCE, family_reply, seed_family

    _,app=api
    repo=app.state.repository
    state=repo.draft(seed_family(repo)['wid'],True)['state']
    mother=state['characters'][2]['id']
    source=FAMILY_SOURCE.removesuffix(' Лиза родилась в 1996 году.')
    notes=[dict(issue_id='family',message='Проверить совместимость дат',paths=[])]
    packet=family_reply(dict(candidate=state,candidate_hash=candidate_hash(state),findings=notes,
                             author_context=dict(original_idea=source)))
    evidence=packet['changes'][0]['date_basis']['parents'][0]
    del evidence['birth_year'],evidence['birth_year_quote']
    result=proposal_result(dict(base=dict(state=state,source=source),findings=notes),json.dumps(packet))
    assert result['status']=='preview',result.get('failure')
    report=result['chronologies'][0]
    assert report['date']=='2015-06-12' and report['options']==191
    birthday=result['candidate']['world']['characters'][mother]['birth_date']
    assert age_on(birthday,report['date'])==19
    assert dict(name='Лиза',date=birthday) in report['inventions']
    assert result['calendar_decisions'][mother].get('known_year') is None
