"""Thin draft endpoints. All authoritative state and validation are backend-side."""
import json
from typing import Any, Literal
from decimal import Decimal
from pydantic import Field
from fastapi.responses import PlainTextResponse
from backend.api.schemas import DTO, Revision, Credential, ModelConfig
from backend.services import draft_world as domain


class Import(Revision):
    text: str = Field(min_length=1,max_length=2000000)
    format: Literal['text','json'] = 'text'

class Change(Revision):
    operation: Literal['patch','add','remove','restore']
    kind: str = ''
    entity_id: str = ''
    field: str = ''
    value: Any = None
    source_id: int | None = None
    warnings_ack: bool = False

from backend.services.world_creation_settings import CreationSettings, CalendarPresets

from backend.runtime_v3.remote_models import CommunicationCapabilities

class ApplyCommunication(Revision):
    profile: CommunicationCapabilities

class ApplyPresets(Revision):
    presets: CalendarPresets

class ResponseBudget(DTO):
    max_total_tokens: int | None = Field(default=None,ge=1)
    max_cost_usd: Decimal | None = Field(default=None,ge=0)

class Generate(Revision,Credential):
    budget: ResponseBudget = Field(default_factory=ResponseBudget)
    creation_settings: CreationSettings = Field(default_factory=CreationSettings)
    task: Literal['world','field','character'] = 'world'
    text: str = Field(default='',max_length=100000)
    use_idea: bool = False
    kind: str = ''
    entity_id: str = ''
    field: str = ''
    warnings_ack: bool = False
    config: ModelConfig

class Resume(Credential):
    revision: int | None = None
    max_tokens: int | None = Field(default=None,ge=256,le=65536)
    context_length: int | None = Field(default=None,ge=8192)
    acknowledge_unknown: bool = False
    retry_last_fragment: bool = False

class CandidateChange(Revision):
    path: str
    value: Any

class MergeRelations(Revision):
    ids: list[str] = Field(min_length=2,max_length=2)

class Confirm(Revision):
    version_id: int
    accept_warnings: bool = False
    stop_review: bool = False


