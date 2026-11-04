"""Bounded corrections to an unaccepted proposal, never patches to the world."""
import json
from typing import Any
from pydantic import BaseModel, ConfigDict
from backend.repositories.drafts import candidate_hash
from backend.services.draft_completeness import pointer
from backend.services.draft_response import strict_loads
from backend.services import draft_repair
from backend.services.draft_changes import Proposal


class Assignment(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    path: str
    value: Any


class Correction(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    proposal_hash: str
    patches: list[Assignment]
    drop_indices: list[int]


def scope(state, text, exc):
    """Map existing validator addresses to exact values in the proposal.

    Appended cards have actual candidate indices; references among new entities
    are checked on the entire trial, so operation order is immaterial.
    """
    try:proposal=strict_loads(text)
    except ValueError:return None
    if not isinstance(proposal,dict) or not isinstance(proposal.get('changes'),list):return None
    paths=list(getattr(exc,'proposal_paths',[]));world_paths=list(getattr(exc,'world_paths',[]))
    drops=list(getattr(exc,'drop_indices',[]))
    diagnostics=getattr(exc,'errors',[])
    if callable(diagnostics):
        diagnostics=diagnostics(include_url=False,include_context=False,include_input=False)
        for error in diagnostics:
            loc=error.get('loc',())
            # Do not grant replacement of the whole proposal/list/operation.
            if len(loc)>=3 and loc[0]=='changes' or loc in (('candidate_hash',),('rationale',)):
                paths.append('/'+'/'.join(str(p).replace('~','~0').replace('/','~1') for p in loc))
    else:world_paths.extend(e['path'] for e in diagnostics if isinstance(e,dict) and isinstance(e.get('path'),str))
    lengths={k:len(state.get(k,[])) for k in ('characters','locations')}
    for index,change in enumerate(proposal['changes']):
        if not isinstance(change,dict) or not isinstance(change.get('path'),str):continue
        root=change['path']
        if root in ('/characters/-','/locations/-'):
            name=root.split('/')[1];root=f'/{name}/{lengths[name]}';lengths[name]+=1
        for path in world_paths:
            if path==root or path.startswith(root+'/'):
                tail=path[len(root):]
                # Keep an entire meaningful record immutable when a diagnostic
                # does not identify its bad field. Such failures need editing.
                if tail or not isinstance(change.get('value'),(dict,list)):
                    paths.append(f'/changes/{index}/value'+tail)
    allowed=[]
    for path in dict.fromkeys(paths):
        try:
            parent=pointer(proposal,path.rsplit('/',1)[0])
            if isinstance(parent,dict) or isinstance(parent,list) and path.rsplit('/',1)[1].isdigit() and int(path.rsplit('/',1)[1])<len(parent):allowed.append(path)
        except (KeyError,IndexError,ValueError,TypeError):pass
    if not allowed and not drops:return None
    return dict(proposal_hash=candidate_hash(proposal),paths=allowed,drop_indices=sorted(set(drops)),
                world_paths=list(dict.fromkeys(world_paths)),diagnostics=diagnostics,reason=str(exc))


def messages(state, text, author_context, allowed, feedback=None):
    from backend.services.draft_initial import prompt_schema
    original={}
    for path in allowed['world_paths']:
        parent=path.rsplit('/',1)[0]
        try:original[parent]=pointer(state,parent)
        except (KeyError,IndexError,ValueError,TypeError):pass
    proposal=strict_loads(text)
    sections={c.get('path','').split('/')[2] for c in proposal['changes'] if isinstance(c,dict) and isinstance(c.get('path'),str) and c['path'].startswith('/world/') and len(c['path'].split('/'))>=3}
    schemas=prompt_schema()['properties']['world']['properties']
    return [dict(role='system',content='Адресная коррекция творческого предложения, не новое творчество. Исправь только диагностированные поля через patches; path обязан входить в allowed_paths. Нельзя переписывать хорошие изменения, исходный мир, авторские факты и ограничения или принимать будущие решения игрока. При запрещённом scope можно убрать только указанную операцию через drop_indices. Остальные записи и их зависимости сохраняются. Верни JSON по response_schema. proposal_hash скопируй точно. Полный исправленный пакет снова будет проверен атомарно.'),
            dict(role='user',content=json.dumps(dict(author_context=author_context,proposal=proposal,
                proposal_hash=allowed['proposal_hash'],allowed_paths=allowed['paths'],allowed_drop_indices=allowed['drop_indices'],
                diagnostics=allowed['diagnostics'],reason=allowed['reason'],previous_correction_error=feedback,
                original_records=original,controlled_actor_id=state['controlled_actor_id'],
                entities={'characters':[dict(id=c['id'],name=c['name']) for c in state['characters']],
                          'locations':[dict(id=c['id'],name=c['name']) for c in state['locations']],
                          'world_ids':{k:list(v) for k,v in state['world'].items() if isinstance(v,dict)}},
                record_schemas={k:schemas[k] for k in sections if k in schemas},
                proposal_schema=Proposal.model_json_schema(),response_schema=Correction.model_json_schema()),ensure_ascii=False,separators=(',',':')))]


def apply(text, reply, allowed):
    correction=Correction.model_validate(strict_loads(reply))
    proposal=strict_loads(text)
    if correction.proposal_hash!=allowed['proposal_hash'] or candidate_hash(proposal)!=allowed['proposal_hash']:
        raise ValueError('Коррекция относится к другой версии предложения.')
    drops=correction.drop_indices
    if len(set(drops))!=len(drops) or not set(drops)<=set(allowed['drop_indices']):raise ValueError('Удаление не разрешено диагностикой.')
    if any(p.path.startswith('/changes/'+str(i)+'/') for p in correction.patches for i in drops):raise ValueError('Нельзя исправлять и удалять одну операцию.')
    if not correction.patches and not drops:raise ValueError('Коррекция не содержит изменений.')
    corrected=draft_repair.apply(text,json.dumps({'patches':[p.model_dump() for p in correction.patches]},ensure_ascii=False),allowed['paths']) if correction.patches else text
    value=strict_loads(corrected)
    for i in sorted(drops,reverse=True):del value['changes'][i]
    if value==proposal:raise ValueError('Коррекция не изменила предложение.')
    return json.dumps(value,ensure_ascii=False)
