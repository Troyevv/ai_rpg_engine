"""Bounded semantic interpretation before creative world generation.

The result is authoring provenance/planning metadata, never Runtime truth.
Canonical entity IDs are allocated here; model-local keys are never persisted as
canonical identities. Interpretation cannot grant Character Knowledge.
"""
from typing import Literal
import json

from pydantic import Field, JsonValue, model_validator

from backend.runtime_v3.models import StrictModel, identity


class SourceSpan(StrictModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    quote: str = Field(min_length=1, max_length=10000)


class EntitySeed(StrictModel):
    key: str = Field(min_length=1, max_length=100, pattern=r'^[\w-]+$')
    kind: Literal['character', 'location', 'organization']
    name: str = Field(min_length=1, max_length=200)
    origin: Literal['explicit', 'inferred'] = 'explicit'
    tier: Literal['protagonist', 'core', 'secondary'] | None = None
    spans: list[SourceSpan] = Field(min_length=1, max_length=12)


class InterpretedClaim(StrictModel):
    classification: Literal['explicit', 'inferred', 'open', 'prohibition', 'ambiguity']
    subject_key: str | None = None
    section: Literal['character', 'appearance', 'personality', 'location', 'organization',
        'family', 'relationship', 'residence', 'role', 'fact', 'knowledge', 'history',
        'opening', 'setting', 'possession', 'contact', 'commitment']
    field: str = Field(min_length=1, max_length=100)
    value: JsonValue = None
    description: str = Field(min_length=1, max_length=3000)
    spans: list[SourceSpan] = Field(default_factory=list, max_length=12)
    time_scope: str = Field(default='', max_length=1000)
    visibility: Literal['author', 'player'] = 'author'
    holder_keys: list[str] = Field(default_factory=list, max_length=100)
    related_keys: list[str] = Field(default_factory=list, max_length=100)
    blocking: bool = False

    @model_validator(mode='after')
    def provenance_required(self):
        if self.classification in ('explicit', 'prohibition') and not self.spans:
            raise ValueError('explicit facts and prohibitions require source spans')
        if self.blocking and self.classification != 'ambiguity':
            raise ValueError('only material ambiguities can block interpretation')
        return self


class Interpretation(StrictModel):
    entities: list[EntitySeed] = Field(default_factory=list, max_length=200)
    claims: list[InterpretedClaim] = Field(default_factory=list, max_length=500)

    @model_validator(mode='after')
    def references(self):
        keys = {entity.key for entity in self.entities}
        if len(keys) != len(self.entities): raise ValueError('duplicate entity key')
        people = {entity.key for entity in self.entities if entity.kind == 'character'}
        if sum(entity.tier == 'protagonist' for entity in self.entities) > 1:
            raise ValueError('multiple protagonists require an explicit ambiguity')
        for claim in self.claims:
            if claim.subject_key is not None and claim.subject_key not in keys:
                raise ValueError('unknown claim subject')
            if set(claim.holder_keys) - people: raise ValueError('unknown knowledge holder')
            if set(claim.related_keys) - keys: raise ValueError('unknown related entity')
        return self


def _span(span, brief, path):
    if brief[span.start:span.end] == span.quote:
        return span.model_dump()
    # Models are unreliable at character offsets. A unique exact quote provides
    # deterministic evidence; repeated/absent quotes require a corrected result.
    start = brief.find(span.quote)
    if start >= 0 and brief.find(span.quote, start + 1) < 0:
        return dict(start=start, end=start+len(span.quote), quote=span.quote)
    raise ValueError(f'{path}: source quote is absent or ambiguous')


def accept(raw, brief, namespace, revision, previous=None):
    """Validate references/provenance and allocate stable application IDs."""
    from backend.services.initial_world_v2 import _check
    parsed = _check(Interpretation, raw, 'interpretation')
    entities = []
    ids = {}
    for index, entity in enumerate(parsed.entities):
        spans = [_span(span, brief, f'entities/{index}/spans') for span in entity.spans]
        # Namespace belongs to the workspace. Name + anchored first occurrence
        # distinguishes same-name identities without fuzzy merging.
        eid = identity(entity.kind, namespace, entity.name, spans[0]['start'])
        prior = [row for row in (previous or {}).get('entities', [])
                 if row['kind'] == entity.kind and row['name'] == entity.name]
        same_named = [row for row in parsed.entities if row.kind == entity.kind and row.name == entity.name]
        if len(prior) == len(same_named) == 1:
            eid = prior[0]['id']
        elif prior:
            anchored = [row for row in prior if row['spans'][0]['quote'] == spans[0]['quote']]
            if len(anchored) == 1: eid = anchored[0]['id']
        if eid in ids.values(): raise ValueError(f'entities/{index}: duplicate identity anchor')
        ids[entity.key] = eid
        row = entity.model_dump(exclude={'key'}); row.update(id=eid, spans=spans)
        entities.append(row)
    claims = []
    for index, claim in enumerate(parsed.claims):
        spans = [_span(span, brief, f'claims/{index}/spans') for span in claim.spans]
        row = claim.model_dump(exclude={'subject_key','holder_keys','related_keys'})
        row.update(spans=spans, subject_id=ids.get(claim.subject_key),
            holder_ids=[ids[key] for key in claim.holder_keys],
            related_ids=[ids[key] for key in claim.related_keys])
        row['id'] = identity('constraint', namespace, revision, index, json.dumps(row, sort_keys=True, ensure_ascii=False))
        claims.append(row)
    return dict(version=1, constraint_revision=revision, brief=brief,
        entities=entities, claims=claims,
        blocking_ids=[row['id'] for row in claims if row['blocking']],
        # No inferred/open claim is promoted to an explicit user fact.
        fixed_claim_ids=[row['id'] for row in claims if row['classification'] in ('explicit','prohibition')])


def messages(brief):
    contract = '''Interpret the user's world brief; do not generate missing story details.
Return one JSON object matching the schema. Entity keys are temporary references;
the application allocates canonical IDs. Preserve all named people, organizations
and places. Never merge same-name people without explicit evidence. Extract every
explicit age, appearance, personality, role, ownership, relationship and opening
constraint with exact source quotes. Keep omissions open, inferences labeled and
prohibitions explicit. Do not infer country, citizenship or jurisdiction from names.
Keep adoptive/biological/legal kinship distinct; parental plans for marriage are
intentions, never marriage, engagement, consent or romance. Distinguish affection
from romance. Preserve corporate parent/subsidiary links using related_keys.
Separate objective facts from per-character knowledge: holder_keys must contain
only established knowers and time_scope must preserve discovery chronology.
Secrets default to author visibility. Preserve the exact opening day/time/place
and activity already underway; do not choose the protagonist's next action.
Flag only material contradictions as blocking ambiguities. Missing routine details
are open, not blockers. Legal-career/jurisdiction uncertainty is an ambiguity,
never an invented factual resolution. All descriptions use the user's language.
value contains literal data/text; all entity references use subject_key,
related_keys and holder_keys, not invented canonical IDs inside value.
'''
    return [dict(role='system', content=contract+'\nJSON Schema:\n'+json.dumps(
        Interpretation.model_json_schema(), ensure_ascii=False, separators=(',', ':'))),
        dict(role='user', content=brief)]


def public_summary(plan):
    """Job/public views never reveal names, claims, quotes or secret existence."""
    return dict(constraint_revision=plan['constraint_revision'],
                needs_attention=bool(plan['blocking_ids']))


def run(preparation, jid, config, api_key, handle, loaded, stream_fn):
    from backend.services.continuation import request_context
    from backend.services.usage import tracked_stream
    repo=preparation.repo; job=repo.preparation_job(jid)
    brief=config['_draft_input']
    if config.get('_use_idea'):
        idea=repo.workspace(job['workspace_id'])['idea'].strip()
        if not idea:raise ValueError('Сначала создай сценарий в режиме Сценариста.')
        brief+='\n\n'+idea
    context=config['context_length']
    if loaded: context=min(context,int(loaded.get('config',{}).get('context_length') or context))
    request,limit=request_context(messages(brief),'',context,config['max_tokens'],format_hint='json')
    repo.draft_phase(jid,'interpreting')
    def opened(stream):
        handle.stream=stream
        if handle.cancel.is_set():stream.close()
    parts=[]
    for chunk in tracked_stream(repo,stream_fn,jid,'world_interpretation',config,request,
            model=config['model'],provider=config['provider'],api_key=api_key,
            temperature=config['temperature'],max_tokens=limit,require_complete=True,
            cancel_event=handle.cancel,on_stream=opened,
            **({'response_format':{'type':'json_object'}} if config['provider']=='deepseek' else {})):
        if handle.cancel.is_set():return
        parts.append(chunk)
    if handle.cancel.is_set():return
    try:raw=json.loads(''.join(parts))
    except (ValueError,TypeError) as exc:raise ValueError('interpretation: invalid JSON; previous interpretation retained') from exc
    # The repository assigns the next constraint revision and commits by CAS.
    repo.finish_interpretation_job(jid,raw,brief)
