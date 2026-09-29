"""History audit is diagnostic, never a current-state validation prerequisite."""
INFORMATION_MEDIA = frozenset(('observation','conversation','message','testimony','discovery'))


def audit_world_history(history):
    warnings=[]
    def warning(section,index=None,code='history_invalid',reason='повреждена историческая запись'):
        warnings.append(dict(section=section,index=index,code=code,reason=reason))
    if not isinstance(history,dict):
        warning('history');return warnings
    events={}
    records=history.get('events',[])
    if not isinstance(records,list):warning('events');records=[]
    for i,event in enumerate(records):
        if not isinstance(event,dict) or not isinstance(event.get('id'),str):warning('events',i);continue
        if any(not isinstance(event.get(key,[]),list) or any(not isinstance(v,str) for v in event.get(key,[])) for key in ('witnesses','fact_ids')):
            warning('events',i);continue
        events[event['id']]=event
    records=history.get('knowledge_acquisitions',[])
    if not isinstance(records,list):warning('knowledge_acquisitions');records=[]
    for i,acquisition in enumerate(records):
        source=acquisition.get('source_event_id') if isinstance(acquisition,dict) else None
        event=events.get(source) if isinstance(source,str) else None
        medium=event.get('medium') if event else None
        if (not event or not isinstance(acquisition,dict) or not isinstance(medium,str) or
            acquisition.get('actor_id') not in event.get('witnesses',[]) or acquisition.get('fact_id') not in event.get('fact_ids',[]) or medium not in INFORMATION_MEDIA):
            warning('knowledge_acquisitions',i,'history_provenance_incomplete','неполное историческое происхождение; текущее знание сохранено')
    return warnings
