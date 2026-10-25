"""One optional, atomic completion batch using the existing review and repair."""
import json
from llm import ProviderHTTPError
from backend.repositories.drafts import candidate_hash
from backend.services import draft_completeness as review, draft_repair as repair


def selected(issues):
    # Only explicit reviewer selections: no length quotas and no fabricated needs.
    return [e for e in issues if e.get('severity')=='recommendation'
            and e.get('assertion')=='optional_detail' and e.get('patch_paths')]


def complete(state, issues, author_context, journal, call):
    chosen=selected(issues)
    if not chosen or journal.get('quality',{}).get('status') in ('accepted','rejected'):return state,None
    before=candidate_hash(state)
    record=journal.setdefault('quality',dict(status='running',before_hash=before))
    try:
        raw=json.dumps(state,ensure_ascii=False)
        messages,scope=repair.request(raw,chosen,author_context)
        messages[0]['content']='Один необязательный пакет улучшения выбранных слабых полей. Сохрани хорошие поля и авторские ограничения. '+messages[0]['content']
        answer=call('quality_'+before,messages,'draft_world_quality')
        if answer is None:return state,None
        trial=json.loads(repair.apply(raw,answer,scope))
        from backend.services.draft_initial import inspect_candidate
        trial,report=inspect_candidate(trial)
        if report['errors']:raise ValueError('; '.join(report['errors']))
        signature=candidate_hash(trial)
        # Text can affect distant facts and knowledge: bounded full re-review.
        answer=call('quality_review_'+signature,review.messages(trial,author_context),'draft_world_validation')
        if answer is None:return state,None
        checked=review.parse(answer,trial)
        if any(e.get('severity')=='blocker' for e in checked):
            raise ValueError('Дополнение не прошло повторную смысловую проверку: '+json.dumps(checked,ensure_ascii=False))
        record.update(status='accepted',after_hash=signature,issues=checked)
        return trial,checked
    except (ValueError,ProviderHTTPError) as exc:
        record.update(status='rejected',warning=str(exc))
        if isinstance(exc,repair.RejectedTrial):record['trial']=exc.details
        return state,None
