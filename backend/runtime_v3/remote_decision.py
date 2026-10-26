"""Versioned wire contract shared by optional initiative and phone jobs."""
import json
from pydantic import Field
from backend.runtime_v3.remote_models import RemoteModel, RemoteProposal

VERSION = 'remote-decision/1'


class DecisionProposal(RemoteProposal):
    basis_ids: list[str] = Field(min_length=1, max_length=8)


class RemoteDecision(RemoteModel):
    action: DecisionProposal | None


def parse(raw):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result: raise ValueError(f'Повторяющееся поле решения: {key}')
            result[key]=value
        return result
    value = json.loads(raw, object_pairs_hook=unique)
    normalized = isinstance(value, dict) and isinstance(value.get('action'), str)
    if normalized:
        value = {'action': DecisionProposal.model_validate(value).model_dump()}
    result = RemoteDecision.model_validate(value)
    return result.action.model_dump() if result.action else None, {
        'contract': VERSION, 'normalized_flat': normalized,
    }
