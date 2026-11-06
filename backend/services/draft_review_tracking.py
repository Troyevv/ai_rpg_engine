"""Observed structural fixes across completed reports, outside the world canon.

Text disappearance is not evidence. Re-evaluate the same typed predicate using
the existing review validator; bind array paths to entity IDs, never positions.
Semantic findings still require an explicit reviewer decision.
"""
from copy import deepcopy
from backend.runtime_v3.life import SYMMETRIC
from backend.services.draft_completeness import (
    ReviewIssue, issue_identity, pointer, predicate_disproved,
)


def _bind(state, path):
    if not isinstance(path, str):
        return None
    parts = path.split('/')
    if len(parts) > 2 and parts[1] in ('characters', 'locations'):
        try:
            row = pointer(state, '/'.join(parts[:3]))
            ident = row['id']
            if sum(r.get('id') == ident for r in state[parts[1]]) != 1:
                return None
        except (ValueError, KeyError, TypeError, IndexError):
            return None
        return {'collection': parts[1], 'id': ident, 'tail': parts[3:]}
    return {'path': path}


def _path(state, address):
    if 'path' in address:
        return address['path']
    rows = state.get(address['collection'], [])
    indexes = [i for i, row in enumerate(rows) if row.get('id') == address['id']]
    if len(indexes) != 1:
        raise ValueError('Исходный объект отсутствует или неоднозначен.')
    return '/' + '/'.join([address['collection'], str(indexes[0]), *address['tail']])


def _probe(state, descriptor):
    spec = dict(descriptor['claim'], path=_path(state, descriptor['address']))
    # Check the parent as well: deleting the original object is not filling its
    # missing field, even if another object later takes the same array position.
    path = spec['path']
    if spec['assertion'] != 'missing_record':
        pointer(state, path.rsplit('/', 1)[0])
    issue = ReviewIssue.model_validate(dict(spec, message='Проверка сохранённого условия', patch_paths=[]))
    try:
        return predicate_disproved(state, issue), issue.path
    except KeyError:
        return False, path


def observe(previous, state, review):
    """Pure metadata update; failed/stale/running reviews cannot confirm fixes."""
    from backend.repositories.drafts import candidate_hash
    tracking = deepcopy(previous or {'pending': {}, 'fixed': []})
    if not review or review.get('status') != 'completed':
        return tracking
    checked_hash = candidate_hash(state)
    if review.get('candidate_hash') != checked_hash:
        return tracking
    pending = tracking.setdefault('pending', {})
    fixed = tracking.setdefault('fixed', [])
    for key, item in list(pending.items()):
        try:
            verified, path = _probe(state, item['descriptor'])
        except (ValueError, KeyError, TypeError, IndexError):
            continue
        if not verified or item['candidate_hash'] == checked_hash:
            continue
        reason = {
            'missing_value': 'Повторная проверка подтвердила: указанное поле теперь заполнено.',
            'missing_reference': 'Повторная проверка подтвердила: ссылка разрешается в существующую запись.',
            'missing_record': 'Повторная проверка нашла запись с исходными идентифицирующими полями.',
        }[item['descriptor']['claim']['assertion']]
        fixed.append(dict(issue_id=key, signature=review.get('signature') or checked_hash,
                          message=item['message'], resolution='fixed', reason=reason,
                          paths=[path], candidate_hash=checked_hash,
                          checked_revision=review.get('checked_revision')))
        del pending[key]
    for row in review.get('issues', []):
        if row.get('assertion') not in ('missing_value', 'missing_reference', 'missing_record'):
            continue
        if row.get('protocol_warnings') or row.get('server_verification') == 'disproved':
            continue
        original = row.get('original_issue') or row
        claim = {key: original[key] for key in ('assertion', 'section', 'target_path', 'record_match') if original.get(key) is not None}
        claim['assertion'] = row['assertion']
        match = claim.get('record_match')
        if claim.get('section') == 'objective_relations' and match and match.get('kind') in SYMMETRIC:
            if all(isinstance(match.get(key), str) for key in ('source_id', 'target_id')):
                source, target = sorted((match['source_id'], match['target_id']))
                claim['record_match'] = dict(match, source_id=source, target_id=target)
        address = _bind(state, row.get('path'))
        if address is None:
            continue
        descriptor = dict(claim=claim, address=address)
        try:
            verified, _ = _probe(state, descriptor)
        except (ValueError, KeyError, TypeError, IndexError):
            continue
        if verified:
            continue  # False positive in its first report, not a repaired world.
        key = issue_identity(descriptor)
        pending.setdefault(key, dict(descriptor=descriptor, message=row['message'], candidate_hash=checked_hash))
    return tracking


def fixed_decisions(tracking, current_hash):
    return [dict(row, applies_to_current=row['candidate_hash'] == current_hash)
            for row in (tracking or {}).get('fixed', [])]
