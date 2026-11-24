"""Records embedded in a branch's WorldState. Public cards never contain private NPC fields."""

from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_serializer, model_validator

Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=240)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Publication(Record):
    id: str
    author: str | None
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


class Article(Record):
    topic: Short
    title: Short
    summary: Text
    category: Short
    source: Short
    previous_id: Short | None = None
    event_id: Short | None = None


class Question(Record):
    id: str
    sender: str
    recipient: str
    anonymous: bool
    text: Text
    sequence: int
    minute: int
    hidden: bool = False
    publication_id: str | None = None


class Listing(Record):
    listing_key: Short
    title: Short
    description: Text
    category: Short
    location_id: Short | None = None


class EventListing(Listing):
    start: int = Field(ge=0)
    end: int | None = Field(default=None, ge=0)
    cancelled: bool = False


class Vacancy(Listing):
    employer: Short
    organization_id: Short | None = None
    employment: Literal["permanent", "temporary", "gig"]
    requirements: str = Field(default="", max_length=2000)
    schedule: str = Field(default="", max_length=600)
    pay: str = Field(default="", max_length=600)
    expires: int | None = Field(default=None, ge=0)
    closed: bool = False


class ListingStamp(Record):
    id: str
    sequence: int
    minute: int


class PostedEvent(EventListing, ListingStamp):
    previous_start: int | None = None
    version: int = Field(default=1, ge=1)


class VacancyTerms(Record):
    pay: str
    schedule: str
    requirements: str
    changed_at: int


class PostedVacancy(Vacancy, ListingStamp):
    previous_terms: list[VacancyTerms] = Field(default_factory=list)


class Application(Record):
    actor: str
    vacancy: str
    job_id: str
    pending_text: str
    event_id: str | None = None


# Optional additions to the #276 wire format. Historical snapshots and their
# patch digests distinguish absent fields from explicitly stored empty values.
CATALOG_COLLECTIONS = ("articles", "questions", "listings", "vacancies", "favorites", "applications",
                       "representatives", "invitations", "attendance_plans")
CATALOG_FIELDS = (*CATALOG_COLLECTIONS, "activity_index")


class SmartphoneState(Record):
    articles: dict[str, Article] = Field(default_factory=dict)
    questions: dict[str, Question] = Field(default_factory=dict)
    listings: dict[str, PostedEvent] = Field(default_factory=dict)
    vacancies: dict[str, PostedVacancy] = Field(default_factory=dict)
    favorites: dict[str, list[str]] = Field(default_factory=dict)
    applications: dict[str, Application] = Field(default_factory=dict)
    representatives: dict[str, str] = Field(default_factory=dict)
    attendance_plans: dict[str, str] = Field(default_factory=dict)
    invitations: dict[str, str] = Field(default_factory=dict)
    publications: dict[str, Publication] = Field(default_factory=dict)
    reactions: dict[str, Reaction] = Field(default_factory=dict)
    profiles: dict[str, str] = Field(default_factory=dict)
    dating: dict[str, DatingShelf] = Field(default_factory=dict)
    opened: dict[str, dict[str, int]] = Field(default_factory=dict)
    sequence: int = Field(default=0, ge=0)
    last_considered: int | None = None
    activity_index: int = Field(default=0, ge=0)

    @model_serializer(mode="wrap")
    def preserve_archived_shape(self, serialize):
        result = serialize(self)
        for key in CATALOG_FIELDS:
            if key not in self.model_fields_set:
                result.pop(key, None)
        return result


class PublicAction(Record):
    kind: Literal["post", "comment", "like", "repost"]
    author: Short
    target: str | None = None
    text: Text | None = None


Action = TypeVar("Action")


class Batch(Record, Generic[Action]):
    actions: list[Action] = Field(max_length=6)


class SearchResult(Record):
    candidates: list[Brief] = Field(max_length=8)


class AppCommand(Record):
    operation_id: Short
    actor_id: Short
    action: Literal[
        "open", "profile", "post", "comment", "like", "repost", "read", "refresh", "search", "accept", "skip",
        "generate", "ask", "answer", "hide", "plan", "invite", "favorite", "apply"
    ]
    app: Literal["social", "dating", "calls", "messages", "contacts", "news", "questions", "events", "work"]
    target: Short | None = None
    text: str = Field(default="", max_length=5000)
    desired: bool = True
    ids: list[Short] = Field(default_factory=list, max_length=80)
    marker: int | None = Field(default=None, ge=0)
    filters: SearchFilters | None = None

    @model_validator(mode="after")
    def valid_app(self):
        actions = {
            "dating": {"search", "accept", "skip"},
            "social": {"profile", "refresh", "post", "repost", "comment", "like", "read"},
            "news": {"generate", "comment", "like", "read"},
            "questions": {"ask", "answer", "hide", "comment", "like", "read"},
            "events": {"generate", "plan", "invite"},
            "work": {"generate", "favorite", "apply"},
        }
        if self.action != "open" and self.action not in actions.get(self.app, ()):
            raise ValueError("Действие недоступно в этом приложении.")
        if self.action in ("like", "repost", "comment", "accept", "skip", "ask", "answer", "hide",
                           "plan", "invite", "favorite", "apply") and not self.target:
            raise ValueError("Выбери запись.")
        if self.action in ("post", "comment", "ask", "answer", "invite", "apply") and not self.text.strip():
            raise ValueError("Введите текст.")
        if self.action == "search" and not self.filters:
            raise ValueError("Задай параметры поиска.")
        return self