def install(app,repo,preparation,credentials,job):
    @app.get('/api/communication/presets')
    def communication_presets():
        from backend.services.communication_profile import catalog
        return catalog()

    @app.post('/api/workspaces/{wid}/draft/communication')
    def communication_profile(wid:str,body:ApplyCommunication):
        repo.apply_communication_profile(wid,body.revision,body.profile.model_dump())
        return repo.draft(wid,True)

    @app.post('/api/calendar/preview')
    def creation_calendar_preview(body:CreationSettings):
        from backend.services.calendar_presets import apply, preview
        from backend.runtime_v3.models import Calendar
        settings=body.model_dump();start=body.calendar_start
        cal=Calendar(start_minute=0,start_weekday=start.weekday or 0,start_date=start.date,
                     profile=start.profile or {}).model_dump()
        state={'creation_settings':settings,'world_clock':{'minute':0,'calendar':cal}}
        return preview(apply(state,(start.presets or CalendarPresets()).model_dump()))

    @app.post('/api/workspaces/{wid}/draft/calendar-preview')
    def proposed_calendar_preview(wid:str,body:CalendarPresets):
        from backend.services.calendar_presets import apply,preview
        value=repo.draft(wid,True)
        state=value.get('candidate') or value.get('state')
        if not state:raise ValueError('Сначала создайте мир.')
        return preview(apply(state,body.model_dump(),explicit=True))

    @app.get('/api/calendar/presets')
    def preset_catalog():
        from backend.services.calendar_presets import catalog
        return catalog()

    @app.post('/api/workspaces/{wid}/draft/calendar-presets')
    def apply_presets(wid:str,body:ApplyPresets):
        repo.apply_calendar_presets(wid,body.revision,body.presets.model_dump())
        return repo.draft(wid,True)

    @app.get('/api/workspaces/{wid}/draft/calendar-preview')
    def calendar_preview(wid:str):
        from backend.services.calendar_presets import preview
        value=repo.draft(wid,True)
        state=value.get('candidate') or value.get('state')
        if not state:raise ValueError('Сначала создайте мир.')
        return preview(state)

    @app.get('/api/workspaces/{wid}/draft')
    def draft(wid:str,author:bool=False):return repo.draft(wid,author)

    @app.patch('/api/workspaces/{wid}/draft/candidate')
    def candidate(wid:str,body:CandidateChange):
        repo.edit_candidate(wid,body.revision,body.path,body.value)
        return repo.draft(wid,True)

    @app.post('/api/workspaces/{wid}/draft/merge-relations')
    def merge_relations(wid:str,body:MergeRelations):
        repo.merge_draft_relations(wid,body.revision,body.ids)
        return repo.draft(wid,True)

    @app.get('/api/workspaces/{wid}/draft/raw')
    def raw(wid:str):
        current=repo.workspace(wid)['job']
        if not current:raise ValueError('Нет задания.')
        saved=repo.preparation_job(current['id'])
        journal=json.loads(saved.get('response_journal') or '{}')
        # Explicit allowlist: never export config, credentials or authorization headers.
        keys=('responses','pending','errors','review_failures','repair_failures','http_failures','review_recoveries',
              'quality','quality_attempts','review_strategies','review_resolutions','review_preparation_failures','internal_errors',
              'accepted_reviews','unknown_attempts','recovery_epoch','reserved_tokens','reserved_cost','actual_tokens','actual_cost','fragment_recoveries','binding')
        requests=[{k:r.get(k) for k in ('id','stage','status','finish_reason','usage_json','input_tokens','output_tokens','cost_usd')} for r in repo.request_log(job_id=current['id'])]
        draft=repo.draft(wid,True)
        return {'current_diagnostics':draft['validation'].get('diagnostics',[]),'current_start_block_reason':draft.get('start_block_reason'),
                'candidate_snapshot':draft.get('candidate') or draft.get('state'),'candidate_version':draft.get('version_id'),
                'author_input':{'text':json.loads(saved['config_json']).get('_draft_source',json.loads(saved['config_json']).get('_draft_input','')),'source_text':draft.get('source_text'),'outline':draft.get('outline')},
                'requests':requests,**{k:journal[k] for k in keys if k in journal},'recovery':{'status':saved['status'],'phase':saved.get('phase'),
                'revision':saved['revision'],'review':repo.draft(wid,True).get('review')}}

    @app.post('/api/workspaces/{wid}/draft/import')
    def import_world(wid:str,body:Import):
        repo.import_draft(wid,body.text,body.revision,body.format)
        return repo.draft(wid)

    @app.patch('/api/workspaces/{wid}/draft')
    def change(wid:str,body:Change):
        eid=repo.edit_draft(wid,body.revision,body.operation,body.kind,body.entity_id,body.field,body.value,body.source_id,body.warnings_ack)
        return {**repo.draft(wid,True),'entity_id':eid}

    @app.get('/api/workspaces/{wid}/draft/dependencies')
    def dependencies(wid:str,kind:str,entity_id:str):
        state=repo.draft(wid,True)['state']
        return domain.dependencies(state,kind,entity_id)

    @app.post('/api/workspaces/{wid}/draft/generate')
    def generate(wid:str,body:Generate):
        if body.task=='world' and not body.text.strip() and not body.use_idea:raise ValueError('Опиши желаемый мир.')
        if body.task!='world':
            state=repo.draft(wid,True)['state']
            domain.entity(state,body.kind,body.entity_id)
            if body.task=='character' and body.kind!='character':raise ValueError('Нужна карточка персонажа.')
            if body.task=='field' and body.field not in domain.FIELDS.get(body.kind,set()) and not(body.kind=='character' and body.field.startswith('fields.')):raise ValueError('Поле недоступно.')
        if body.task=='world' and body.creation_settings.calendar_start.presets is None:
            body.creation_settings.calendar_start.presets=CalendarPresets()
        config={**body.config.model_dump(),'_draft_task':body.task,'_draft_input':body.text,'_use_idea':body.use_idea,
                '_creation_settings':body.creation_settings.model_dump(), '_warnings_ack':body.warnings_ack,'_draft_target':{'kind':body.kind,'id':body.entity_id,'field':body.field}}
        if body.budget.max_total_tokens is not None:config['_draft_token_budget']=body.budget.max_total_tokens
        if body.budget.max_cost_usd is not None:config['_draft_cost_budget_usd']=str(body.budget.max_cost_usd)
        jid=preparation.submit(wid,'draft_'+body.task,body.text,config,body.revision,credentials.resolve(body.config.provider,body.key()))
        return job(jid)

    @app.post('/api/workspaces/{wid}/draft/resume')
    def resume(wid:str,body:Resume):
        current=repo.workspace(wid)['job']
        if not current: raise ValueError('Нет задания.')
        saved=repo.preparation_job(current['id'])
        provider=json.loads(saved['config_json'])['provider']
        preparation.resume(current['id'],credentials.resolve(provider,body.key()),revision=body.revision,
            config_changes={k:getattr(body,k) for k in ('max_tokens','context_length') if getattr(body,k) is not None},
            acknowledge_unknown=body.acknowledge_unknown,retry_last_fragment=body.retry_last_fragment)
        return job(current['id'])

    @app.post('/api/workspaces/{wid}/draft/confirm')
    def confirm(wid:str,body:Confirm):
        result=repo.confirm_draft(wid,body.revision,body.version_id,body.accept_warnings,body.stop_review)
        for stopped in result.get('start_decision',{}).get('stopped_jobs',[]):
            preparation.signal_stopped(stopped['id'],stopped['epoch'])
        return result

    @app.get('/api/workspaces/{wid}/draft/export')
    def export(wid:str,version_id:int,format:Literal['md','txt','json']='md'):
        value=repo.draft(wid,True)
        if value['version_id']!=version_id:raise ValueError('Версия изменилась. Обнови редактор.')
        text=json.dumps(value.get('candidate') if value.get('candidate') is not None else value['state'],ensure_ascii=False,indent=2) if format=='json' else domain.export_markdown(value['state'])
        return PlainTextResponse(text,media_type='application/json' if format=='json' else 'text/plain',headers={'Content-Disposition':f'attachment; filename="world.{format}"'})
