"""Typed envelopes at the existing draft provider boundary (not a world model)."""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from backend.services.draft_response import strict_loads

VERSION = 1

class ProtocolError(ValueError):
    def __init__(self, stage, errors):
        self.errors=[{'stage':stage,'contract_version':VERSION,'code':'invalid_response','world_path':None,**e} for e in errors]
        super().__init__('; '.join(e['report_path']+': '+e['message'] for e in self.errors))

def reject(stage,path,message):
    raise ProtocolError(stage,[dict(report_path=path,message=message)])

def decode(model,text,stage):
    try:return model.model_validate(strict_loads(text))
    except ValidationError as exc:
        raise ProtocolError(stage,[dict(report_path='/'+'/'.join(str(p).replace('~','~0').replace('/','~1') for p in e['loc']),message=e['msg']) for e in exc.errors(include_input=False)]) from exc
    except ValueError as exc:
        if isinstance(exc,ProtocolError):raise
        reject(stage,'/',str(exc))

class DTO(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)

class Replacement(DTO):
    issue_id: str = Field(min_length=1)
    issues: list[dict[str,Any]] = Field(min_length=1)
class Correction(DTO):
    replacements: list[Replacement] = Field(min_length=1)
class Basis(DTO):
    path: str = Field(min_length=1)
class Resolution(DTO):
    issue_id: str = Field(min_length=1)
    resolution: Literal['replaced','disproved','unresolved']
    reason: str = Field(min_length=1)
    basis: list[Basis] = Field(default_factory=list)
    issues: list[dict[str,Any]] = Field(default_factory=list)
    @model_validator(mode='after')
    def shape(self):
        if not self.reason.strip():raise ValueError('Нужно содержательное основание.')
        if self.resolution=='replaced' and not self.issues:raise ValueError('Замена требует непустой issues.')
        if self.resolution=='disproved' and (not self.basis or self.issues):raise ValueError('Опровержение требует basis и не добавляет issues.')
        return self
class Reaudit(DTO):
    resolutions: list[Resolution] = Field(min_length=1)

class Assignment(DTO):
    path: str
    value: Any
class Removal(DTO):
    op: Literal['remove']
    path: str
    expected: dict[str,Any]
class Addition(DTO):
    op: Literal['add_location']
    path: Literal['/locations/-']
    value: dict[str,Any]
    @model_validator(mode='after')
    def identity(self):
        if not isinstance(self.value.get('id'),str) or not self.value['id'].strip():raise ValueError('Нужен строковый ID локации.')
        return self
Operation = Assignment | Removal | Addition
class PatchReply(DTO):
    candidate_hash: str | None = None
    patches: list[Operation] = Field(min_length=1)
    @model_validator(mode='after')
    def supplied_hash(self):
        if 'candidate_hash' in self.model_fields_set and not self.candidate_hash:raise ValueError('Переданный candidate_hash должен быть непустой строкой.')
        return self
class PreservedUnknown(DTO):
    path: str
    author_excerpt: str = Field(min_length=8)
class QualityReply(PatchReply):
    patches: list[Operation]
    preserved_unknown: list[PreservedUnknown] = Field(default_factory=list)

class UnknownConfirmation(DTO):
    path: str
    actor_id: str
    field: str
    decision: Literal['preserve','unresolved']
    reason: str = Field(min_length=1)
    @model_validator(mode='after')
    def explained(self):
        if not self.reason.strip():raise ValueError('Нужно содержательное основание.')
        return self
class QualityAudit(DTO):
    issues: list[dict[str,Any]]
    unknown_confirmations: list[UnknownConfirmation]
