"""Canonical visual traits. Functional consequences remain owned by #38.

Semantic assertions come from Extraction; source, agency, CAS, references and
idempotency are checked here. This is not a natural-language meaning verifier.
"""
from copy import deepcopy
from typing import Literal
from pydantic import Field
from backend.runtime_v3.models import StrictModel, AppearanceProfile, AppearanceFeature, identity

KINDS = {'intrinsic': {'eye_color','natural_hair_color','skin','face'},
         'body': {'build','height'}, 'modification': {'scar','tattoo','piercing','cosmetic'},
         'presentation': {'hairstyle','facial_hair'}, 'condition': {'condition'}}


class AppearanceDelta(StrictModel):
    actor_id: str
    item_id: str = Field(min_length=1, max_length=100)
    operation: Literal['establish','update','remove']
    category: Literal['intrinsic','body','modification','presentation','condition']
    kind: Literal['eye_color','natural_hair_color','skin','face','build','height','scar','tattoo','piercing','hairstyle','facial_hair','cosmetic','condition']
    text: str = Field(default='', max_length=600)
    expected_revision: int = Field(ge=0)
    source_event_id: str
    fact_id: str
    condition_id: str | None = None
    assertion: Literal['established_visual_outcome']
    transition: Literal['voluntary','involuntary','established_trait']
    evidence: str = Field(min_length=1, max_length=1000)
    player_evidence: str = ''
    player_assertion: Literal['explicit_choice'] | None = None


def initialize_profiles(snapshot):
    for card in snapshot.get('character_cards', []):
        actor = snapshot['world_state']['characters'].get(card['id'])
        if actor is not None and not (actor.get('appearance') or {}).get('legacy_text') and not (actor.get('appearance') or {}).get('items') and not (actor.get('appearance') or {}).get('applied'):
            actor['appearance'] = AppearanceProfile(legacy_text=card.get('fields', {}).get('Внешность','')).model_dump()
    return snapshot


def salvage_profiles(state):
    """Optional corrupt entries degrade locally; persisted history is untouched."""
    import logging
    from backend.runtime_v3.models import PortraitReference
    log=logging.getLogger(__name__)
    for actor in state.get('characters', {}).values():
        if not isinstance(actor,dict): continue
        if 'appearance' in actor:
            raw=actor['appearance']
            if not isinstance(raw,dict): raw={}
            items={}
            for key,value in list((raw.get('items') if isinstance(raw.get('items'),dict) else {}).items())[:48]:
                try: items[key]=AppearanceFeature.model_validate(value).model_dump()
                except (ValueError,TypeError): log.warning('Ignoring malformed appearance item for %s',actor.get('id'))
            legacy=raw.get('legacy_text','')
            applied=raw.get('applied',[])
            actor['appearance']=AppearanceProfile(items=items,legacy_text=legacy if isinstance(legacy,str) else '',
                applied=[a for a in applied if isinstance(a,str)] if isinstance(applied,list) else []).model_dump()
        if 'portraits' in actor:
            rows=actor['portraits'];valid=[];seen=set()
            for row in rows[:128] if isinstance(rows,list) else []:
                try:
                    p=PortraitReference.model_validate(row).model_dump()
                    if p['id'] in seen: raise ValueError('duplicate portrait')
                    seen.add(p['id']);valid.append(p)
                except (ValueError,TypeError): log.warning('Ignoring malformed portrait reference for %s',actor.get('id'))
            actor['portraits']=valid


def visible(state, cid, item, observer):
    if observer == cid: return True
    fid = item.get('fact_id')
    return not item.get('source_event_id') or bool(fid and state['knowledge'].get(str(observer)+':'+fid,{}).get('status')=='known')


def current_items(state, cid, *, observer=None, omniscient=False):
    items = (state['characters'][cid].get('appearance') or {}).get('items',{})
    result = {}
    for key,item in items.items():
        if not omniscient and not visible(state,cid,item,observer): continue
        if item.get('condition_id'):
            condition=state['conditions'].get(item['condition_id'])
            if not condition or condition['actor_id']!=cid or condition['status']!='active': continue
            # Read-time projection invalidates immediately on #38 resolution.
            item=dict(item,text=condition['description'])
        result[key]=item
    return result


def context_profile(state, cid, *, observer=None, omniscient=False, known_actor_ids=None):
    profile=state['characters'][cid].get('appearance')
    if profile is None: return None
    budget=1600; items={}
    for key,item in current_items(state,cid,observer=observer,omniscient=omniscient).items():
        row={k:item[k] for k in ('category','kind','text','revision','condition_id')}
        row['known_by']=(sorted(a for a in (known_actor_ids if known_actor_ids is not None else {cid,observer}) if a in state['characters'] and visible(state,cid,item,a)) if item.get('source_event_id') else 'initial_baseline')
        if len(str(row))>budget: continue
        items[key]=row;budget-=len(str(row))
    legacy=profile.get('legacy_text','')[:min(600,budget)]
    return dict(items=items,legacy_text=legacy) if items or legacy else None


