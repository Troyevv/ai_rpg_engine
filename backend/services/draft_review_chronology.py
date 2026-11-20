"""Compile one cited family chronology into the existing review proposal and diff."""
from bisect import bisect_left, bisect_right
import calendar as gregorian
import re

from pydantic import BaseModel, ConfigDict, Field

from backend.runtime_v3.birth_identity import dob_metadata, is_game_birth
from backend.runtime_v3.calendar import age_on, current_time, date_parts
from backend.services.draft_calendar import age_reference_date
from backend.services.draft_initial import escape


class ParentAtBirth(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    actor_id: str
    quote: str = Field(min_length=1)
    age: int | None = Field(default=None, ge=0, le=9999)
    died_at_birth: bool = False
    birth_year: int | None = Field(default=None, ge=1, le=9999)
    birth_year_quote: str = ''


class ConditionalMarriage(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    relation_id: str
    quote: str = Field(min_length=1)


def birth_path(cid):
    return '/world/characters/'+escape(cid)+'/birth_date'


def editable_birth(state, cid):
    actor = state['world']['characters'][cid]
    record = state.get('authoring', {}).get('calendar_completion', {}).get('birth_dates', {}).get(cid, {})
    source = dob_metadata(actor).get('source')
    return (not protected(state, birth_path(cid))
            and not is_game_birth(state['world'], cid) and record.get('value') == actor.get('birth_date')
            and ((source == 'authoring_automatic' and record.get('source') in ('automatic','review_creative'))
                 or (source == 'unknown' and record.get('source') == 'unknown' and record.get('known_year'))))


def year_days(year, profile):
    months = profile.get('month_lengths') if profile.get('system') == 'custom' else [
        gregorian.monthrange(year, m)[1] for m in range(1,13)]
    return [f'{year:04d}-{m:02d}-{d:02d}' for m,length in enumerate(months,1) for d in range(1,length+1)]


def exact_age(card):
    match = re.fullmatch(r'(\d{1,4})(?:\s+(?:лет|год|года))?', str(card['fields'].get('Возраст','')).strip())
    return int(match[1]) if match else None


def quoted(quote, sources):
    return bool(quote.strip()) and any(quote in text for text in sources if isinstance(text,str))


def protected(state, path):
    return any(path==p or path.startswith(p+'/') or p.startswith(path+'/')
               for p in state.get('authoring',{}).get('manual_paths',[]))


def number_in(value, quote):
    return re.search(r'(?<!\d)'+str(value)+r'(?!\d)', quote) is not None


def parent_evidence(base, child, proof, cards):
    world = base['state']['world']
    cid = proof.actor_id
    if cid not in cards or cid == child:
        raise ValueError('Проверьте ID родителя и ребёнка.')
    texts = [base.get('source'), cards[child]['fields'].get('Биография'), cards[cid]['fields'].get('Биография')]
    previous = base['state'].get('authoring',{}).get('calendar_completion',{}).get('family_chronologies',{}).get(child,{})
    for entry in previous.get('parent_evidence',[]):
        if entry['actor_id']==cid:
            texts.extend([entry['quote'],entry.get('birth_year_quote','')])
    for group, field in [('facts','character_ids'),('events','participants')]:
        texts.extend(r.get('text') for r in world[group].values() if {cid,child} <= set(r.get(field,[])))
    age_in_card = proof.died_at_birth and proof.age == exact_age(cards[cid])
    if not quoted(proof.quote,texts) or (proof.age is not None and not age_in_card and not number_in(proof.age,proof.quote)):
        raise ValueError('Возраст и связь родителя при рождении должны иметь основание в замысле или каноне.')
    if proof.birth_year and not (quoted(proof.birth_year_quote,texts) and number_in(proof.birth_year,proof.birth_year_quote)):
        raise ValueError('Не подтверждён год рождения родителя.')


def birthday_range(options, day, age):
    """Indices of dates strictly before delivery and compatible with a stated age."""
    end = bisect_left(options, day)
    if age is None:
        return 0, end
    year = int(day[:4])-age
    earliest = f'{year-1:04d}'+day[4:]
    latest = f'{year:04d}'+day[4:]
    return bisect_right(options,earliest), min(end,bisect_right(options,latest))


def has_compatible_birthday(options, day, age):
    start,end=birthday_range(options,day,age)
    return start<end


def plan_birth(base, cid, basis, exact_dates):
    state = base['state']
    world = state['world']
    actors = world['characters']
    clock = state['world_clock']
    cal = clock.get('calendar') or {}
    profile = cal.get('profile') or {}
    cards = {card['id']:card for card in state['characters']}
    refs = world['objective_relations']
    if cid not in cards:
        raise ValueError('Неизвестный ID ребёнка.')
    writable = editable_birth(state,cid)
    fixed_birth = actors[cid].get('birth_date') if not writable else None
    if not writable and not fixed_birth:
        raise ValueError('Для защищённой неизвестной даты требуется отдельное решение автора.')
    child = cards[cid]
    metadata = state.get('authoring',{}).get('calendar_completion',{})
    ledger = metadata.get('birth_dates',{}).get(cid,{})
    if ledger.get('known_year') not in (None,basis.year):
        raise ValueError('Указанный год расходится с ранее подтверждённым годом рождения.')
    sources = [base.get('source'),child['fields'].get('Биография'),actors[cid].get('biography')]
    sources.extend(f.get('text') for f in world['facts'].values() if cid in f.get('character_ids',[]))
    if not quoted(basis.quote,sources) or not number_in(basis.year,basis.quote):
        raise ValueError('Год рождения не подтверждён цитатой об этом персонаже.')
    today = age_reference_date(actors[cid],clock)
    age = exact_age(child)
    if not today:
        raise ValueError('Не установлена дата, на которую проверяется возраст ребёнка.')
    dates = [d for d in year_days(basis.year,profile) if d <= today and (age is None or age_on(d,today,profile)==age)]
    previous = metadata.get('family_chronologies',{}).get(cid,{})
    adjustable = set()
    def previously_chosen(path, value):
        return path in previous.get('adjustable',[]) and previous.get('date')==value and not protected(state,path)
    links = {r['source_id'] for r in refs.values() if r['kind']=='parent' and r['target_id']==cid}
    proofs = {p.actor_id:p for p in basis.parents}
    if len(proofs)!=len(basis.parents):
        raise ValueError('Один родитель указан дважды.')
    for old in previous.get('parent_evidence', []):
        original = ParentAtBirth.model_validate(old)
        supplied = proofs.get(original.actor_id)
        if supplied is None:
            proofs[original.actor_id]=original
            continue
        if ((original.age is not None and supplied.age not in (None,original.age))
                or (original.birth_year and supplied.birth_year not in (None,original.birth_year))):
            raise ValueError('Предложение противоречит ранее подтверждённым возрастам семьи.')
        proofs[original.actor_id] = supplied.model_copy(update={
            'age': original.age if supplied.age is None else supplied.age,
            'birth_year': supplied.birth_year or original.birth_year,
            'birth_year_quote': supplied.birth_year_quote or original.birth_year_quote,
            'died_at_birth': supplied.died_at_birth or original.died_at_birth,
            'quote': original.quote if original.age is not None and supplied.age is None else supplied.quote,
        })
    for proof in proofs.values():
        parent_evidence(base,cid,proof,cards)
    parent_ids = links | proofs.keys()
    parents = []
    constraints = {fixed_birth} if fixed_birth else set()
    updates = {}
    dependent = {}
    def minute_date(minute):
        value = current_time({'meta':{'world_time':clock['minute'],'calendar':cal}}, minute)['date']
        if not value:
            raise ValueError('Не удалось сопоставить датированное событие с календарём.')
        return value
    event_ids = list(dict.fromkeys([*previous.get('event_ids',[]), *basis.event_ids]))
    for eid in event_ids:
        event=world['events'].get(eid)
        if not event or not ({cid,*parent_ids} & set(event.get('participants',[]))):
            raise ValueError('Указанное событие рождения или смерти не связано с семьёй.')
        if event.get('minute') is not None:
            constraints.add(minute_date(event['minute']))
    for pid in sorted(parent_ids):
        actor = actors[pid]
        proof = proofs.get(pid)
        if actor.get('life_status')=='dead' and not proof:
            raise ValueError('Нужно уточнить по источнику, связана ли смерть родителя с родами.')
        died = bool(proof and proof.died_at_birth)
        if died and actor.get('life_status')!='dead':
            raise ValueError('В каноне отсутствует смерть указанного родителя.')
        required = proof.age if proof else None
        if died:
            card_age=exact_age(cards[pid])
            if card_age is not None and required is not None and required!=card_age:
                raise ValueError('Возраст при родах расходится с возрастом на дату смерти.')
            required = card_age if required is None else required
            death_path='/world/characters/'+escape(pid)+'/death_date'
            if actor.get('death_date') and not previously_chosen(death_path,actor['death_date']):
                constraints.add(actor['death_date'])
            elif not protected(state,death_path):
                adjustable.add(death_path)
            if actor.get('death_minute') is not None:
                constraints.add(minute_date(actor['death_minute']))
        current = exact_dates.get(pid) or actor.get('birth_date')
        parent_year = proof.birth_year if proof else None
        known_year = metadata.get('birth_dates',{}).get(pid,{}).get('known_year')
        if parent_year and known_year and parent_year!=known_year:
            raise ValueError('Указанный год рождения родителя расходится с ранее подтверждённым.')
        options = [current] if current else []
        missing_generated = (not current and not dob_metadata(actor).get('source')
                             and not protected(state,birth_path(pid)) and not is_game_birth(world,pid)
                             and (base.get('generated') or base.get('origin_job')))
        if parent_year and (editable_birth(state,pid) or missing_generated) and pid not in exact_dates:
            options = year_days(parent_year,profile)
            parent_now = exact_age(cards[pid])
            if not died and parent_now is not None:
                ref_date = age_reference_date(actor,clock)
                options = [d for d in options if age_on(d,ref_date,profile)==parent_now]
        elif parent_year and current and date_parts(current,profile)[0]!=parent_year:
            raise ValueError('Защищённая дата родителя не соответствует указанному году.')
        if not options and required is not None:
            raise ValueError('Для проверки возраста родителя нужна дата рождения или подтверждённый год.')
        if options:
            dates = [day for day in dates if has_compatible_birthday(options,day,required)]
        parents.append((pid,died,required,options,current))
    if sum(died for _,died,*_ in parents)>1:
        raise ValueError('Указано несколько умерших при родах матерей. Уточните источник.')
    approx = {a.relation_id:a for a in basis.conditional_marriages}
    marriages = {}
    for pid,died,*_ in parents:
        if not died:continue
        for rid,r in refs.items():
            pair={r['source_id'],r['target_id']}
            if not (r['kind']=='spouse' and r.get('outcome')=='widowed' and pid in pair and
                    (pair <= parent_ids or rid in approx)):continue
            path='/world/objective_relations/'+escape(rid)+'/until_date'
            conditional=approx.get(rid)
            if conditional and not quoted(conditional.quote,[r.get('context'),r.get('evidence'),base.get('source')]):
                raise ValueError('Условность прежней даты брака не подтверждена цитатой.')
            adjustable_end = conditional or previously_chosen(path,r.get('until_date'))
            if r.get('until_date') and (not adjustable_end or protected(state,path)):
                constraints.add(r['until_date'])
            elif not protected(state,path):
                adjustable.add(path)
            if r.get('until') is not None:constraints.add(minute_date(r['until']))
            if r.get('since_date'):dates=[d for d in dates if d>=r['since_date']]
            if r.get('since') is not None:dates=[d for d in dates if d>=minute_date(r['since'])]
            marriages[rid]=path
    if not approx.keys() <= marriages.keys():
        raise ValueError('Изменять можно лишь окончание брака, связанное со смертью при родах.')
    if constraints:
        dates=[d for d in dates if constraints=={d}]
    if not dates:
        raise ValueError('Нет общей даты, согласующей год рождения, возраст и связанные события. Требуется решение автора.')
    chosen = basis.preferred_date if basis.preferred_date in dates else dates[len(dates)//2]
    def creative(key,value,year):
        updates[key]=dict(source='review_creative',known_year=year,value=value,basis=basis.model_dump(exclude_defaults=True))
    if writable:
        creative(cid,chosen,basis.year)
    ages = []
    inventions = []
    if len(dates)>1:
        inventions.append(dict(name=child['name'],date=chosen))
    for pid,died,required,options,current in parents:
        start,end=birthday_range(options,chosen,required)
        legal=options[start:end]
        birth = current if current in legal else legal[len(legal)//2] if legal else None
        if birth and birth!=current:
            creative(pid,birth,int(birth[:4]))
            if len(legal)>1:
                inventions.append(dict(name=cards[pid]['name'],date=birth))
        if died:
            dependent['/world/characters/'+escape(pid)+'/death_date']=chosen
        ages.append(dict(id=pid,name=cards[pid]['name'],age=age_on(birth,chosen,profile),required=required,birth_date=birth,died=died,quote=proofs[pid].quote if pid in proofs else ''))
    for path in marriages.values():dependent[path]=chosen
    report=dict(child=cid,name=child['name'],date=chosen,year=basis.year,age=age,reference=today,parents=ages,
                marriage_ids=list(marriages),event_ids=event_ids,parent_evidence=[p.model_dump() for p in proofs.values()],options=len(dates),first=dates[0],last=dates[-1],
                inventions=inventions,adjustable=sorted(adjustable),anchored=bool(constraints),quote=basis.quote)
    return updates,dependent,report


def validate_result(state, reports, *, preview=True):
    world=state['world']
    clock=state['world_clock']
    profile=(clock.get('calendar') or {}).get('profile') or {}
    cards={c['id']:c for c in state['characters']}
    for report in reports:
        day=report['date']
        child=world['characters'][report['child']]
        if child.get('birth_date')!=day or int(day[:4])!=report['year'] or (report['age'] is not None and
                age_on(day,age_reference_date(child,clock),profile)!=report['age']) or exact_age(cards[report['child']])!=report['age']:
            raise ValueError('Итоговая дата рождения расходится с годом или возрастом ребёнка.')
        for parent in report['parents']:
            actor=world['characters'][parent['id']]
            age=age_on(actor.get('birth_date'),day,profile)
            if (preview and age!=parent['age']) or (parent['required'] is not None and age!=parent['required']):
                raise ValueError('Итоговый возраст родителя не соответствует хронологии семьи.')
            if parent['died'] and (actor.get('life_status')!='dead' or actor.get('death_date')!=day):
                raise ValueError('Дата смерти при родах расходится с датой рождения ребёнка.')
            if parent['died'] and actor.get('death_minute') is not None:
                if current_time({'meta':dict(world_time=clock['minute'],calendar=clock['calendar'])},actor['death_minute'])['date']!=day:
                    raise ValueError('Время смерти не совпадает с рассчитанным календарным днём.')
        for eid in report['event_ids']:
            event=world['events'].get(eid)
            if not event:
                raise ValueError('Связанное историческое событие отсутствует.')
            if event.get('minute') is not None:
                historical=current_time({'meta':dict(world_time=clock['minute'],calendar=clock['calendar'])},event['minute'])
                if historical['date']!=day:
                    raise ValueError('Дата связанного исторического события расходится с датой родов.')
        for rid in report['marriage_ids']:
            relation=world['objective_relations'][rid]
            if relation.get('until_date')!=day or relation.get('outcome')!='widowed' or (relation.get('since_date') or '')>day:
                raise ValueError('Дата или причина окончания брака расходится со смертью при родах.')


def validate_review(before, trial, reports):
    """A later change to a shared parent must also fit previously agreed family dates."""
    validate_result(trial, reports)
    previous = before.get('authoring',{}).get('calendar_completion',{}).get('family_chronologies',{})
    replaced = {report['child'] for report in reports}
    for child,report in previous.items():
        if child in replaced:continue
        actors = [child, *(p['id'] for p in report['parents'])]
        relevant = [('characters',cid) for cid in actors]
        relevant += [('events',eid) for eid in report['event_ids']]
        relevant += [('objective_relations',rid) for rid in report['marriage_ids']]
        if any(before['world'][group].get(key)!=trial['world'][group].get(key) for group,key in relevant):
            validate_result(trial,[report],preview=False)


class FamilyConfirmation(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    child: str
    parent: str
    died_at_birth: bool = False
    age: int | None = Field(default=None,ge=0,le=9999)
    birth_year: int | None = Field(default=None,ge=1,le=9999)
    conditional_marriages: list[str] = Field(default_factory=list)


def legacy_families(edit):
    state=edit['base']['state']
    cards={c['id']:c for c in state['characters']}
    relations=state['world']['objective_relations']
    families=[]
    for cid,record in (edit.get('calendar_decisions') or {}).items():
        if record.get('source')!='unknown' or not record.get('known_year'):continue
        parents=[]
        for pid in sorted({r['source_id'] for r in relations.values() if r['kind']=='parent' and r['target_id']==cid}):
            actor=state['world']['characters'][pid]
            marriages=[dict(id=rid,date=r.get('until_date'),partner=cards[next(x for x in
                (r['source_id'],r['target_id']) if x!=pid)]['name']) for rid,r in relations.items()
                if r['kind']=='spouse' and r.get('outcome')=='widowed' and pid in (r['target_id'],r['source_id'])]
            parents.append(dict(id=pid,name=cards[pid]['name'],dead=actor.get('life_status')=='dead',marriages=marriages))
        families.append(dict(id=cid,name=cards[cid]['name'],year=record['known_year'],parents=parents))
    return families


def confirmed_reply(edit, raw, confirmations):
    """Bind new, explicit author input to existing family IDs. Preserve the paid response verbatim."""
    from backend.services.draft_response import strict_loads
    packet=strict_loads(raw)
    available={(family['id'],p['id']):(family,p) for family in legacy_families(edit) for p in family['parents']}
    additions=[]
    seen=set()
    for item in confirmations:
        key=(item.child,item.parent)
        if key not in available or key in seen:
            raise ValueError('Подтверждение не относится к семье из сохранённого предложения.')
        seen.add(key)
        family,parent=available[key]
        if item.died_at_birth and not parent['dead']:
            raise ValueError('Родитель не указан умершим в этой версии мира.')
        if not set(item.conditional_marriages)<={m['id'] for m in parent['marriages']} or (item.conditional_marriages and not item.died_at_birth):
            raise ValueError('Условная дата брака не связана с указанной смертью.')
        basis=next((c['date_basis'] for c in packet['changes'] if c.get('path')==birth_path(item.child)
                    and (c.get('date_basis') or {}).get('kind') in ('creative_year','year_only')),None)
        if basis is None:
            raise ValueError('В сохранённом ответе отсутствует основание года рождения.')
        quote=f"Автор подтверждает родительство: {parent['name']} и ребёнок {family['name']}."
        if item.age is not None:quote+=f' Возраст при родах: {item.age}.'
        if item.died_at_birth:quote+=' Смерть родителя наступила при этих родах.'
        if item.birth_year is not None:quote+=f' Год рождения родителя: {item.birth_year}.'
        additions.append(quote)
        evidence=dict(actor_id=item.parent,quote=quote,died_at_birth=item.died_at_birth,age=item.age,
                      birth_year=item.birth_year,birth_year_quote=quote if item.birth_year else '')
        basis['parents']=[p for p in basis.get('parents',[]) if p['actor_id']!=item.parent]+[evidence]
        for rid in item.conditional_marriages:
            reason=f"Автор подтвердил условность даты окончания брака {rid} и его завершение в день смерти при родах."
            additions.append(reason)
            basis['conditional_marriages']=[r for r in basis.get('conditional_marriages',[]) if r['relation_id']!=rid]+[
                dict(relation_id=rid,quote=reason)]
    from json import dumps
    base=dict(edit['base'],source='\n'.join([edit['base'].get('source',''),*additions]))
    return dict(edit,base=base),dumps(packet,ensure_ascii=False)
