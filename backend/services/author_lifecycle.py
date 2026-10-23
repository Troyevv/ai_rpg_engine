"""Preparation of explicitly supplied ongoing pregnancy; no random outcomes.

Dates use the existing calendar. A date-only conception is an interval, never an
invented exact minute. Missing information that Runtime requires is diagnosed.
"""
from backend.runtime_v3 import models as m
from backend.runtime_v3.calendar import ordinal


def anchor_offset(doc):
    from backend.services.world_authoring_compiler import CompileError
    if not doc.pregnancies:
        return 0
    if not doc.opening.time.date:
        raise CompileError('opening/time/date', 'Для датированной беременности нужна дата начала мира.')
    profile=doc.opening.calendar.model_dump()
    start=ordinal(doc.opening.time.date,profile)
    earliest=min(ordinal(p.conception_earliest_date,profile) for p in doc.pregnancies)
    return max(0,start-earliest)*1440


def compile_pregnancies(doc, state, ids, actor, history, track):
    from backend.services.world_authoring_compiler import CompileError
    calendar=state['meta']['calendar'];profile=calendar['profile']
    start=ordinal(calendar['start_date'],profile) if doc.pregnancies else None
    def day(date):
        return calendar['start_minute']//1440*1440+(ordinal(date,profile)-start)*1440
    for row in doc.pregnancies:
        path='pregnancies/'+row.key;pid=ids[path]
        gestational=actor(row.gestational_actor,path+'/gestational_actor')
        impregnating=actor(row.impregnating_actor,path+'/impregnating_actor')
        parents=[actor(k,path+'/parents') for k in row.parents]
        earliest=day(row.conception_earliest_date);latest=day(row.conception_latest_date)+1439
        if earliest>latest or latest>state['meta']['world_time']:
            raise CompileError(path,'Интервал зачатия должен предшествовать началу мира.')
        if row.due.date is None or row.due.clock is None or row.due.weekday is not None or row.due.day_offset is not None or row.due.period is not None:
            raise CompileError(path+'/due','Runtime требует точную игровую границу срока; задайте дату и время явно, сохранив описание неопределённости.')
        due=day(row.due.date)+int(row.due.clock[:2])*60+int(row.due.clock[3:])
        if due<latest:raise CompileError(path+'/due','Срок предшествует зачатию.')
        if len({c.key for c in row.children})!=len(row.children):
            raise CompileError(path+'/children','Повторяющийся ключ будущего ребёнка.')
        if any(c.sex is None for c in row.children):
            raise CompileError(path+'/children','Runtime требует определённый исход пола каждого ребёнка; компилятор не выбирает его случайно. Уточните авторский исход до запуска.')
        children=[dict(id=m.identity('author_unborn',pid,c.key),sex=c.sex) for c in row.children]
        eid=m.identity('author_conception',pid)
        def supplied_fact(key, fallback, field):
            if key is None:return fallback
            fid=ids.get('facts/'+key)
            if fid not in state['facts']:raise CompileError(path+'/'+field,'Неизвестная ссылка на авторский факт.')
            return fid
        fact=supplied_fact(row.fact,m.identity('author_pregnancy_fact',pid),'fact')
        count=supplied_fact(row.count_fact,m.identity('author_pregnancy_count',pid),'count_fact')
        sexes={child['id']:supplied_fact(source.sex_fact,m.identity('author_child_sex',pid,child['id']),'children/'+source.key+'/sex_fact') for child,source in zip(children,row.children)}
        if row.fact is None:state['facts'][fact]=m.Fact(id=fact,text=row.description,visibility='secret',character_ids=[gestational]).model_dump()
        if row.count_fact is None:state['facts'][count]=m.Fact(id=count,text='child_count:'+str(len(children)),visibility='secret',character_ids=[gestational]).model_dump()
        for child in children:
            fid=sexes[child['id']]
            if fid not in state['facts']:state['facts'][fid]=m.Fact(id=fid,text='child_sex:'+child['sex'],visibility='secret',character_ids=[gestational]).model_dump()
        history['events'].append(dict(id=eid,text=row.description,time_description=row.conception_earliest_date+' … '+row.conception_latest_date,
            participants=[gestational,impregnating],witnesses=[],fact_ids=[fact],medium='other',after=[]))
        state['reproductive_events'][eid]=m.ReproductiveEvent(id=eid,participants=[gestational,impregnating],
            gestational_actor_id=gestational,impregnating_actor_id=impregnating,protection='unknown',
            source_event_id=eid,evidence=row.description,turn_id=0,earliest_minute=earliest,latest_minute=latest,
            conceived=True,pregnancy_id=pid,closed=True,policy=m.ReproductionPolicy()).model_dump()
        state['pregnancies'][pid]=m.Pregnancy(id=pid,event_id=eid,gestational_actor_id=gestational,parent_ids=parents,
            status='due' if due<=state['meta']['world_time'] else 'active',earliest_minute=earliest,latest_minute=latest,
            due_minute=due,children=children,fact_id=fact,count_fact_id=count,sex_fact_ids=sexes).model_dump()
        state['scheduled_events'][pid]=m.ScheduledEvent(id=pid,description='pregnancy_due',character_ids=[gestational],
            due_minute=due,type='pregnancy_due',evidence=row.due.description).model_dump()
        track(row,path,'world_state/pregnancies/'+pid)
