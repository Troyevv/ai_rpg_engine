"""Scene agency projections and claims for the existing Director/Resolver.

No autonomous clock, character agent, romance state or persistent permit store.
"""
from copy import deepcopy
import json
from typing import Literal
from pydantic import Field
from backend.runtime_v3.models import StrictModel
from backend.runtime_v3.life import capabilities


class SceneAction(StrictModel):
    actor_id: str
    target_ids: list[str] = Field(default_factory=list, max_length=8)
    source_event_id: str
    phase: Literal['start', 'continue', 'redirect', 'end', 'refuse', 'offer']
    modality: Literal['speech', 'physical', 'departure', 'other']
    adult: bool = False
    interruptible: bool = False
    response: Literal['none', 'open', 'player_supplied', 'involuntary'] = 'none'
    response_event_id: str | None = None
    player_evidence: str = ''
    knowledge_ids: list[str] = Field(default_factory=list, max_length=8)
    knowledge_use: Literal['assertion', 'inquiry'] = 'assertion'
    evidence: str


def scene_plan(state, scope):
    """Eligibility is permission, not selection of a semantic action or a quota.

    Reuse scope membership/ranking. Referenced authors cannot act merely because
    their letter was read; remote actors require an already available channel.
    """
    external = scope.controlled_actor_id
    ranked = sorted(scope.present_actor_ids | scope.remote_actor_ids,
                    key=lambda cid: (cid not in scope.present_actor_ids,
                                     -scope.actor_scores.get(cid, 0), cid))
    actors = []
    for cid in ranked:
        if cid == external or cid not in state['characters']:
            continue
        caps = capabilities(state, cid)
        if not caps['can_act']:
            continue
        actors.append(dict(actor_id=cid,
            channel='scene' if cid in scope.present_actor_ids else 'established_remote',
            capabilities={k: caps[k] for k in ('can_speak', 'can_move', 'adult_eligible')}))
    result = dict(external_actor_id=external, actors=actors[:8],
                budget=3, optional=True, extra_llm_calls=0)
    from backend.runtime_v3.remote_initiative import opportunities
    remote = opportunities(state)
    if remote:
        result['remote_opportunities'] = remote
    accepted_remote = sum(e['provenance'].startswith('npc_initiative:') and
        e['turn_id']==state['meta']['turn_id'] for e in state.get('remote_events',{}).values())
    if accepted_remote: result['budget']=max(0,result['budget']-accepted_remote)
    pressure = getattr(scope, 'continuity_decision', {}).get('pressure',0)
    if pressure: result['grounded_development_priority'] = pressure
    return result


def recorded_plan(messages):
    """Regeneration uses the original permit, never newly selected actors."""
    for message in messages:
        if message['content'].startswith('Director / GM-only\n'):
            return deepcopy(json.loads(message['content'].split('\n', 1)[1]).get('scene_agency', {}))
    return {}  # legacy contexts need no invented permit or new canonical data


def validate_actions(resolver, raw, events):
    """Optional event annotations cannot veto independently extracted outcomes."""
    from backend.runtime_v3.resolver import normalized
    external = resolver.protected_actor_id
    seen = set()
    for index, row in enumerate(raw.records['scene_actions']):
        def warning(code):
            resolver.warn('scene_actions', index, 'Необязательная аннотация инициативы отклонена.', code=code)
        try:
            claim = SceneAction.model_validate(row)
        except (ValueError, TypeError):
            warning('initiative_claim_invalid'); continue
        cid = claim.actor_id
        event = events.get(claim.source_event_id)
        if cid == external or not event or cid not in event['participants'] or not set(claim.target_ids) <= set(event['participants']):
            warning('initiative_event_invalid'); continue
        if claim.source_event_id in seen:
            warning('initiative_duplicate'); continue
        if claim.response_event_id is not None and (claim.response != 'player_supplied' or claim.response_event_id not in (resolver.continuity_decision or {}).get('pending_response_ids', [])):
            resolver.warn('scene_actions', index, 'Неизвестная ссылка ответа; аннотация пропущена.', code='initiative_response_reference_invalid'); continue
        if claim.response == 'player_supplied':
            quote = normalized(claim.player_evidence)
            if external not in claim.target_ids or not quote or quote not in normalized(resolver.player_input):
                warning('initiative_player_evidence_required'); continue
        invalid_knowledge = any(
            (k := resolver.before['knowledge'].get(key)) is None or k['actor_id'] != cid
            or k['status'] not in ('known', 'suspected')
            or k['status'] == 'suspected' and claim.knowledge_use != 'inquiry'
            for key in claim.knowledge_ids)
        if invalid_knowledge:
            warning('initiative_knowledge_invalid'); continue
        caps = capabilities(resolver.state, cid)
        stages=[caps]
        if cid in resolver.before['characters']: stages.append(capabilities(resolver.before,cid))
        # An action can precede same-turn incapacity/death, or follow recovery.
        # Final capabilities must not erase an accepted earlier Event.
        if not any(stage['can_act'] and (claim.modality!='speech' or stage['can_speak'])
                   and (claim.modality!='departure' or stage['can_move']) for stage in stages):
            warning('initiative_capability_invalid'); continue
        if claim.adult and any(not capabilities(resolver.state, a)['adult_eligible'] for a in [cid, *claim.target_ids]):
            warning('initiative_adult_context_required'); continue
        seen.add(claim.source_event_id)
        event['scene_action'] = claim.model_dump(exclude={'source_event_id', 'evidence'})
