"""Setting-neutral communication records owned by canonical Runtime v3.

History records their transitions; it is not an independent messenger database.
"""

from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field


class RemoteModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CommunicationCapabilities(RemoteModel):
    # The existing capability flags remain the single source of channel availability.
    profile_version: Literal[1] = 1
    preset: Literal["unspecified", "none", "letters", "1939", "modern", "fantastic", "custom"] = "unspecified"
    letter: bool = False
    courier: bool = False
    telegram: bool = False
    landline: bool = False
    magic: bool = False
    delivery_policy: dict[Literal["text_message", "voice_call", "letter", "courier", "telegram", "landline", "magic"], Literal["instant", "delayed", "live"]] = Field(default_factory=dict)
    delivery_minutes: dict[Literal["letter", "courier", "telegram"], Annotated[int, Field(ge=1, le=5256000)]] = Field(default_factory=dict)
    author_note: str = Field(default="", max_length=2000)
    text_message: bool = False
    voice_call: bool = False
    presentation: Literal["none", "phone"] = "none"
    region: str = ""
    ring_timeout_minutes: int = Field(default=2, ge=1, le=60)
    emergency_numbers: dict[Literal["medical", "police", "fire"], str] = Field(
        default_factory=dict
    )


class Contact(RemoteModel):
    id: str
    owner_id: str
    character_id: str | None = None
    label: str = Field(min_length=1, max_length=160)
    address: str = Field(min_length=1, max_length=160)
    kind: Literal["person", "service", "shared"] = "person"
    blocked: bool = False
    available: bool = True
    identity_visible: bool = False
    provenance: str = Field(min_length=1, max_length=1000)
    created_at: int = Field(ge=0)


class Membership(RemoteModel):
    actor_id: str
    joined_at: int = Field(ge=0)
    left_at: int | None = Field(default=None, ge=0)
    provenance: str


class GroupPacing(RemoteModel):
    stimulus: str | None = None
    event_ids: list[str] = Field(default_factory=list)
    world_time: int = Field(ge=0)
    turn_id: int = Field(ge=0)
    operation_id: str


class ResponseRequest(RemoteModel):
    target_id: str
    expires_at: int = Field(ge=0)
    evidence: str = Field(min_length=1)
    provenance: str = Field(min_length=1)
    resolved_by: str | None = None
    closed_reason: Literal["membership", "death"] | None = None


class GroupRequestChange(RemoteModel):
    source_event_id: str
    target_id: str
    expires_at: int = Field(ge=0)
    evidence: str = Field(min_length=1)


class GroupResponseChange(RemoteModel):
    request_event_id: str
    response_event_id: str
    assertion: Literal["answered", "refused"]
    evidence: str = Field(min_length=1)


class Conversation(RemoteModel):
    id: str
    title: str = Field(default="", max_length=160)
    group: bool = False
    members: list[Membership] = Field(default_factory=list, max_length=128)
    contact_id: str | None = None
    initiative_pacing: GroupPacing | None = None
    provenance: str


HISTORICAL_CHANNELS = {"LETTER", "COURIER_LETTER", "TELEGRAM"}
TextChannel = Literal["TEXT_MESSAGE", "LETTER", "COURIER_LETTER", "TELEGRAM"]
RemoteChannel = Literal["TEXT_MESSAGE", "VOICE_CALL", "LETTER", "COURIER_LETTER", "TELEGRAM"]


class ChannelContent(RemoteModel):
    """Authored text is preserved; compute budgets belong to generation."""
    content: str = ""


class RemoteEvent(ChannelContent):
    id: str
    ordinal: int = Field(default=0, ge=0)
    channel: RemoteChannel
    sender_id: str
    recipient_ids: list[str] = Field(default_factory=list, max_length=16)
    contact_id: str | None = None
    destination: str
    service: Literal["medical", "police", "fire"] | None = None
    conversation_id: str | None = None
    delivery_due_at: int | None = Field(default=None, ge=0)
    world_time: int = Field(ge=0)
    updated_at: int = Field(ge=0)
    turn_id: int = Field(ge=0)
    status: Literal[
        "sent", "in_transit", "delivered", "undeliverable", "ringing", "answered", "declined", "missed", "ended"
    ]
    delivered_to: list[str] = Field(default_factory=list, max_length=16)
    read_by: list[str] = Field(default_factory=list, max_length=16)
    fact_ids: list[str] = Field(default_factory=list, max_length=8)
    provenance: str
    operation_id: str
    response_request: ResponseRequest | None = None


class RemoteCommand(ChannelContent):
    channel: TextChannel = "TEXT_MESSAGE"
    operation_id: str = Field(min_length=8, max_length=100)
    action: Literal[
        "send",
        "call",
        "read",
        "answer",
        "decline",
        "ignore",
        "end",
        "focus",
        "add_contact",
        "edit_contact",
        "create_group",
        "join",
        "leave",
        "remove",
        "resolve_contact",
    ]
    contact_id: str | None = None
    conversation_id: str | None = None
    event_id: str | None = None
    service: Literal["medical", "police", "fire"] | None = None
    label: str = Field(default="", max_length=160)
    address: str = Field(default="", max_length=160)
    kind: Literal["person", "service", "shared"] = "person"
    member_ids: list[str] = Field(default_factory=list, max_length=16)
    blocked: bool = False
    focus: Literal["physical", "call"] = "physical"
    character_id: str | None = None
    evidence: str = Field(default="", max_length=1000)


class RemoteProposal(RemoteModel):
    actor_id: str
    character_id: str | None = None
    action: Literal["send", "call", "answer", "decline", "read", "end", "identify"]
    contact_id: str | None = None
    conversation_id: str | None = None
    event_id: str | None = None
    content: str = ""
    basis_ids: list[str] = Field(default_factory=list, max_length=8)
    knowledge_ids: list[str] = Field(default_factory=list, max_length=8)
    speaker_name: str = Field(default="", max_length=160)
    existing_character_id: str | None = None


class EstablishedContact(RemoteModel):
    """An address actually established in this scene, never a generated number."""
    label: str = Field(min_length=1, max_length=160)
    address: str = Field(min_length=1, max_length=160)


class ExtractedRemoteEvent(ChannelContent):
    """Ordinary Extraction input to Remote, not a second persistent event model."""
    sender_id: str
    recipient_ids: list[str] = Field(min_length=1, max_length=16)
    channel: RemoteChannel
    minute: int | None = Field(default=None, ge=0)
    status: Literal["delivered", "ringing", "missed", "ended"] | None = None
    ended_at: int | None = Field(default=None, ge=0)
    contact_id: str | None = None
    conversation_id: str | None = None
    established_contact: EstablishedContact | None = None
    existing_event_id: str | None = None
    reader_id: str | None = None
    artifact_id: str | None = None
    source_event_id: str | None = None
    evidence: str = ""