def project_card(card, state, observer=None, *, omniscient=False, bounded=False, known_actor_ids=None):
    cid=card['id']; result=deepcopy(card)
    profile=context_profile(state,cid,observer=observer,omniscient=omniscient,known_actor_ids=known_actor_ids) if bounded else None
    if not bounded:
        canonical=state['characters'][cid].get('appearance') or {}
        profile=dict(items=current_items(state,cid,observer=observer,omniscient=omniscient),legacy_text=canonical.get('legacy_text',''))
    if profile is not None:
        # Explicit structured current state takes precedence; legacy stays separately
        # labelled for manual inspection rather than masquerading as current clothing.
        result['fields']['Внешность']='\n'.join(v['text'] for v in profile['items'].values())
        if profile['legacy_text']: result['fields']['Исходное описание внешности']=profile['legacy_text']
    return result


def apply_appearance(r, raw, events):
    from backend.runtime_v3.resolver import normalized
    from backend.runtime_v3.personality import _record
    for i,row in r.records(raw,'appearance_deltas'):
        c=r.typed(AppearanceDelta,row,'appearance_deltas',i)
        if c is None: continue
        try:
            cid=c['actor_id'];actor=r.state['characters'].get(cid);event=events.get(c['source_event_id'])
            if not actor or not event or cid not in event['participants']: raise ValueError('Нет принятого события персонажа.')
            if c['fact_id'] not in event['fact_ids']: raise ValueError('Нет факта внешности в событии.')
            fact=r.state['facts'][c['fact_id']]
            if cid not in fact['character_ids']: raise ValueError('Факт относится к другому персонажу.')
            if normalized(c['evidence']) not in normalized(r.narrative): raise ValueError('Нужен совершившийся результат в повествовании.')
            if c['kind'] not in KINDS[c['category']]: raise ValueError('Несогласованная категория внешности.')
            if c['kind'] in ('tattoo','piercing','hairstyle','facial_hair','cosmetic') and c['transition']!='voluntary':
                raise ValueError('Косметическое изменение требует добровольного действия.')
            if c['transition']=='voluntary' and cid==r.protected_actor_id:
                quote=normalized(c['player_evidence'])
                if r.mode=='background' or c['player_assertion']!='explicit_choice' or not quote or quote not in normalized(r.player_input):
                    raise ValueError('Нет явного выбора EXTERNAL actor.')
            profile=actor.get('appearance') or AppearanceProfile().model_dump()
            guard=identity('appearance',cid,event['id'],c['item_id'])
            source_guard=identity('appearance_source',cid,event['id'],c['fact_id'],c['kind'])
            if guard in profile['applied'] or source_guard in profile['applied']: continue
            old=profile['items'].get(c['item_id'])
            if (old or {}).get('revision',0)!=c['expected_revision']: raise ValueError('Устаревшая версия внешности.')
            if c['operation']=='establish' and old or c['operation']!='establish' and not old: raise ValueError('Некорректная операция внешности.')
            if c['kind'] in ('eye_color','natural_hair_color','build','height','hairstyle','facial_hair') and any(k!=c['item_id'] and v['kind']==c['kind'] for k,v in profile['items'].items()):
                raise ValueError('Признак уже имеет canonical ID.')
            if old and (old['kind']!=c['kind'] or old['category']!=c['category']): raise ValueError('Нельзя менять тип признака.')
            if c['category']=='intrinsic' and old and c['transition']=='established_trait': raise ValueError('Устойчивая черта уже установлена.')
            if c['category']=='condition':
                cond=r.state['conditions'].get(c['condition_id'])
                if not cond or cond['actor_id']!=cid or cond['status']!='active' or cond['fact_id']!=c['fact_id']:
                    raise ValueError('Функциональное последствие принадлежит #38; нужна действующая ссылка.')
            elif c['condition_id'] is not None: raise ValueError('Ссылка #38 допустима только для проекции состояния.')
            if c['operation']=='remove':
                if c['text']: raise ValueError('Удаление не задаёт новый признак.')
                after=None
            else:
                if c['category']!='condition' and not c['text'].strip(): raise ValueError('Пустое описание.')
                after=AppearanceFeature(category=c['category'],kind=c['kind'],text='' if c['category']=='condition' else c['text'],
                    revision=c['expected_revision']+1,condition_id=c['condition_id'],source_event_id=event['id'],
                    fact_id=c['fact_id'],evidence=c['evidence']).model_dump()
            if len(profile['items'])>=48 and not old: raise ValueError('Превышен лимит профиля.')
            actor['appearance']=profile
            if after is None: del profile['items'][c['item_id']]
            else: profile['items'][c['item_id']]=after
            profile['applied'].extend([guard,source_guard])
            _record(r,'appearance_delta',cid,old,after,source_ids=[event['id']],operation_ids=[guard,source_guard],
                item_id=c['item_id'],evidence=c['evidence'],fact_id=c['fact_id'],source_event_id=event['id'])
        except ValueError as exc:
            r.warn('appearance_deltas',i,str(exc),code='appearance_rejected')
