"""Scene agency projections and claims for the existing Director/Resolver.

No autonomous clock, character agent, romance state or persistent permit store.
"""
from copy import deepcopy
import json
from typing import Literal
from pydantic import Field
from backend.runtime_v3.models import StrictModel, fatal
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
    """Validate structured semantic claims; normal domain handlers own effects.

    Deliberately no keyword parser pretending to verify arbitrary narrative prose.
    Violations reject the turn atomically, not only an inconvenient audit record.
    """
    from backend.runtime_v3.resolver import normalized
    rows = raw.records['scene_actions']
    if not rows:
        return
    permit = resolver.initiative_decision or {}
    actors = {r['actor_id']: r for r in permit.get('actors', [])}
    def reject(code):
        fatal('Некорректная инициатива персонажа.', code, repairable=False, section='scene_actions')
    if len(rows) > permit.get('budget', 0):
        reject('initiative_budget_exceeded')
    external = resolver.before['camera']['controlled_actor_id']
    if permit.get('external_actor_id') != external:
        reject('initiative_control_mismatch')
    seen = set()
    for row in rows:
        try:
            claim = SceneAction.model_validate(row)
        except (ValueError, TypeError):
            reject('initiative_claim_invalid')
        cid = claim.actor_id
        if cid == external or cid == resolver.protected_actor_id or cid not in actors:
            reject('initiative_actor_ineligible')
        event = events.get(claim.source_event_id)
        if not event or cid not in event['participants'] or not set(claim.target_ids) <= set(event['participants']):
            reject('initiative_event_invalid')
        # One semantic action per Event; never overwrite another actor's audit.
        key = claim.source_event_id
        if key in seen:
            reject('initiative_duplicate')
        seen.add(key)
        if not normalized(claim.evidence) or normalized(claim.evidence) not in normalized(resolver.narrative):
            reject('initiative_evidence_invalid')
        caps = capabilities(resolver.before, cid)
        if not caps['can_act'] or claim.modality == 'speech' and not caps['can_speak'] or claim.modality == 'departure' and not caps['can_move']:
            reject('initiative_capability_invalid')
        if actors[cid]['channel'] != 'scene' and claim.modality in ('physical', 'departure'):
            reject('initiative_channel_invalid')
        if claim.modality == 'physical' and not set(claim.target_ids) <= set(resolver.before['camera']['present_character_ids']):
            reject('initiative_target_absent')
        if claim.adult and any(not capabilities(resolver.before, a)['adult_eligible'] for a in [cid, *claim.target_ids]):
            reject('initiative_adult_context_required')
        if external in claim.target_ids:
            if claim.interruptible and claim.response not in ('open', 'player_supplied'):
                reject('initiative_response_required')
            if claim.response == 'player_supplied' and (not normalized(claim.player_evidence) or normalized(claim.player_evidence) not in normalized(resolver.player_input)):
                reject('initiative_player_evidence_required')
            if claim.response == 'involuntary':
                # A label alone cannot grant an involuntary outcome. #68 validates
                # the causal evidence and the domain result independently.
                if not any(c.get('actor_id') == external and c.get('source_event_id') == claim.source_event_id for c in raw.records['consequences'] if isinstance(c, dict)):
                    reject('initiative_consequence_required')
        elif claim.response in ('player_supplied', 'involuntary'):
            reject('initiative_response_target_invalid')
        if claim.response_event_id is not None:
            pending = (resolver.continuity_decision or {}).get('pending_response_ids', [])
            if claim.response != 'player_supplied' or claim.response_event_id not in pending:
                reject('initiative_response_reference_invalid')
        for key in claim.knowledge_ids:
            knowledge = resolver.before['knowledge'].get(key)
            if (not knowledge or knowledge['actor_id'] != cid
                    or knowledge['status'] not in ('known', 'suspected')
                    or knowledge['status'] == 'suspected' and claim.knowledge_use != 'inquiry'):
                reject('initiative_knowledge_invalid')
        event['scene_action'] = claim.model_dump(exclude={'source_event_id', 'evidence'})
        # Event already carries canonical identity, evidence, participants,
        # audience, turn and time. No duplicate social state or pending-action FSM.
