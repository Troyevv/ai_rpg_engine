"""Author-confirmed editorial proposals, including offline replay of live exports."""
import hashlib
import json
import os
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.repositories.drafts import candidate_hash
from backend.repositories.preparation import Repository
from backend.services.draft_completeness import pointer
from backend.services.draft_review_actions import proposal_result
from review_actions_fixture import seed_family
from test_api import api
from test_draft_review_actions import submit, wait_job


def live_family(repo):
    wid=seed_family(repo)['wid']
    record=repo.draft(wid,True)
    old=record['state']
    ids={c['id']:name for c,name in zip(old['characters'],('ilya','murphy','liza'))}
    ids.update(old_marriage='or_spouse_ilya_liza',delivery='ev_liza_death')
    def rename(v):
        if isinstance(v,list):return [rename(item) for item in v]
        if isinstance(v,dict):return {ids.get(k,k):rename(item) for k,item in v.items()}
        return ids.get(v,v) if isinstance(v,str) else v
    return wid,rename(old)


@pytest.mark.parametrize(('archive','reopen'),[(False,False),(True,False),(True,True)],
                         ids=['public-nine-operations','original-third-export','reopen-third-export'])
def test_nine_recorded_addresses_confirm_persist_restore(api,archive,reopen):
    fields=[
        ('world.characters.ilya.birth_date','/world/characters/ilya/birth_date','1996-07-10'),
        ('world.characters.murphy.birth_date','/world/characters/murphy/birth_date','2015-09-27'),
        ('characters[1].fields.Возраст','/characters/1/fields/Возраст','10 лет'),
        ('world.characters.liza.birth_date','/world/characters/liza/birth_date','1996-06-15'),
        ('world.objective_relations.or_spouse_ilya_liza.since_date','/world/objective_relations/or_spouse_ilya_liza/since_date','2014-08-01'),
        ('world.objective_relations.or_spouse_ilya_liza.until_date','/world/objective_relations/or_spouse_ilya_liza/until_date','2015-09-27'),
        ('world.objective_relations.or_spouse_ilya_liza.context','/world/objective_relations/or_spouse_ilya_liza/context','Семейная история.'),
        ('world.facts.f_liza_death.text','/world/facts/f_liza_death/text','Новая запись факта.'),
        ('world.events.ev_liza_death.text','/world/events/ev_liza_death/text','Новая запись события.'),
    ]
    idea='Мёрфи Волкова, 11 лет. В 19 лет Лиза родила Мёрфи и умерла при родах.'
    packet=dict(changes=[dict(path=addr,value=value,op='replace') for addr,_,value in fields],
                conflicts=['Предложение меняет авторский возраст.'])
    if archive:
        path=os.getenv('RPG_WORLD_EDIT_THIRD_EXPORT')
        if not path:pytest.skip('Private third export supplied separately')
        raw=Path(path).read_bytes()
        assert hashlib.sha256(raw).hexdigest()=='fc4fb1837a5c6d2c10ada55d7e7cd7731526491a27baa8bf34aa0570f75b9f1e'
        export=json.loads(raw)
        packet=export['proposal']
        assert [row['path'] for row in packet['changes']]==[addr for addr,_,_ in fields]
        assert len(export['diagnostics'])==9
        idea=export['author_idea']
    client,app=api
    repo=app.state.repository
    wid,state=live_family(repo)
    state['world']['facts']['f_liza_death']=dict(id='f_liza_death',text='Лиза умерла при родах.')
    with repo.connect() as db:
        repo._write_draft(db,wid,state,'draft_world',source=idea,review=dict(status='completed',
                          advisory=True,issues=[dict(message='Проверить даты.',severity='warning')]))
    url=f'/api/workspaces/{wid}/draft'
    before=repo.draft(wid,True)
    # The export contains the envelope and proposal, but not its frozen WorldState.
    response=dict(packet,candidate_hash=candidate_hash(before['state']))
    def recorded(**kw):
        system,user=kw['messages']
        payload=json.loads(user['content'])
        assert payload['author_context']['original_idea']==idea
        assert 'Мёрфи Волкова, 11 лет' in idea
        assert 'приоритет над автоматически заполненными датами' in system['content']
        assert '/characters/1/fields/Возраст' in system['content']
        assert payload['response_schema']['$defs']['EditorialChange']['properties']['path']['pattern']=='^/'
        yield json.dumps(response,ensure_ascii=False)
    with patch('backend.services.preparation.chat_stream',side_effect=recorded) as transport:
        # Recreate an already journaled failed job exactly as projected in the export.
        with ExitStack() as setup:
            if reopen:
                historical={k:export[k] for k in ('status','failure','diagnostics','outcomes')}
                historical['proposal']=response
                setup.enter_context(patch('backend.services.draft_review_actions.proposal_result',return_value=historical))
            job=submit(client,url,before,'fix','nine').json()
            assert wait_job(client,job['id'])['status']=='saved'
        if reopen:
            old=client.get(url+'/edits?author=true').json()['edits'][0]
            assert old['status']=='unapplied' and old['can_replay']
            opened=client.post(url+'/edits/'+job['id'],json=dict(revision=old['base_revision'],decision='replay'))
            assert opened.is_success,opened.text
        edit=client.get(url+'/edits?author=true').json()['edits'][0]
        assert edit['status']=='preview',edit.get('failure')
        assert edit['proposal']['conflicts']==packet['conflicts']
        if reopen:assert edit['requests']==old['requests']
        assert [row['path'] for row in edit['proposal']['changes']]==[path for _,path,_ in fields]
        assert Repository(repo.path).draft(wid,True)['state']==before['state']
        accepted=client.post(url+'/edits/'+job['id'],json=dict(revision=edit['base_revision'],decision='accept'))
        assert accepted.is_success,accepted.text
        after=Repository(repo.path).draft(wid,True)
        assert after['version_id']!=before['version_id']
        for (_,canonical,_),change in zip(fields,packet['changes'],strict=True):
            assert pointer(after['state'],canonical)==change['value']
        assert after['state']['world']['knowledge']==before['state']['world']['knowledge']
        restored=client.patch(url,json=dict(revision=after['revision'],operation='restore',source_id=before['version_id']))
        assert restored.is_success,restored.text
        assert Repository(repo.path).draft(wid,True)['state']==before['state']
        assert len(edit['requests'])==transport.call_count==1
        assert repo.world_edits(wid,True)['edits'][0]['requests']==edit['requests']


