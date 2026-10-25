"""Lossless normalization at the new-generation boundary, never save migration."""
from copy import deepcopy


def motivations(state):
    """Legacy short_goal is input once; later editor clears remain authoritative."""
    state=deepcopy(state)
    world=state.get('world')
    if not isinstance(world,dict) or not isinstance(world.get('characters'),dict):return state
    for cid, actor in world['characters'].items():
        if not isinstance(actor,dict):continue
        text=actor.get('short_goal','')
        if not isinstance(text,str):
            from backend.services.draft_initial import DraftErrors,error,escape
            raise DraftErrors([error('/world/characters/'+escape(cid)+'/short_goal','Ожидался текст.','string_type')])
        text=text.strip()
        if not text:continue
        if cid==state.get('controlled_actor_id'):
            if not actor.get('goals'):
                from backend.services.draft_initial import DraftErrors,error,escape
                raise DraftErrors([error('/world/characters/'+escape(cid)+'/short_goal','Цель управляемого героя требует явного подтверждения автора; исходный текст сохранён.','player_agency')])
            continue
        goals=actor.get('goals')
        if not goals:actor['goals']=[text]
        elif isinstance(goals,list) and all(isinstance(g,(str,dict)) for g in goals) and not any((g if isinstance(g,str) else g.get('text'))==text for g in goals):
            from backend.services.draft_initial import DraftErrors,error,escape
            raise DraftErrors([error('/world/characters/'+escape(cid)+'/goals',
                'short_goal и goals расходятся; оба значения сохранены.','motivation_conflict')])
    return state


def merge_duplicates(state):
    """Merge compatible directed pairs without interpreting text or averaging."""
    from backend.services.draft_initial import DraftErrors,error,escape
    from backend.runtime_v3.models import Relationship,Knowledge
    from pydantic import ValidationError
    for section, fields in [('relationships',('source_id','target_id')),('knowledge',('actor_id','fact_id'))]:
        records=state['world'][section];seen={};problems=[]
        for key,record in list(records.items()):
            model=Relationship if section=='relationships' else Knowledge
            try:model.model_validate({k:v for k,v in record.items() if k in model.model_fields} if isinstance(record,dict) else record)
            except ValidationError as exc:
                problems.extend(error('/world/'+section+'/'+escape(key)+'/'+ '/'.join(escape(p) for p in e['loc']),e['msg'],e['type']) for e in exc.errors(include_input=False))
                continue
            pair=tuple(record[f] for f in fields)
            if pair not in seen:seen[pair]=key;continue
            first=seen[pair];merged=deepcopy(records[first]);conflicts=[]
            for field,value in record.items():
                if field=='id':continue
                if field not in merged:merged[field]=deepcopy(value)
                elif merged[field]==value:continue
                elif section=='relationships' and field=='context':
                    merged[field]='\n\n'.join(x for x in (merged[field],value) if x)
                elif section=='relationships' and field=='dimensions':
                    for dim,number in value.items():
                        if dim in merged[field] and merged[field][dim]!=number:conflicts.append(field+'/'+escape(dim))
                        else:merged[field][dim]=number
                else:conflicts.append(field)
            if conflicts:
                problems.extend(error(f'/world/{section}/{escape(key)}/{f}',
                    'Несовместимые дубли; исходные значения сохранены.','duplicate',
                    related_paths=[f'/world/{section}/{escape(first)}/{f}']) for f in conflicts)
            else:records[first]=merged;del records[key]
        if problems:raise DraftErrors(problems)
    return state
