"""Versioned wire contract shared by optional initiative and phone jobs."""
import json
from pydantic import Field, model_validator
from backend.runtime_v3.remote_models import RemoteModel, RemoteProposal
from backend.runtime_v3.group_planning import GroupSeries

VERSION = 'remote-decision/1'


class DecisionProposal(RemoteProposal):
    basis_ids: list[str] = Field(min_length=1, max_length=8)


class RemoteDecision(RemoteModel):
    action: DecisionProposal | None


def decode(raw):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result: raise ValueError(f'Повторяющееся поле решения: {key}')
            result[key]=value
        return result
    return json.loads(raw, object_pairs_hook=unique)


def parse(raw):
    value = decode(raw)
    normalized = isinstance(value, dict) and isinstance(value.get('action'), str)
    if normalized:
        value = {'action': DecisionProposal.model_validate(value).model_dump()}
    result = RemoteDecision.model_validate(value)
    return result.action.model_dump() if result.action else None, {
        'contract': VERSION, 'normalized_flat': normalized,
    }


class RemoteStageDecision(RemoteDecision):
    group_series: GroupSeries | None = None

    @model_validator(mode='after')
    def exclusive(self):
        if self.action is not None and self.group_series is not None:
            raise ValueError('one_remote_opportunity')
        return self
