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


class ConstraintRule(StrictModel):
    stage: Literal['setting','places','characters','life','lore','opening']
    path: str = Field(min_length=2,max_length=500,pattern=r'^/')
    operator: Literal['equals','contains','absent','only'] = 'equals'
    expected: JsonValue = None
    where: dict[str,JsonValue] = Field(default_factory=dict)
    select: str | None = None

    @model_validator(mode='after')
    def canonical_target(self):
        from backend.services.initial_world_stages import STAGES
        import re
        root=self.path.split('/')[1].replace('~1','/').replace('~0','~')
        if root not in STAGES[self.stage].model_fields or re.search(r'~(?![01])',self.path):
            raise ValueError('rule path must target a canonical stage field')
        if self.operator=='only' and not isinstance(self.expected,list):
            raise ValueError('exact set rule requires an expected list')
        if self.select is not None and self.operator!='only':
            raise ValueError('select is only supported for exact set rules')
        return self


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
    rules: list[ConstraintRule] = Field(default_factory=list,max_length=30)

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
        def resolve(value):
            if isinstance(value,str) and value.startswith('@'):
                if value[1:] not in ids: raise ValueError(f'claims/{index}/rules: unknown entity reference')
                return ids[value[1:]]
            if isinstance(value,list): return [resolve(item) for item in value]
            if isinstance(value,dict): return {key:resolve(item) for key,item in value.items()}
            return value
        for rule in row['rules']:
            rule['path']='/'.join(resolve(part) for part in rule['path'].split('/'))
            rule['expected']=resolve(rule['expected']);rule['where']=resolve(rule['where'])
        row['id'] = identity('constraint', namespace, revision, index, json.dumps(row, sort_keys=True, ensure_ascii=False))
        claims.append(row)
    return dict(version=1, constraint_revision=revision, brief=brief,
        entities=entities, claims=claims,
        blocking_ids=[row['id'] for row in claims if row['blocking']],
        # No inferred/open claim is promoted to an explicit user fact.
        fixed_claim_ids=[row['id'] for row in claims if row['classification'] in ('explicit','prohibition')])


def messages(brief):
    contract = '''Interpret the user's world brief; do not generate missing story details.
For explicit facts/prohibitions attach canonical rules where representable. A rule
addresses a stage JSON pointer; use @entity_key for stable entity references in
path segments, expected and where. Stages: setting (/campaign), places (/locations,
/organizations,/parent_organizations), characters (/characters/@key, /cards/@key),
life (/objective_relations,/relationships,/residences,/roles,/possessions,/contacts),
lore (/facts,/knowledge,/initial_history), opening (/world_time,/camera,/calendar).
Use equals for a precise field, contains for a collection record subset, absent
for prohibited subsets, only with where/select for an exact holder set. Preserve
historical versus current scope. Do not derive birthdays from ages or replace
unknowns with false precision. Rules must be grounded in the quoted source.
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
    modern=config.get('_interpretation_version')==2
    from backend.services import world_blueprint as blueprint
    chunks=blueprint.fragments(brief) if modern else [brief]
    accepted=[]
    repo.draft_phase(jid,'interpreting')
    def opened(stream):
        handle.stream=stream
        if handle.cancel.is_set():stream.close()
    for fragment in chunks:
        data=json.dumps({'brief':fragment,'known_entities':list({e['key']:e for part in accepted for e in part['entities']}.values())},ensure_ascii=False) if modern else fragment
        request,limit=request_context((blueprint.messages if modern else messages)(data),'',context,config['max_tokens'],format_hint='json')
        pieces=[]
        for chunk in tracked_stream(repo,stream_fn,jid,'world_interpretation',config,request,
                model=config['model'],provider=config['provider'],api_key=api_key,
                temperature=config['temperature'],max_tokens=limit,require_complete=True,
                cancel_event=handle.cancel,on_stream=opened,
                **({'response_format':{'type':'json_object'}} if config['provider']=='deepseek' else {})):
            if handle.cancel.is_set():return
            pieces.append(chunk)
        if handle.cancel.is_set():return
        try:raw=json.loads(''.join(pieces))
        except (ValueError,TypeError) as exc:raise ValueError('interpretation: invalid JSON; previous interpretation retained') from exc
        if modern:
            from backend.services.initial_world_v2 import _check
            raw=_check(blueprint.Blueprint,raw,'blueprint').model_dump()
            blueprint.accept_parts([*accepted,raw],brief,job['workspace_id'],1)
        accepted.append(raw)
    # Existing standalone preview is atomic; creation uses durable per-fragment jobs.
    repo.finish_interpretation_job(jid,accepted if modern else accepted[0],brief,version=2 if modern else 1)


STAGE_SECTIONS = {
    'setting': {'setting'}, 'places': {'setting','location','organization','residence','opening'},
    'characters': {'character','appearance','personality','role','history','family','opening','commitment'},
    'life': {'relationship','family','residence','role','possession','contact','commitment'},
    'lore': {'fact','knowledge','history','family','commitment'},
    'opening': {'opening','setting','knowledge','commitment'},
}


def scoped_plan(plan):
    """Derived semantic inputs; canonical truth remains in Runtime records."""
    scopes={stage:{'claims':[row for row in plan['claims'] if row['classification']=='prohibition' or row['section'] in sections or any(r['stage']==stage for r in row.get('rules',[]))],
        **({'entities':plan['entities']} if stage=='setting' else {}),
        **({'creation':plan['creation']} if 'creation' in plan else {})} for stage,sections in STAGE_SECTIONS.items()}
    claims=scopes['characters']['claims']
    def targets(row):return {row.get('subject_id'),*row.get('related_ids',[])}-{None}
    scopes['character_global']={'claims':[r for r in claims if not targets(r)],'creation':plan.get('creation')}
    for entity in plan['entities']:
        if entity['kind']=='character':scopes['character_'+entity['id']]={'claims':[r for r in claims if entity['id'] in targets(r)]}
    from backend.services.generation_semantics import groups
    reviews=groups(plan)
    for stage in ('setting','places','characters','life','lore','opening'):
        scopes['review_'+stage]=[c for group in reviews if group['stage']==stage for c in group['claims']]
    plan['scopes']=scopes
    return plan
