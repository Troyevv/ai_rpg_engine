"""Exact current-turn provenance; no linguistic reconstruction of movement."""
from backend.services.world_delta_errors import SecondaryDeltaError


def validate_provenance(delta, narrative, user_text):
    from state_updates import normalized_evidence, EvidenceError
    sources=[normalized_evidence(narrative),normalized_evidence(user_text)]
    for section,entries in delta.items():
        for index,item in enumerate(entries):
            quote=normalized_evidence(item['evidence'])
            if quote and any(quote in s for s in sources):continue
            if section=='promotions':raise EvidenceError('Новая роль не подтверждена цитатой текущего хода.')
            raise SecondaryDeltaError(section,index,'Нет подтверждённой цитаты текущего хода',
                entity=item.get('id') or item.get('actor_id') or item.get('source_id'),
                cause_field='evidence',code='evidence_unsupported')
