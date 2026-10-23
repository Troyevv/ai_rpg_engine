"""Versioned creative source models. No Runtime DTO in provider schemas."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

VERSION = 'world-authoring-1'
Origin = Literal['explicit', 'generated', 'unknown']
Level = Literal['very_low', 'low', 'neutral', 'high', 'very_high', 'unknown']


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)


class Record(Model):
    key: str = Field(min_length=1, max_length=100, pattern=r'^[\w-]+$')
    origin: Origin = 'generated'
    field_origins: dict[str, Origin] = Field(default_factory=dict)


class Seed(Record):
    kind: Literal['character', 'location', 'organization']
    name: str = Field(min_length=1, max_length=200)


class Observation(Model):
    section: str
    text: str = Field(min_length=1, max_length=20000)
    entities: list[str] = Field(default_factory=list)
    time_description: str = ''
    uncertain: bool = False


class AuthorBrief(Model):
    entities: list[Seed] = Field(default_factory=list, max_length=200)
    observations: list[Observation] = Field(default_factory=list, max_length=500)
    ambiguities: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def extraction_only(self):
        keys = [r.key for r in self.entities]
        if len(keys) != len(set(keys)):
            raise ValueError('author_brief/entities: duplicate key')
        if any(r.origin != 'explicit' for r in self.entities):
            raise ValueError('author_brief/entities: analysis cannot invent entities')
        for note in self.observations:
            if set(note.entities) - set(keys):
                raise ValueError('author_brief/observations: unregistered entity')
        return self


class World(Model):
    title: str = Field(min_length=1, max_length=300)
    setting: str = ''
    era: str = ''
    genre: str = ''
    tone: str = ''
    description: str = ''
    public_description: str = ''
    rules: str = ''


class Motive(Record):
    text: str = Field(min_length=1)


class Abilities(Model):
    conscious: bool | None = None
    can_perceive: bool | None = None
    can_act: bool | None = None
    can_speak: bool | None = None
    can_move: bool | None = None


class IdentityChange(Model):
    previous: str = Field(min_length=1)
    current: str = Field(min_length=1)
    date: str | None = None
    description: str = Field(min_length=1)


class Person(Record):
    name: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    age: str = ''
    role: str = ''
    biography: str = ''
    appearance: str = ''
    personality: str = ''
    communication: str = ''
    habits: str = ''
    strengths: str = ''
    weaknesses: str = ''
    fears: str = ''
    location: str | None = None
    situation: str = ''
    physical_state: str = ''
    birth_date: str | None = None
    life_status: Literal['alive', 'dead', 'missing', 'unknown'] = 'unknown'
    capabilities: Abilities = Field(default_factory=Abilities)
    developmental_stage: Literal['unknown', 'infant', 'child', 'adolescent', 'adult'] = 'unknown'
    reproductive_capability: Literal['can_become_pregnant', 'can_impregnate', 'neither', 'unknown'] = 'unknown'
    biological_sex: Literal['female', 'male'] | None = None
    identity_components: dict[str, str] = Field(default_factory=dict)
    name_changes: list[IdentityChange] = Field(default_factory=list)
    goals: list[Motive] = Field(default_factory=list)
    intentions: list[Motive] = Field(default_factory=list)
    obligations: list[Motive] = Field(default_factory=list)


class Place(Record):
    name: str = Field(min_length=1)
    description: str = ''
    kind: str = 'unknown'
    parent: str | None = None


class Organization(Record):
    name: str = Field(min_length=1)
    description: str = ''
    kind: str = 'unknown'
    parent: str | None = None
    locations: list[str] = Field(default_factory=list)


class Tie(Record):
    source: str
    target: str
    kind: Literal['spouse', 'partner', 'engaged', 'parent', 'adoptive_parent',
                  'guardian', 'foster_parent', 'step_parent', 'sibling', 'contact',
                  'friend', 'close_friend', 'coworker']
    status: Literal['active', 'closed'] = 'active'
    context: str = ''
    time_description: str = ''
    since_date: str | None = None
    until_date: str | None = None
    outcome: Literal['', 'ended', 'divorced', 'widowed', 'superseded', 'revoked'] = ''


class Feelings(Record):
    source: str
    target: str
    levels: dict[Literal['trust', 'affection', 'attraction', 'irritation', 'fear', 'jealousy', 'respect'], Level] = Field(default_factory=dict)
    context: str = ''


class Fact(Record):
    text: str = Field(min_length=1)
    secret: bool = False
    participants: list[str] = Field(default_factory=list)


class PastEvent(Record):
    text: str = Field(min_length=1)
    time_description: str = ''
    participants: list[str] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)
    witnesses: list[str] = Field(default_factory=list)
    medium: Literal['observation', 'conversation', 'message', 'testimony', 'discovery', 'other'] = 'other'
    after: list[str] = Field(default_factory=list)


class Knowing(Record):
    actor: str
    fact: str
    status: Literal['known', 'suspected', 'unknown', 'outdated', 'refuted', 'superseded']
    evidence: str = Field(min_length=1)
    event: str | None = None
    current: bool = True
    time_description: str = ''


class Phase(Record):
    status: Literal['active', 'closed'] = 'active'
    since_date: str | None = None
    until_date: str | None = None
    outcome: str = ''


class Residence(Phase):
    actor: str
    location: str
    context: str = ''


class Occupation(Phase):
    actor: str
    title: str
    kind: str
    organization: str | None = None
    context: str = ''


class Possession(Record):
    name: str
    kind: str
    description: str = ''
    owner: str | None = None
    holder: str | None = None
    location: str | None = None
    status: Literal['unknown', 'available', 'lost', 'destroyed'] = 'unknown'


class Contact(Record):
    owner: str
    character: str | None = None
    label: str = Field(min_length=1, max_length=160)
    address: str = Field(min_length=1, max_length=160)
    kind: Literal['person', 'service', 'shared'] = 'person'
    blocked: bool = False
    available: bool = True
    identity_visible: bool = False
    provenance: str = Field(min_length=1, max_length=1000)


class Condition(Record):
    actor: str
    description: str
    status: Literal['active', 'resolved', 'cancelled', 'unknown_outcome'] = 'active'
    duration: Literal['temporary', 'persistent', 'unknown'] = 'unknown'
    effects: Abilities = Field(default_factory=Abilities)
    evidence: str = ''


class Time(Model):
    description: str = ''
    date: str | None = None
    day_offset: int | None = Field(default=None, ge=-366, le=366)
    weekday: int | None = Field(default=None, ge=0, le=13)
    clock: str | None = Field(default=None, pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
    period: Literal['night', 'morning', 'afternoon', 'evening'] | None = None


class Commitment(Record):
    description: str
    participants: list[str] = Field(default_factory=list)
    location: str | None = None
    time: Time = Field(default_factory=Time)


class UnbornChild(Record):
    sex_fact: str | None = None
    sex: Literal['female', 'male'] | None = None


class Pregnancy(Record):
    fact: str | None = None
    count_fact: str | None = None
    gestational_actor: str
    impregnating_actor: str
    parents: list[str] = Field(default_factory=list)
    conception_earliest_date: str
    conception_latest_date: str
    due: Time
    children: list[UnbornChild] = Field(min_length=1, max_length=8)
    description: str = Field(min_length=1)


class Calendar(Model):
    system: Literal['gregorian', 'custom'] = 'gregorian'
    month_lengths: list[int] = Field(default_factory=list)
    month_names: list[str] = Field(default_factory=list)
    weekday_names: list[str] = Field(default_factory=list)


class Opening(Model):
    protagonist: str | None = None
    controlled: str | None = None
    pov: str | None = None
    location: str | None = None
    present: list[str] = Field(default_factory=list)
    situation: str
    time: Time
    calendar: Calendar = Field(default_factory=Calendar)


class Sections(Model):
    characters: list[Person] = Field(default_factory=list)
    locations: list[Place] = Field(default_factory=list)
    organizations: list[Organization] = Field(default_factory=list)
    objective_relations: list[Tie] = Field(default_factory=list)
    feelings: list[Feelings] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)
    events: list[PastEvent] = Field(default_factory=list)
    knowledge: list[Knowing] = Field(default_factory=list)
    residences: list[Residence] = Field(default_factory=list)
    roles: list[Occupation] = Field(default_factory=list)
    possessions: list[Possession] = Field(default_factory=list)
    conditions: list[Condition] = Field(default_factory=list)
    pregnancies: list[Pregnancy] = Field(default_factory=list)
    contacts: list[Contact] = Field(default_factory=list)
    commitments: list[Commitment] = Field(default_factory=list)


class Document(Sections):
    version: Literal['world-authoring-1'] = VERSION
    world: World
    opening: Opening
    uncertainties: list[str] = Field(default_factory=list)


class PlannedRecord(Model):
    section: Literal['characters', 'locations', 'organizations', 'objective_relations',
        'feelings', 'facts', 'events', 'knowledge', 'residences', 'roles', 'possessions', 'conditions', 'commitments', 'contacts', 'pregnancies']
    key: str = Field(min_length=1, max_length=100, pattern=r'^[\w-]+$')
    summary: str = Field(min_length=1, max_length=3000)
    references: list[str] = Field(default_factory=list)


class Plan(Model):
    world: World
    opening: Opening
    records: list[PlannedRecord] = Field(max_length=3000)
    uncertainties: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def registered(self):
        keys = [r.section + '/' + r.key for r in self.records]
        if len(set(keys)) != len(keys):
            raise ValueError('author_plan/records: duplicate key')
        if any(set(r.references) - set(keys) for r in self.records):
            raise ValueError('author_plan/records: unregistered reference; use section/key')
        return self


ANALYSIS_RULES = '''Extract only what the author has supplied. Do not invent missing
entities, biographies, motives or relationships. Entity origin must be explicit.
Preserve temporal scope, before/after disclosures and uncertain groups separately.
No quotes, character offsets, executable constraints or Runtime IDs are needed.
Return the requested JSON. The original source is retained independently.'''

AUTHOR_RULES = '''Create a coherent, rich world from the ORIGINAL idea, its analysis
and creation settings. Expand missing aspects, preserve detailed supplied traits.
Use natural prose for biography, personality, appearance and voice. Do not reduce
cards to adjectives. Use local keys and explicit references for executable facts.
Never generate technical Runtime fields. Register entities before referring to them.
Mark origin explicit/generated/unknown per record; use field_origins for mixed records.
Relationships belong in their sections, never independently editable duplicates.
Create only meaningful ties, never all possible character pairs. Directed feelings
are not reciprocal. Unknown levels are not neutral. Public facts do not grant knowledge.
Separate objective truth, communication events, current knowledge and previous knowledge.
Preserve vague temporal precision. The opening needs an author-visible exact clock
and calendar reference; creative choices must be acknowledged as uncertainties.
Only author-explicit goals/intentions/obligations/commitments may bind the controlled
actor. Never choose that actor's next action or consent. Optional circumstances need
not exist. Build starting circumstances, never a predetermined future plot.
Return only the requested structured JSON in the user's language.'''


class PageRecord(PlannedRecord):
    summary: str = Field(min_length=1, max_length=200)


class PlanPage(Model):
    """One bounded response; references may point to a later registered page."""
    world: World | None = None
    opening: Opening | None = None
    records: list[PageRecord] = Field(default_factory=list, max_length=32)
    complete: bool
    uncertainties: list[str] = Field(default_factory=list, max_length=8)


class CombinedBrief(AuthorBrief):
    entities: list[Seed] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
