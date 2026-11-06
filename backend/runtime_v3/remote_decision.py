"""Versioned wire contract shared by optional initiative and phone jobs."""
import json
from typing import Literal

from pydantic import Field, model_validator
from backend.runtime_v3.remote_models import RemoteModel, RemoteProposal
from backend.runtime_v3.group_planning import GroupSeries

VERSION = 'remote-decision/2'
LEGACY_VERSION = 'remote-decision/1'


class DecisionEvidence(RemoteModel):
    actor_id: str
    basis_ids: list[str] = Field(min_length=1, max_length=8)
    knowledge_ids: list[str] = Field(default_factory=list, max_length=8)


class RoutedAction(DecisionEvidence):
    action: Literal['send', 'call']
    route_index: int = Field(ge=0, description="Zero-based position in this option's paths")
    content: str = ''


class EventAction(DecisionEvidence):
    action: Literal['answer', 'decline', 'read', 'end']
    event_id: str


class IdentifyAction(DecisionEvidence):
    action: Literal['identify']
    event_id: str
    speaker_name: str = Field(min_length=1, max_length=160)
    existing_character_id: str | None = None


class RemoteDecision(RemoteModel):
    action: RoutedAction | EventAction | IdentifyAction | None


class LegacyProposal(RemoteProposal):
    basis_ids: list[str] = Field(min_length=1, max_length=8)


class LegacyDecision(RemoteModel):
    action: LegacyProposal | None


def decode(raw):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result: raise ValueError(f'Повторяющееся поле решения: {key}')
            result[key]=value
        return result
    return json.loads(raw, object_pairs_hook=unique)


def permitted_option(options, actor_id, action, basis_ids):
    for option in options:
        if (actor_id == option['actor_id'] and action in option['actions']
                and basis_ids and set(basis_ids) <= set(option['basis_ids'])):
            return option
    raise ValueError('remote_ineligible')


def resolve(action, options):
    if action is None:
        return None
    # A truncated prompt may offer fewer actors than the runtime candidate set.
    if options is not None or isinstance(action, RoutedAction):
        option = permitted_option(options or (), action.actor_id, action.action, action.basis_ids)
    if isinstance(action, RoutedAction):
        paths = option.get('paths', [])
        if action.route_index >= len(paths):
            raise ValueError('remote_unreachable')
        return dict(action.model_dump(exclude={'route_index'}), **paths[action.route_index])
    return action.model_dump()


def parse(raw, options=None, *, contract=VERSION):
    value = decode(raw)
    normalized = isinstance(value, dict) and isinstance(value.get('action'), str)
    if normalized:
        value = {'action': value}
    if contract == LEGACY_VERSION:
        decision = LegacyDecision.model_validate(value)
    elif contract == VERSION:
        decision = RemoteDecision.model_validate(value)
    else:
        raise ValueError('unknown_remote_contract')
    return resolve(decision.action, options), {
        'contract': contract, 'normalized_flat': normalized,
    }


class RemoteStageDecision(RemoteDecision):
    group_series: GroupSeries | None = None

    @model_validator(mode='after')
    def exclusive(self):
        if self.action is not None and self.group_series is not None:
            raise ValueError('one_remote_opportunity')
        return self
