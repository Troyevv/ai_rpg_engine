from copy import deepcopy
import json

from backend.repositories.drafts import candidate_hash
from backend.services.draft_completeness import parse
from backend.services.draft_review_tracking import observe, fixed_decisions


def report(state, issues, signature='s'):
    return dict(status='completed', candidate_hash=candidate_hash(state),
                signature=signature, issues=parse(json.dumps({'issues': issues}), state))


def fixture():
    from test_initial_draft_v4 import rich
    state=rich()
    state['characters'][1]['fields']['Привычки']=''
    issue=dict(assertion='missing_value', message='Не заполнены привычки',
               path='/characters/1/fields/Привычки', severity='recommendation')
    return state,issue


def test_fixed_requires_observed_predicate_not_disappearance_or_failed_report():
    state,issue=fixture()
    history=observe(None,state,report(state,[issue]))
    assert len(history['pending'])==1
    for status in ('completed','failed','running','stale'):
        current=dict(report(state,[]),status=status)
        assert not observe(history,state,current)['fixed']
    fixed=deepcopy(state);fixed['characters'][1]['fields']['Привычки']='Насвистывает за работой.'
    for status in ('failed','running','stale'):
        assert not observe(history,fixed,dict(report(fixed,[]),status=status))['fixed']
    assert not observe(history,fixed,report(state,[]))['fixed']  # Wrong checked candidate.
    result=observe(history,fixed,report(fixed,[],'next'))
    assert len(result['fixed'])==1 and not result['pending']
    assert result==observe(result,fixed,report(fixed,[],'next'))
    assert fixed_decisions(result,candidate_hash(fixed))[0]['applies_to_current']
    assert not fixed_decisions(result,candidate_hash(state))[0]['applies_to_current']


def test_identity_ignores_rewording_and_follows_entity_after_array_reordering():
    state,issue=fixture();history=observe(None,state,report(state,[issue]))
    reordered=deepcopy(state);reordered['characters'].reverse()
    ident=state['characters'][1]['id'];index=next(i for i,c in enumerate(reordered['characters']) if c['id']==ident)
    changed=dict(issue,message='Другая формулировка',path=f'/characters/{index}/fields/Привычки')
    history=observe(history,reordered,report(reordered,[changed],'second'))
    assert len(history['pending'])==1 and not history['fixed']
    reordered['characters'][index]['fields']['Привычки']='Записывает мысли.'
    result=observe(history,reordered,report(reordered,[],'third'))
    assert len(result['fixed'])==1
    assert result['fixed'][0]['paths']==[changed['path']]


def test_deleted_subject_or_semantic_claim_is_never_inferred_fixed():
    state,issue=fixture();history=observe(None,state,report(state,[issue]))
    deleted=deepcopy(state);del deleted['characters'][1]
    assert not observe(history,deleted,report(deleted,[]))['fixed']
    semantic=dict(issue,assertion='semantic',message='Характер противоречит биографии')
    tracked=observe(None,state,report(state,[semantic]))
    changed=deepcopy(state);changed['characters'][1]['fields']['Привычки']='Иной текст'
    assert not observe(tracked,changed,report(changed,[]))['fixed']


def test_already_disproved_claim_is_not_a_fixed_defect():
    state,issue=fixture();state['characters'][1]['fields']['Привычки']='Известны'
    history=observe(None,state,report(state,[issue]))
    assert not history['pending'] and not history['fixed']


def test_missing_reference_reuses_typed_check_and_does_not_accept_empty_id():
    state={'campaign':{'ref':'absent'},'world':{'facts':{}}}
    issue=dict(assertion='missing_reference',path='/campaign/ref',target_path='/world/facts',message='Нет факта',severity='recommendation')
    history=observe(None,state,report(state,[issue]))
    empty=deepcopy(state);empty['campaign']['ref']=''
    assert not observe(history,empty,report(empty,[]))['fixed']
    fixed=deepcopy(state);fixed['world']['facts']['absent']={'id':'absent','text':'Есть факт'}
    assert len(observe(history,fixed,report(fixed,[]))['fixed'])==1


def test_missing_record_matches_existing_symmetric_relation_and_active_status():
    state,unused=fixture();ids=[c['id'] for c in state['characters']][:2]
    state['world']['objective_relations']={}
    issue=dict(assertion='missing_record',section='objective_relations',record_match=dict(source_id=ids[0],target_id=ids[1],kind='friend'),message='Нужна связь',severity='recommendation')
    history=observe(None,state,report(state,[issue]));assert len(history['pending'])==1
    reversed_issue=dict(issue,message='Дружба описана иначе',record_match=dict(source_id=ids[1],target_id=ids[0],kind='friend'))
    history=observe(history,state,report(state,[reversed_issue],'reworded'))
    assert len(history['pending'])==1
    fixed=deepcopy(state);fixed['world']['objective_relations']['friend']=dict(id='friend',source_id=ids[1],target_id=ids[0],kind='friend',status='ended')
    assert not observe(history,fixed,report(fixed,[]))['fixed']
    fixed['world']['objective_relations']['friend']['status']='active'
    assert len(observe(history,fixed,report(fixed,[]))['fixed'])==1


def test_sqlite_tracking_is_author_only_persists_versions_and_resets_for_new_generation(tmp_path):
    from backend.repositories.preparation import Repository
    from test_api import REMOTE
    repo=Repository(tmp_path/'tracking.sqlite');w=repo.create_workspace('История проверки')
    config=dict(REMOTE,_draft_task='world',_draft_input='Мир',_draft_token_budget=30000)
    jid=repo.begin_preparation(w['id'],'draft_world','Мир',config,0)
    state,issue=fixture()
    repo.save_draft_candidate(jid,state,[],review=report(state,[issue]))
    fixed=deepcopy(state);fixed['characters'][1]['fields']['Привычки']='Собирает открытки.'
    repo.save_draft_candidate(jid,fixed,[],review=report(fixed,[],'next'))
    before=repo.draft(w['id'],True);assert len(before['review_decisions'])==1
    assert before['review_decisions'][0]['resolution']=='fixed'
    assert repo.draft(w['id'],False)['review_decisions']==[]
    assert repo.draft(repo.create_workspace('Другой мир')['id'],True)['review_decisions']==[]
    repo.save_draft_candidate(jid,fixed,[],review=report(fixed,[],'next'))
    repeated=repo.draft(w['id'],True)
    assert repeated['revision']==before['revision'] and repeated['history']==before['history']
    repo.finish_draft_job(jid,fixed)
    final=repo.draft(w['id'],True);assert len(final['review_decisions'])==1
    repo.edit_candidate(w['id'],final['revision'],'/campaign/title','Новое название')
    stale=repo.draft(w['id'],True);assert not stale['review_decisions'][0]['applies_to_current']
    newer=repo.begin_preparation(w['id'],'draft_world','Другой замысел',config,stale['revision'])
    repo.save_draft_candidate(newer,state,[],review=report(state,[],'new-world'))
    assert repo.draft(w['id'],True)['review_decisions']==[]