def test_second_archived_edit_preview(api):
    path=os.getenv('RPG_WORLD_EDIT_SECOND_EXPORT')
    if not path:pytest.skip('Private original supplied separately')
    export=json.loads(Path(path).read_text())
    assert export['failure']=='Год рождения не подтверждён цитатой об этом персонаже.'
    client,app=api
    repo=app.state.repository
    wid,state=live_family(repo)
    source='Сегодня у Ильи день рождения. Илья Волков, 30 лет. В 19 лет Лиза родила Мёрфи и умерла при родах.'
    # The download has no world snapshot. Only rebind the envelope to our reconstructed base.
    proposal=dict(export['proposal'],candidate_hash=candidate_hash(state))
    notes=[{k:v for k,v in row.items() if k in ('issue_id','message','paths')} for row in export['outcomes']]
    decisions=[dict(issue_id=r['issue_id'],outcome='proposed',reason=r['reason'],change_indices=r.get('change_indices',[])) for r in export['outcomes']]
    edit=dict(base=dict(state=state,source=source),findings=notes)
    result=proposal_result(edit,json.dumps(dict(proposal,decisions=decisions)))
    assert result['status']=='preview',result.get('failure')
    world=result['candidate']['world']
    assert world['characters']['ilya']['birth_date']=='1996-07-10'
    assert world['characters']['murphy']['birth_date']==world['characters']['liza']['death_date']=='2015-06-15'
    assert world['objective_relations']['or_spouse_ilya_liza']['until_date']=='2015-06-15'
    assert result['proposal']['conflicts']==proposal['conflicts']
    with repo.connect() as db:
        repo._write_draft(db,wid,state,'draft_world',source=source,review=dict(status='completed',advisory=True,
            issues=[dict(message=n['message'],severity='warning') for n in notes]))
    url=f'/api/workspaces/{wid}/draft'
    before=repo.draft(wid,True)
    raw=json.dumps(dict(proposal,decisions=decisions))
    with patch('backend.services.preparation.chat_stream',side_effect=lambda **kw:iter([raw])) as transport:
        job=submit(client,url,before,'fix','archived').json()
        assert wait_job(client,job['id'])['status']=='saved'
        preview=repo.world_edits(wid,True)['edits'][0]
        assert preview['proposal']['conflicts']==export['proposal']['conflicts']
        assert repo.draft(wid,True)['state']==before['state']
        accepted=client.post(url+'/edits/'+job['id'],json=dict(revision=repo.draft(wid)['revision'],decision='accept'))
        assert accepted.is_success,accepted.text
        assert accepted.json()['state']['world']['characters']['murphy']['birth_date']=='2015-06-15'
        assert transport.call_count==1



