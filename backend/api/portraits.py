"""Save-scoped portrait routes. No global asset route or filesystem mount."""
from fastapi import Request, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from backend.repositories import portraits
from backend.runtime_v3.models import PortraitCrop
from typing import Literal
from backend.runtime_v3.models import ProceduralPortrait


class PortraitEdit(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    revision: int = Field(ge=0)
    crop: PortraitCrop | None = None
    label: str | None = Field(default=None,max_length=120)
    stage: Literal['unknown','infant','child','adolescent','adult'] | None = None
    min_age: int | None = Field(default=None,ge=0,le=10000)
    max_age: int | None = Field(default=None,ge=0,le=10000)
    make_current: bool = False


def register(app,repo):
    register_drafts(app,repo)
    base='/api/saves/{sid}/characters/{cid}/portraits'
    @app.get(base)
    def list_portraits(sid:int,cid:str):
        return portraits.listing(repo,sid,cid)

    @app.post(base)
    async def upload(sid:int,cid:str,request:Request,revision:int,replace_id:str|None=None,settings:str="{}"):
        import json
        try:
            changes=PortraitEdit.model_validate(dict(json.loads(settings),revision=revision)).model_dump(exclude_unset=True,exclude={"revision"})
        except (ValueError,TypeError): raise HTTPException(422,"Некорректные настройки портрета.")
        from backend.services.portrait_assets import MAX_BYTES,decode_image
        # Validate access before buffering/decoding untrusted bytes.
        portraits.listing(repo,sid,cid)
        data=bytearray()
        async for chunk in request.stream():
            if len(data)+len(chunk)>MAX_BYTES: raise HTTPException(413,'Изображение больше 10 MiB.')
            data.extend(chunk)
        from starlette.concurrency import run_in_threadpool
        try:
            image=await run_in_threadpool(decode_image,bytes(data),request.headers.get('content-type',''))
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from exc
        return await run_in_threadpool(portraits.edit,repo,sid,cid,revision,image=image,portrait_id=replace_id,changes=changes)

    @app.patch(base+'/{pid}')
    def change(sid:int,cid:str,pid:str,body:PortraitEdit):
        changes=body.model_dump(exclude_unset=True,exclude={'revision'})
        if any(changes.get(k,'valid') is None for k in ('crop','label','stage')): raise HTTPException(422,'Некорректные поля портрета.')
        return portraits.edit(repo,sid,cid,body.revision,portrait_id=pid,changes=changes)

    @app.delete(base+'/{pid}')
    def remove(sid:int,cid:str,pid:str,revision:int):
        return portraits.edit(repo,sid,cid,revision,portrait_id=pid,remove=True)

    @app.get(base+'/assets/{aid}')
    def original(sid:int,cid:str,aid:str):
        try: content=portraits.asset(repo,sid,cid,aid)
        except ValueError: raise HTTPException(404,'Портрет недоступен.')
        return Response(content,media_type='image/png',headers={'Cache-Control':'private, no-store',
            'X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'none'"})


class ProceduralEdit(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision: int = Field(ge=0)
    descriptor: ProceduralPortrait
    mode: Literal['auto','procedural'] = 'procedural'


def register_drafts(app,repo):
    from backend.services import draft_portraits as drafts
    base='/api/workspaces/{wid}/draft/characters/{cid}/portraits'

    @app.get(base)
    def listing(wid:str,cid:str,author:bool=False):
        return drafts.listing(repo,wid,cid,author)

    @app.put(base+'/procedural')
    def procedural(wid:str,cid:str,body:ProceduralEdit):
        return drafts.edit(repo,wid,cid,body.revision,descriptor=body.descriptor.model_dump(),mode=body.mode)

    @app.post(base)
    async def upload(wid:str,cid:str,request:Request,revision:int,replace_id:str|None=None,settings:str='{}'):
        import json
        from backend.services.portrait_assets import MAX_BYTES,decode_image
        from starlette.concurrency import run_in_threadpool
        try:
            changes=PortraitEdit.model_validate(dict(json.loads(settings),revision=revision)).model_dump(exclude_unset=True,exclude={'revision'})
        except (ValueError,TypeError): raise HTTPException(422,'Некорректные настройки портрета.')
        with repo.connect() as db: drafts.load(repo,db,wid,cid,revision,editable=True)
        data=bytearray()
        async for chunk in request.stream():
            if len(data)+len(chunk)>MAX_BYTES: raise HTTPException(413,'Изображение больше 10 MiB.')
            data.extend(chunk)
        try: image=await run_in_threadpool(decode_image,bytes(data),request.headers.get('content-type',''))
        except ValueError as exc: raise HTTPException(422,str(exc)) from exc
        return await run_in_threadpool(drafts.edit,repo,wid,cid,revision,image=image,portrait_id=replace_id,changes=changes)

    @app.patch(base+'/{pid}')
    def change(wid:str,cid:str,pid:str,body:PortraitEdit):
        changes=body.model_dump(exclude_unset=True,exclude={'revision'})
        if any(changes.get(k,'valid') is None for k in ('crop','label','stage')): raise HTTPException(422,'Некорректные поля портрета.')
        return drafts.edit(repo,wid,cid,body.revision,portrait_id=pid,changes=changes)

    @app.delete(base+'/{pid}')
    def remove(wid:str,cid:str,pid:str,revision:int):
        return drafts.edit(repo,wid,cid,revision,portrait_id=pid,remove=True)

    @app.get(base+'/assets/{aid}')
    def asset(wid:str,cid:str,aid:str,author:bool=False):
        try: content=drafts.asset(repo,wid,cid,aid,author)
        except ValueError: raise HTTPException(404,'Портрет недоступен.')
        return Response(content,media_type='image/png',headers={'Cache-Control':'private, no-store',
            'X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'none'"})
