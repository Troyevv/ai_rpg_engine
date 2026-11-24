"""Records embedded in a branch's WorldState. Public cards never contain private NPC fields."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=240)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Publication(Record):
    id: str
    author: str
    minute: int
    sequence: int
    text: Text
    post_id: str | None = None
    reply_to: str | None = None


class ScenePublication(Record):
    author: Short
    text: Text
    target: Short | None = None
    player_evidence: str = ""
    evidence: str = ""  # Normalized by the shared Extraction decoder.


class Reaction(Record):
    author: str
    target: str
    kind: Literal["like", "repost"]
    minute: int
    sequence: int


class SearchFilters(Record):
    gender: Literal["any", "male", "female"] = "any"
    min_age: int = Field(default=18, ge=18, le=150)
    max_age: int = Field(default=60, ge=18, le=150)
    location: str = Field(default="", max_length=240)
    interests: str = Field(default="", max_length=1000)
    wishes: str = Field(default="", max_length=1500)

    @model_validator(mode="after")
    def ordered(self):
        if self.min_age > self.max_age:
            raise ValueError("Проверь диапазон возраста.")
        return self


class Brief(Record):
    name: Short
    age: int = Field(ge=18, le=150)
    gender: Literal["female", "male"]
    occupation: Short
    personality: Short
    appearance: Short
    interests: list[Short] = Field(min_length=1, max_length=10)
    location: Short
    bio: Text


class Candidate(Brief):
    id: str
    search_date: str | None
    skipped: bool = False
    character_id: str | None = None
    job_id: str | None = None


class DatingShelf(Record):
    searched: bool = False
    filters: SearchFilters = Field(default_factory=SearchFilters)
    candidates: dict[str, Candidate] = Field(default_factory=dict)
    results: list[str] = Field(default_factory=list)


class SmartphoneState(Record):
    publications: dict[str, Publication] = Field(default_factory=dict)
    reactions: dict[str, Reaction] = Field(default_factory=dict)
    profiles: dict[str, str] = Field(default_factory=dict)
    dating: dict[str, DatingShelf] = Field(default_factory=dict)
    opened: dict[str, dict[str, int]] = Field(default_factory=dict)
    sequence: int = Field(default=0, ge=0)
    last_considered: int | None = None


class PublicAction(Record):
    kind: Literal["post", "comment", "like", "repost"]
    author: Short
    target: str | None = None
    text: Text | None = None


class Batch(Record):
    actions: list[PublicAction] = Field(max_length=6)


class SearchResult(Record):
    candidates: list[Brief] = Field(max_length=8)


class AppCommand(Record):
    operation_id: Short
    actor_id: Short
    action: Literal[
        "open", "profile", "post", "comment", "like", "repost", "read", "refresh", "search", "accept", "skip"
    ]
    app: Literal["social", "dating", "calls", "messages", "contacts"]
    target: Short | None = None
    text: str = Field(default="", max_length=5000)
    desired: bool = True
    ids: list[Short] = Field(default_factory=list, max_length=80)
    marker: int | None = Field(default=None, ge=0)
    filters: SearchFilters | None = None

    @model_validator(mode="after")
    def valid_app(self):
        if self.action != "open":
            required = "dating" if self.action in ("search", "accept", "skip") else "social"
            if self.app != required:
                raise ValueError("Действие недоступно в этом приложении.")
        if self.action in ("like", "repost", "comment", "accept", "skip") and not self.target:
            raise ValueError("Выбери запись.")
        if self.action in ("post", "comment") and not self.text.strip():
            raise ValueError("Введите текст.")
        if self.action == "search" and not self.filters:
            raise ValueError("Задай параметры поиска.")
        return self
