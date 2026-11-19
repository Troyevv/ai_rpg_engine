"""Shared deterministic time domain. Calendar labels never modify monotonic time."""
from dataclasses import dataclass, asdict
import re
from backend.runtime_v3.calendar import calendar_label
from backend.runtime_v3.commitments import temporal_boundaries, clock_barrier


@dataclass(frozen=True)
class TimeSkipRequest:
    start_minute: int
    target_minute: int
    reason: str = ''
    source: str = 'manual'
    wait_for_actor_id: str | None = None

    def __post_init__(self):
        if type(self.start_minute) is not int or type(self.target_minute) is not int or not 0 < self.target_minute-self.start_minute <= 10080:
            raise ValueError('Пропуск времени: выбери длительность от 1 минуты до 7 суток.')
        if self.source not in ('manual','sleep','wait','travel','long_action','narrative'): raise ValueError('Неизвестный источник Time Skip.')




NUMBERS = {'один':1,'одну':1,'два':2,'две':2,'три':3,'четыре':4,'пять':5,'шесть':6,'семь':7,'восемь':8,'девять':9,'десять':10,'двенадцать':12}


def parse_skip(text, now, cards=()):
    text = text.strip().casefold().rstrip('.!')
    # Only a direct player action, never quoted dialogue, negation or a hypothetical.
    if re.search(r'[«»"?]|\b(?:не|если|бы|возможно)\b', text): return None
    reason = text
    # An explicit sleep action can follow preparations in the same player input.
    # Restrict the clock calculation to that clause (not e.g. time spent packing).
    sleep = re.search(r'(?:^|[.,!]\s*|\s+(?:и|затем|потом)\s+)(?:я\s+)?(?P<action>(?:ложусь спать|сплю)\b.*)$', text)
    if sleep:
        text = sleep['action']
    match = re.match(r'^(?:я )?(сплю|ложусь спать|жду|ожидаю|еду|иду|путешествую|следующие|пропускаю)\b', text)
    if not match: return None
    source = {'сплю':'sleep','ложусь спать':'sleep','жду':'wait','ожидаю':'wait','еду':'travel','иду':'travel','путешествую':'travel','следующие':'long_action','пропускаю':'narrative'}[match[1]]
    duration = re.search(r'\b(\d+|'+'|'.join(NUMBERS)+r')\s+(минут\w*|час\w*|сут\w*|дн\w*)\b', text)
    target = None
    if duration:
        number = int(duration[1]) if duration[1].isdigit() else NUMBERS[duration[1]]
        target = now+number*(1 if duration[2].startswith('минут') else 60 if duration[2].startswith('час') else 1440)
    else:
        until = re.search(r'\bдо\s+(?:(следующего|завтрашнего)\s+|(завтра)\s+в\s+)?(\d{1,2}:\d{2}|вечера|утра|полуночи)\b', text)
        if until:
            clock = {'вечера':1080,'утра':420,'полуночи':0}.get(until[3])
            if clock is None:
                hour, minute = map(int,until[3].split(':'))
                if hour>23 or minute>59: raise ValueError('Неверное время Time Skip.')
                clock=hour*60+minute
            target=now//1440*1440+clock
            if until[1] or until[2] or target<=now: target+=1440
    waiting=None
    if source=='wait':
        who=re.fullmatch(r'(?:я )?(?:жду|ожидаю) (.+?) до .+',text)
        if who:
            matches=[]
            for card in cards:
                aliases=[card['name'].replace(' (ГГ)','').casefold(),*map(str.casefold,card.get('aliases',[]))]
                forms=set(aliases)
                for name in aliases:
                    if not name.strip(): continue
                    first=name.split()[0]
                    forms.add(first)
                    if first.endswith('а'):forms.add(first[:-1]+'у')
                    elif first.endswith('я'):forms.add(first[:-1]+'ю')
                    elif first.endswith('й'):forms.add(first[:-1]+'я')
                    else:forms.add(first+'а')
                if who[1] in forms:matches.append(card['id'])
            if len(matches)==1:waiting=matches[0]
    return TimeSkipRequest(now,target,reason,source,waiting) if target is not None else None


def plan_skip(state, request, *, version=1):
    candidates = [e for e in temporal_boundaries(state) if e['due_minute'] <= request.target_minute]
    controlled = state['camera']['controlled_actor_id']
    def interrupts_actor(e):
        arrival=(request.wait_for_actor_id is not None and request.wait_for_actor_id in e['character_ids'] and e.get('type')=='arrival' and e.get('location_id') is not None and e['location_id']==state['camera']['location_id'])
        return bool(controlled is not None and controlled in e['character_ids'] or arrival)
    interrupts = sorted((e for e in candidates if clock_barrier(e, version) and interrupts_actor(e)), key=lambda e:(e['due_minute'],e['id']))
    event = interrupts[0] if interrupts else None
    target = max(request.start_minute, event['due_minute']) if event else request.target_minute
    return dict(requested_target=request.target_minute, actual_target=target, elapsed_minutes=target-request.start_minute,
                requested_duration=request.target_minute-request.start_minute, interrupted=bool(event),
                interruption_event_id=event['id'] if event else None, source=request.source,
                background_results=[], background_candidates=len(candidates))


def interpreted_skip(state, request, planned, elapsed):
    """Resolve the actual endpoint against the completed scene and objective processes."""
    if elapsed is None or elapsed == planned['elapsed_minutes']:
        return planned
    if type(elapsed) is not int or not 0 <= elapsed <= 10080:
        from backend.runtime_v3.models import fatal
        fatal('Некорректная длительность пропуска времени.', 'invalid_time', section='scene')
    end = request.start_minute + elapsed
    if request.source == 'manual':
        end = min(end, request.target_minute)
    actual = plan_skip(state, TimeSkipRequest(request.start_minute, end), version=11) if end > request.start_minute else {}
    target = actual.get('actual_target', end)
    return dict(planned, actual_target=target, elapsed_minutes=target-request.start_minute,
                interrupted=bool(actual.get('interrupted') or target < request.target_minute),
                interruption_event_id=actual.get('interruption_event_id'))
