"""Durable principles on Character, separate from goals and personality items.

Reuse the existing development evidence cache/archive and Resolver/History. No
morality scores, second psychology pipeline or unconditional model call.
"""
from copy import deepcopy
import logging
from typing import Literal
from pydantic import Field
from backend.runtime_v3.models import StrictModel, DurableValue, DevelopmentEvidence, identity
from backend.runtime_v3.personality import visible_item
from backend.runtime_v3.lifecycle import record_change

LABELS=('Ценности', 'Приоритеты')


class ValueDelta(StrictModel):
    actor_id: str
    item_id: str = Field(min_length=1,max_length=100)
    operation: Literal['establish','refine','retire']
    text: str = Field(default='',max_length=2000)
    expected_revision: int = Field(ge=0)
    expected_text: str | None
    basis: Literal['explicit_statement','sustained_behavior']
    evidence_ids: list[str] = Field(default_factory=list,max_length=8)
    source_event_id: str | None = None
    player_evidence: str = ''
    player_assertion: Literal['explicit_value'] | None = None
    evidence: str = Field(min_length=1,max_length=1000)
    rationale: str = Field(min_length=1,max_length=600)


def salvage_values(state):
    """Optional fields degrade locally at the read boundary; archive untouched."""
    for cid,actor in state.get('characters',{}).items():
        if not isinstance(actor,dict): continue
        values=actor.get('values')
        if values is None: continue
        valid={}
        if isinstance(values,dict):
            for key,value in values.items():
                try:
                    entry=DurableValue.model_validate(value).model_dump()
                    if entry['id']!=key: raise ValueError('value identity mismatch')
                    valid[key]=entry
                except (ValueError,TypeError):
                    logging.getLogger(__name__).warning('Ignoring malformed optional value %s/%s',cid,key)
        else: logging.getLogger(__name__).warning('Ignoring malformed optional values for %s',cid)
        actor['values']=valid


def initialize_values(snapshot):
    for card in snapshot.get('character_cards',[]):
        actor=snapshot['world_state']['characters'].get(card['id'])
        if actor is None or actor.get('values') is not None: continue
        actor['values']={}
        for label in LABELS:
            text=card.get('fields',{}).get(label,'')
            if not isinstance(text,str) or not text.strip(): continue
            # Preserve verbatim; no reinterpretation of biography/personality.
            for index in range(0,len(text),2000):
                key=identity('value',card['id'],label,index)
                actor['values'][key]=DurableValue(id=key,text=text[index:index+2000]).model_dump()
    return snapshot


def project_values(card, actor, *, state=None, observer=None):
    result=deepcopy(card)
    if actor.get('values') is not None:
        fields=result.setdefault('fields',{})
        for label in LABELS: fields.pop(label,None)
        texts=[r['text'] for r in actor['values'].values() if r['status']=='active'
               and (state is None or visible_item(state,actor['id'],r,observer))]
        if texts: fields['Ценности']='\n'.join(texts)
    return result


