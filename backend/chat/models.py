from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ModelSettings(Strict):
    provider: Literal['local', 'deepseek', 'compatible'] = 'local'
    model: str = Field(default='', max_length=160)
    temperature: float = Field(default=.8, ge=0, le=2)
    max_tokens: int = Field(default=4096, ge=128, le=131072)
    context_length: int = Field(default=32768, ge=2048, le=2097152)
    auto_context: bool = False
    auto_output: bool = False
    thinking: Literal['off', 'low', 'high'] = 'off'

    @model_validator(mode='after')
    def capacity(self):
        if not self.auto_context and not self.auto_output and self.max_tokens >= self.context_length * .8:
            raise ValueError('Оставьте место для входного контекста.')
        return self


class Settings(Strict):
    prompt: str = Field(max_length=100000)
    language: str = Field(default='Русский', max_length=80)
    reply: ModelSettings = Field(default_factory=lambda: ModelSettings(auto_context=True, auto_output=True))
    summary: ModelSettings = Field(default_factory=lambda: ModelSettings(temperature=.2, max_tokens=8192, auto_context=True, auto_output=True))
    soft_threshold: float = Field(default=.85, ge=.5, le=.95)
    summary_target: int = Field(default=6000, ge=256, le=65536)
    tail_tokens: int = Field(default=1200, ge=0, le=8192)


class Revision(Strict):
    revision: int = Field(ge=0)
    token: str = Field(min_length=8, max_length=100)


class Create(Strict):
    token: str = Field(min_length=8, max_length=100)
    name: str = Field(min_length=1, max_length=120)
    memory: str = Field(max_length=500000)
    settings: Settings
    source: dict | None = None


class Generate(Revision):
    kind: Literal['reply', 'summary', 'start', 'regenerate', 'retry'] = 'reply'
    text: str = Field(default='', max_length=100000)
    target: str | None = None
    next_chapter: bool = False


class Edit(Revision):
    branch: str
    message: str
    text: str = Field(min_length=1, max_length=100000)


class Configure(Revision):
    settings: Settings


class Memory(Revision):
    text: str = Field(max_length=500000)


class DraftEdit(Memory):
    draft_revision: int = Field(ge=0)


class Confirm(Memory):
    draft_revision: int = Field(default=0, ge=0)
    next_chapter: bool = True
    accept_partial: bool = False


class Select(Revision):
    branch: str


class Bookmark(Select):
    message: str
    enabled: bool = True
    note: str = Field(default='', max_length=2000)
    priority: int = Field(default=1, ge=0, le=2)


class CharacterEdit(Select):
    memory_id: str
    text: str = Field(min_length=1, max_length=500000)


class Source(Strict):
    world_id: int | None = None
    save_id: int | None = None
    revision: int | None = None
    history_turns: int = Field(default=2, ge=0, le=10)


class Creation(Strict):
    token: str = Field(min_length=8, max_length=100)
    name: str = Field(min_length=1, max_length=120)
    idea: str = Field(default='', max_length=100000)
    text: str = Field(default='', max_length=500000)
    settings: Settings
    source: Source | None = None


class CreationEdit(Creation, Revision):
    pass


class CreationGenerate(Revision):
    kind: Literal['initial', 'continue'] = 'initial'


class CreationConfirm(Revision):
    accept_partial: bool = False