def test_original_failed_job_can_be_reopened_and_amended_offline(api):
    from backend.repositories.preparation import Repository
    from review_actions_fixture import direct_family_reply
    client,app=api
    repo=app.state.repository
    wid=seed_family(repo)['wid']
    url=f'/api/workspaces/{wid}/draft'
    base=repo.draft(wid,True)
    packet={}
    def respond(**kwargs):
        packet.update(direct_family_reply(json.loads(kwargs['messages'][-1]['content'])))
        yield json.dumps(packet)
    old=dict(status='unapplied',failure='Год рождения не подтверждён цитатой об этом персонаже.',outcomes=[])
    with patch('backend.services.preparation.chat_stream',side_effect=respond) as provider:
        with patch('backend.services.draft_review_actions.proposal_result',return_value=old):
            job=submit(client,url,base,'fix','once').json()
            assert wait_job(client,job['id'])['status']=='saved'
        route=url+'/edits/'+job['id']
        version=repo.draft(wid,True)
        assert repo.world_edits(wid,True)['edits'][0]['can_replay']
        reopened=client.post(route,json=dict(revision=version['revision'],decision='replay'))
        assert reopened.is_success,reopened.text
        assert reopened.json()['state']==base['state']
        preview=Repository(repo.path).world_edits(wid,True)['edits'][0]
        assert preview['proposal']['conflicts']==packet['conflicts']
        related=next(r for r in preview['related_records'] if r['section']=='world/characters' and r['id']=='character_2')
        assert {'kind':'events','id':'delivery'} in related['links']
        assert 'date_basis' not in preview['proposal']['changes'][0]
        assert [a['age'] for a in preview['family_impacts']]==[18,19]
        fresh=reopened.json()['revision']
        invalid=client.post(route,json=dict(revision=fresh,decision='revise',values={0:'2015-02-31'}))
        assert not invalid.is_success and 'birth_date' in invalid.text
        assert repo.draft(wid,True)['revision']==fresh
        updated=client.post(route,json=dict(revision=fresh,decision='revise',values={0:'2015-07-10'}))
        assert updated.is_success,updated.text
        assert not client.post(route,json=dict(revision=fresh,decision='accept')).is_success
        edit=Repository(repo.path).world_edits(wid,True)['edits'][0]
        assert edit['original_proposal']['changes'][0]['value']=='2015-06-15'
        decision=dict(revision=updated.json()['revision'],decision='accept')
        result=client.post(route,json=decision)
        assert result.is_success,result.text
        applied=result.json()
        assert client.post(route,json=decision).json()['version_id']==applied['version_id']
        assert packet['conflicts'][0] in [issue['message'] for issue in applied['review']['issues']]
        world=applied['state']['world']
        assert world['characters']['character_2']['birth_date']=='2015-07-10'
        assert world['characters']['character_3']['death_date']==world['objective_relations']['old_marriage']['until_date']=='2015-06-15'
        assert world['events']['delivery']['text']==packet['changes'][-1]['value']
        assert world['knowledge']==base['state']['world']['knowledge']
        assert repo.world_edits(wid,True)['edits'][0]['requests']==preview['requests']
        assert not repo.world_edits(wid)['edits']
        assert provider.call_count==1
    restored=client.patch(url,json=dict(revision=applied['revision'],operation='restore',source_id=base['version_id']))
    assert restored.json()['state']==base['state']


def test_author_can_edit_controlled_actor_background_but_generation_cannot():
    from backend.services.draft_changes import apply_proposal
    from test_draft_creative import candidate,change,proposal
    state=candidate()
    cid=state['controlled_actor_id']
    raw=proposal(state,[change('/world/characters/'+cid+'/intentions',['Отложить переезд.'],'replace')])
    with pytest.raises(ValueError):apply_proposal(state,raw)
    author,_=apply_proposal(state,raw,editing=True)
    assert author['world']['characters'][cid]['intentions'][0]['text']=='Отложить переезд.'
    assert author['world']['knowledge']==state['world']['knowledge']