def apply_values(resolver, raw, events):
    from backend.runtime_v3.resolver import normalized
    aliases={row.get('id'): (row.get('actor_id'), identity('development',row.get('actor_id'),events[row['source_event_id']]['id']))
             for row in raw.records['development_evidence'] if isinstance(row,dict)
             and isinstance(row.get('id'),str) and isinstance(row.get('source_event_id'),str) and row['source_event_id'] in events}
    touched=set()
    for index,row in resolver.records(raw,'value_deltas'):
        change=resolver.typed(ValueDelta,row,'value_deltas',index)
        if not change: continue
        cid=change['actor_id'];actor=resolver.state['characters'].get(cid)
        def reject(reason,code='value_invalid'):
            resolver.warn('value_deltas',index,reason,entity=cid,code=code)
        if actor is None or actor['life_status']=='dead' or actor['developmental_stage']=='infant':
            reject('Персонаж не может иметь новые установленные принципы.');continue
        external=cid==resolver.protected_actor_id
        if external and resolver.mode=='background':
            reject('Фон не меняет ценности EXTERNAL.','value_agency');continue
        old=(actor.get('values') or {}).get(change['item_id'])
        if ((old or {}).get('revision',0)!=change['expected_revision'] or (old or {}).get('text')!=change['expected_text']
            or (cid,change['item_id']) in touched or old and old['status']!='active'):
            reject('Устаревшая или конфликтующая дельта.','value_conflict');continue
        if (change['operation']=='establish') != (old is None):
            reject('Establish требует новый ID, refine/retire — существующий.');continue
        if (change['operation']=='retire' and change['text']) or (change['operation']!='retire' and not change['text'].strip()):
            reject('Неправильный текст операции.');continue
        sources=[]
        if change['basis']=='explicit_statement':
            event=events.get(change['source_event_id'])
            quote=normalized(change['player_evidence'])
            if (not event or cid not in event['participants'] or normalized(change['evidence']) not in normalized(resolver.narrative)
                or external and (change['player_assertion']!='explicit_value' or not quote or quote not in normalized(resolver.player_input))):
                reject('Нет принятого явного заявления о долговременной ценности.','value_agency');continue
            sources=[dict(id=event['id'],source_event_id=event['id'],source_turn=resolver.turn_id,
                          witnesses=event['witnesses'],fact_ids=event['fact_ids'],player_owned=external)]
        else:
            profile=actor.get('personality') or {}
            for ref in change['evidence_ids']:
                owner,eid=aliases.get(ref,(cid,ref))
                entry=profile.get('evidence',{}).get(eid)
                if not entry and owner==cid and resolver.development_query:
                    archive=resolver.development_query(actor_ids=[cid],kind='development_evidence',evidence_ids=[eid],limit=1)
                    if archive: entry=resolver.typed(DevelopmentEvidence,archive[0]['after'],'value_deltas',index)
                if owner!=cid or not entry: break
                sources.append(entry)
            else:
                sources=list({r['source_event_id']:r for r in sources}.values())
                if len({r['source_turn'] for r in sources if not external or r['player_owned']})>=3:
                    pass
                else: sources=[]
            if len(sources)!=len(set(change['evidence_ids'])) or len({s['source_turn'] for s in sources if not external or s['player_owned']})<3:
                reject('Недостаточно независимого опыта/добровольных выборов.','value_evidence_insufficient');continue
        ids=sorted(r['id'] for r in sources)
        if old and old['source_ids']==ids:
            reject('Повторное использование того же основания.','value_replay');continue
        if not old and len(actor.get('values') or {})>=48:
            reject('Лимит 48 ценностей.');continue
        witnesses=set.intersection(*(set(e['witnesses']) for e in sources))
        facts=set.intersection(*(set(e['fact_ids']) for e in sources))
        entry=DurableValue(id=change['item_id'],text=old['text'] if change['operation']=='retire' else change['text'],
            status='retired' if change['operation']=='retire' else 'active', revision=(old or {}).get('revision',0)+1,
            source_ids=ids,witnesses=sorted(witnesses),fact_ids=sorted(facts)).model_dump()
        if actor.get('values') is None: actor['values']={}
        actor['values'][entry['id']]=entry;touched.add((cid,entry['id']))
        record_change(resolver,cid,'values',old,entry,'value_delta')
        resolver.history.state_changes[-1].update(source_ids=ids,sources=deepcopy(sources),
            evidence=change['evidence'],rationale=change['rationale'])


def context_values(actor, evaluation=False):
    result={};budget=1200
    for key,row in (actor.get('values') or {}).items():
        if row['status']!='active': continue
        record={k:row[k] for k in (('text','revision') if evaluation else ('text',))}
        if len(str(record))>budget: continue
        result[key]=record;budget-=len(str(record))
        if len(result)==8: break
    return result
