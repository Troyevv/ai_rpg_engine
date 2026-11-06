"""Read confirmed re-audit decisions; absence from a later report proves nothing."""
import json
from backend.services.draft_completeness import issue_identity


def decisions(journal, current_hash):
    result=[]
    for batch in journal.get('review_resolutions',[]):
        signature=batch.get('signature')
        # A parsed response may precede a failed final validation. Only the
        # accepted review journal establishes completion of this exact scope.
        if signature not in journal.get('accepted_reviews',{}):continue
        originals={}
        for failure in journal.get('review_failures',[]):
            if failure.get('signature')!=signature:continue
            try:items=json.loads(failure.get('response',''))['issues']
            except (ValueError,KeyError,TypeError):continue
            if not isinstance(items,list):continue
            for item in items:
                if isinstance(item,dict):originals[issue_identity(item)]=(item,failure.get('candidate_hash'))
        for decision in batch.get('decisions',[]):
            original=originals.get(decision.get('issue_id'))
            if not original or decision.get('resolution') not in ('disproved','replaced'):continue
            issue,checked_hash=original
            if not checked_hash or not isinstance(issue.get('message'),str):continue
            result.append(dict(issue_id=decision['issue_id'],signature=signature,
                message=issue['message'],resolution=decision['resolution'],reason=decision['reason'],
                paths=[item['path'] for item in decision.get('basis',[])],
                candidate_hash=checked_hash,applies_to_current=checked_hash==current_hash))
    # Recovery resumes can persist the same accepted decision again.
    return list({(row['signature'],row['issue_id']):row for row in result}.values())
