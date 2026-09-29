"""Versioned tabletop state and strictly bounded command contracts."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Ability = Literal['strength', 'dexterity', 'constitution', 'intelligence', 'wisdom', 'charisma']
Mode = Literal['EXPLORATION', 'DIALOGUE', 'ENCOUNTER', 'AWAITING_ROLL']
ABILITIES = ('strength', 'dexterity', 'constitution', 'intelligence', 'wisdom', 'charisma')


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', validate_assignment=True)


class Ruleset(Model):
    id: str = 'd20-basic-v1'
    name: str = 'D20 Basic — D&D-подобные правила'
    version: int = 1
    capabilities: list[Literal['checks', 'combat', 'rests']] = ['checks', 'combat', 'rests']
    check_die: Literal[20] = 20
    critical: Literal['double_dice', 'max_dice'] = 'double_dice'
    short_rest_minutes: int = Field(default=60, ge=1, le=1440)
    long_rest_minutes: int = Field(default=480, ge=60, le=1440)
    skills: dict[str, Ability] = {'athletics': 'strength', 'stealth': 'dexterity', 'perception': 'wisdom', 'persuasion': 'charisma'}
    # This first implementation advertises only implemented capabilities.


class Attack(Model):
    name: str = 'Меч'
    ability: Ability = 'strength'
    die: Literal[4, 6, 8, 10, 12] = 8
    proficient: bool = True
    reach: int = Field(default=5, ge=5, le=120)


class CharacterSheet(Model):
    id: str
    name: str = Field(min_length=1, max_length=120)
    level: int = Field(default=1, ge=1, le=20)
    character_class: str = 'Воин'
    species: str = 'Человек'
    biography: str = Field(default='', max_length=3000)
    abilities: dict[Ability, int] = {'strength': 16, 'dexterity': 12, 'constitution': 14, 'intelligence': 10, 'wisdom': 12, 'charisma': 10}
    skill_proficiencies: list[str] = ['athletics', 'perception']
    save_proficiencies: list[Ability] = ['strength', 'constitution']
    hp: int = 12
    max_hp: int = Field(default=12, ge=1, le=1000)
    armor_class: int = Field(default=16, ge=1, le=30)
    speed: int = Field(default=30, ge=0, le=120)
    position: int = Field(default=0, ge=-10000, le=10000)
    attacks: dict[str, Attack] = {'sword': Attack()}
    inventory: list[str] = ['Меч', 'Щит', 'Кольчуга']
    features: list[str] = []
    spells: list[str] = []
    resources: dict[str, int] = {'hit_dice': 1}
    conditions: list[Literal['dodge', 'unconscious', 'dead', 'fled', 'stable']] = []
    death_successes: int = Field(default=0, ge=0, le=3)
    death_failures: int = Field(default=0, ge=0, le=3)
    faction: str = 'party'
    location: str = 'gate'
    goals: list[str] = []
    traits: list[str] = []
    knowledge: list[str] = []
    relationships: dict[str, int] = {}
    morale: float = Field(default=0.5, ge=0, le=1)

    @model_validator(mode='after')
    def valid(self):
        if set(self.abilities) != set(ABILITIES) or any(type(v) is not int or not 1 <= v <= 30 for v in self.abilities.values()):
            raise ValueError('Некорректные характеристики')
        if not 0 <= self.hp <= self.max_hp:
            raise ValueError('Некорректные HP')
        return self


class Setting(Model):
    id: str = 'old-watch'
    name: str = Field(default='Старая застава', min_length=1, max_length=120)
    description: str = Field(default='На границе леса стоит заброшенная застава. Ворота приоткрыты; во дворе виден старый сундук.', max_length=6000)


class Campaign(Model):
    name: str = Field(default='Тайна заставы', min_length=1, max_length=120)
    setting_id: str = 'old-watch'
    starting_location: str = 'gate'


class Encounter(Model):
    order: list[str] = []
    initiative: dict[str, int] = {}
    index: int = 0
    round: int = 1
    action: bool = True
    bonus_action: bool = True
    reaction: dict[str, bool] = {}
    movement: int = 30
    disengaged: bool = False


class PendingRoll(Model):
    id: str
    purpose: Literal['check', 'save', 'initiative', 'attack', 'damage', 'death']
    actor: str
    expression: str = '1d20'
    modifier: int = 0
    advantage: Literal[-1, 0, 1] = 0
    dc: int = 10
    target: str = ''
    ability: Ability = 'wisdom'
    skill: str = ''
    weapon: str = ''
    critical: bool = False
    resume: Literal['EXPLORATION', 'DIALOGUE', 'ENCOUNTER'] = 'EXPLORATION'


class SessionState(Model):
    mode: Mode = 'EXPLORATION'
    controlled_actor: str = 'hero'
    pending: PendingRoll | None = None


class GameState(Model):
    model_config = ConfigDict(extra='forbid', validate_assignment=False)  # validate complete transactions, not intermediate copies
    schema_version: Literal[1] = 1
    campaign: Campaign = Campaign()
    ruleset: Ruleset = Ruleset()
    world: Setting = Setting()
    party: list[str] = ['hero']
    characters: dict[str, CharacterSheet]
    npcs: dict[str, CharacterSheet]
    locations: dict[str, str] = {'gate': 'Двор заставы'}
    encounters: dict[str, Encounter] = {}
    active_encounter: str | None = None
    quests: dict[str, str] = {'watch': 'Осмотреть заставу и справиться с её обитателями.'}
    effects: list[dict] = []
    player_knowledge: dict[str, str] = {}
    dm_state: dict = {}
    game_time: int = 0
    session_state: SessionState = SessionState()

    def actors(self):
        return {**self.characters, **self.npcs}

    def actor(self, actor_id):
        try:
            return self.actors()[actor_id]
        except KeyError:
            raise ValueError('Участник не найден') from None

    @property
    def encounter(self):
        return self.encounters.get(self.active_encounter)

    @model_validator(mode='after')
    def invariants(self):
        if set(self.characters) & set(self.npcs):
            raise ValueError('Повтор ID участника')
        actors = self.actors()
        if self.session_state.controlled_actor not in self.party or not set(self.party) <= set(self.characters):
            raise ValueError('Некорректная партия')
        for key, actor in actors.items():
            if key != actor.id or actor.location not in self.locations:
                raise ValueError('Некорректное положение участника')
        p = self.session_state.pending
        if (self.session_state.mode == 'AWAITING_ROLL') != (p is not None):
            raise ValueError('Некорректное ожидание броска')
        if p and (p.actor != self.session_state.controlled_actor or p.target and p.target not in actors and p.target not in self.dm_state.get('objects', {})):
            raise ValueError('Некорректный бросок')
        e = self.encounter
        if self.active_encounter and (not e or not e.order or not set(e.order) <= set(actors) or not 0 <= e.index < len(e.order)):
            raise ValueError('Некорректная очередь')
        if self.session_state.mode == 'ENCOUNTER' and not e:
            raise ValueError('Отсутствует бой')
        return self


class Command(Model):
    """Public/DM command has no HP, roll values, actor override or state patch."""
    type: Literal['look', 'dialogue', 'check', 'save', 'attack', 'start_encounter', 'end_turn', 'dodge', 'dash', 'disengage', 'move', 'rest']
    target: str = Field(default='', max_length=120)
    ability: Ability = 'wisdom'
    skill: str = Field(default='', max_length=80)
    dc: int = Field(default=12, ge=5, le=25)
    weapon: str = Field(default='sword', max_length=80)
    distance: int = Field(default=0, ge=-120, le=120)
    rest: Literal['short', 'long'] = 'short'


class NewGame(Model):
    name: str = Field(default='Тайна заставы', min_length=1, max_length=120)
    character_name: str = Field(default='Искатель', min_length=1, max_length=120)
    biography: str = Field(default='', max_length=3000)
    companion: bool = True
    setting: Setting = Setting()
    ruleset: Ruleset = Ruleset()
