"""Deterministic claims -> patch, with field/record-local optional salvage."""
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
import math
import unicodedata
from pydantic import ValidationError
from backend.runtime_v3.models import (Character, Location, Fact, Knowledge, Relationship,
    Thread, ScheduledEvent, StatePatch, WorldHistoryV3, identity, fatal, assert_world_state_v3_invariants)
from backend.runtime_v3.raw import RawTurnResult
from backend.runtime_v3.history import INFORMATION_MEDIA
from backend.services.relation_dimensions import RELATION_DIMENSIONS
from backend.services.player_agency import PLAYER_FIELDS, supported_player_field


def normalized(text):
    value=unicodedata.normalize('NFC',text).translate(str.maketrans({c:chr(34) for c in '«»“”„'}))
    return ' '.join(value.split())


@dataclass
class ResolvedTurn:
    state: dict
    patch: StatePatch
    history: dict
    warnings: list
    choices: list
    cards: list


class StateResolver:
    def __init__(self, before, narrative, player_input, *, turn_id=None, observed=True):
        self.before = assert_world_state_v3_invariants(before)
        self.state = deepcopy(self.before)
        self.sources = [normalized(narrative), normalized(player_input)]
        self.player_input, self.narrative, self.observed = player_input, narrative, observed
        self.turn_id = turn_id if turn_id is not None else before['meta']['turn_id'] + 1
        self.warnings, self.cards = [], []
        self.history = WorldHistoryV3()

    def warn(self, section, index, reason, field=None, entity=None, code='optional_record_invalid'):
        section={'character_changes':'characters','relationship_changes':'relationships','knowledge_gained':'knowledge','thread_changes':'threads','scheduled_event_changes':'scheduled_events'}.get(section,section)
        value = dict(type='sanitized_delta',section=section,index=index,reason=reason,code=code,
            action='drop_field' if field else 'drop_record')
        if field: value['field'] = field
        if entity: value['entity'] = entity
        self.warnings.append(value)

    def supported(self, record):
        quote = record.get('evidence')
        return isinstance(quote,str) and bool(normalized(quote)) and any(normalized(quote) in source for source in self.sources)

    def records(self, raw, section, *, evidence=True):
        seen=set()
        for i, item in enumerate(raw.records[section]):
            if not isinstance(item, dict):
                self.warn(section,i,'ожидался объект')
            elif evidence and not self.supported(item):
                self.warn(section,i,'нет подтверждённого источника', code='evidence_unsupported')
            else:
                key=item.get('id')
                if section=='relationship_changes':
                    key=(item.get('source_id'),item.get('target_id')) if all(isinstance(item.get(k),str) for k in ('source_id','target_id')) else None
                if section not in ('movements','knowledge_gained') and (isinstance(key,str) or isinstance(key,tuple)):
                    if key in seen:fatal('повторный canonical ID записи','canonical_id_conflict',repairable=True,section=section,index=i)
                    seen.add(key)
                yield i, item

    def actor(self, value, section, index):
        if not isinstance(value,str) or value not in self.state['characters']:
            fatal('неизвестный обязательный character_id', 'unknown_character', repairable=True, section=section,index=index)
        return value

    def typed(self, model, values, section, index):
        try:
            return model.model_validate(values).model_dump()
        except ValidationError:
            self.warn(section,index,'некорректная необязательная запись', code='optional_schema_invalid')
            return None

    def resolve(self, payload):
        raw = payload if isinstance(payload, RawTurnResult) else RawTurnResult.parse(payload)
        self.warnings.extend(raw.warnings)
        s = self.state
        for i, item in self.records(raw,'locations'):
            fields = {key:item[key] for key in ('id','name','description') if key in item}
            entry = self.typed(Location,fields,'locations',i)
            if entry:
                if entry['id'] in s['locations'] and entry != s['locations'][entry['id']]:
                    fatal('конфликт canonical location ID', 'canonical_id_conflict', repairable=True)
                s['locations'][entry['id']] = entry
        for i, item in self.records(raw,'promotions'):
            cid = item.get('id')
            fields = item.get('fields')
            from backend.services.world import CARD_FIELDS
            if not isinstance(cid,str) or not cid or not isinstance(item.get('name'),str) or not isinstance(fields,dict) or any(not isinstance(fields.get(k),str) or not fields[k].strip() for k in CARD_FIELDS):
                self.warn('promotions',i,'значимая роль требует полную карточку'); continue
            if cid in s['characters']:
                fatal('конфликт canonical character ID', 'canonical_id_conflict', repairable=True)
            s['characters'][cid] = Character(id=cid).model_dump()
            self.cards.append(dict(id=cid,name=item['name'],fields=deepcopy(fields),aliases=[],is_player=False))
        scene = raw.final_scene
        lid, present = scene.get('location_id'), scene.get('present_character_ids')
        if lid is not None and (not isinstance(lid,str) or lid not in s['locations']):
            fatal('неизвестное конечное место камеры', 'camera_location_invalid', repairable=True)
        if not isinstance(present,list) or any(not isinstance(cid,str) for cid in present):
            fatal('повреждены участники final_scene', 'camera_invalid', repairable=True)
        present = list(dict.fromkeys(present))
        for cid in present: self.actor(cid,'final_scene',0)
        camera = deepcopy(s['camera'])
        if camera['mode']=='actor' and camera['controlled_actor_id'] not in present:
            fatal('controlled actor отсутствует в final_scene', 'camera_actor_missing', repairable=True)
        elapsed = scene.get('elapsed_minutes',0)
        if type(elapsed) is not int or not 0 <= elapsed <= 10080:
            fatal('некорректная длительность хода', 'invalid_time', repairable=True)
        situation = scene.get('situation',camera['situation'])
        if not isinstance(situation,str):
            fatal('некорректное описание камеры', 'camera_invalid', repairable=True)
        camera.update(location_id=lid,present_character_ids=present,situation=situation)
        s['camera'] = camera
        s['meta'].update(turn_id=self.turn_id,world_time=s['meta']['world_time']+elapsed)
        moves = {}
        for i, item in self.records(raw,'movements'):
            cid = self.actor(item.get('actor_id'),'movements',i)
            if cid in present: continue  # Final camera owns these endpoints.
            target = item.get('to_location_id')
            if not isinstance(target,str) or target not in s['locations']:
                fatal('неизвестное конечное место off-camera перемещения','movement_endpoint_invalid',repairable=True,index=i)
            order = item.get('order')
            if order is not None and (type(order) is not int or order < 0):
                self.warn('movements',i,'некорректный необязательный order',field='order'); order = None
            moves.setdefault(cid,[]).append((order,target,item['evidence']))
        for cid, route in moves.items():
            if len({r[1] for r in route}) > 1:
                if any(r[0] is None for r in route) or len({r[0] for r in route}) != len(route):
                    fatal('неоднозначное off-camera перемещение','movement_ambiguous',repairable=True,entity=cid)
                route.sort(key=lambda r:r[0])
            origin = s['characters'][cid]['location_id']
            for order,target,evidence in route:
                self.history.movements.append(dict(actor_id=cid,from_location_id=origin,to_location_id=target,
                    evidence=evidence,order=order,turn_id=self.turn_id))
                origin = target
            s['characters'][cid]['location_id'] = origin
        for cid in present:
            origin = s['characters'][cid]['location_id']
            if origin != lid:
                self.history.movements.append(dict(actor_id=cid,from_location_id=origin,to_location_id=lid,
                    derived_from='final_scene',turn_id=self.turn_id))
            s['characters'][cid]['location_id'] = lid
        for i, item in self.records(raw,'facts'):
            fields = {key:item[key] for key in ('id','text','visibility','character_ids') if key in item}
            entry = self.typed(Fact,fields,'facts',i)
            if entry:
                for cid in entry['character_ids']: self.actor(cid,'facts',i)
                if entry['id'] in s['facts'] and entry != s['facts'][entry['id']]:
                    fatal('конфликт canonical fact ID','canonical_id_conflict',repairable=True,entity=entry['id'])
                s['facts'][entry['id']] = entry
        events = {}
        for i, item in self.records(raw,'events'):
            eid = item.get('id')
            if not isinstance(eid,str) or not eid or not isinstance(item.get('text'),str):
                self.warn('events',i,'отсутствует ID или текст'); continue
            lists = {key:item.get(key,[]) for key in ('participants','witnesses','fact_ids')}
            if any(not isinstance(v,list) or any(not isinstance(x,str) for x in v) for v in lists.values()):
                self.warn('events',i,'повреждены ссылки Event'); continue
            if set(lists['participants']+lists['witnesses']) - s['characters'].keys():
                self.warn('events',i,'неизвестная ссылка необязательного Event'); continue
            if set(lists['fact_ids']) - s['facts'].keys():
                self.warn('events',i,'ссылки на отсутствующие факты отброшены','fact_ids',eid,'event_fact_reference_dropped')
                lists['fact_ids']=[fid for fid in lists['fact_ids'] if fid in s['facts']]
            if eid in events:
                fatal('неоднозначный ID Event этого хода','canonical_id_conflict',repairable=True)
            medium=item.get('medium','action')
            if not isinstance(medium,str) or medium not in INFORMATION_MEDIA | {'action'}:
                self.warn('events',i,'неизвестный канал Event');continue
            event = dict(id=identity('event',self.turn_id,eid,self.narrative),local_id=eid,text=item['text'],
                **lists,medium=medium,evidence=item['evidence'],turn_id=self.turn_id,
                player_observed=self.observed,recorded_minute=s['meta']['world_time'])
            for key in ('minute','order'):
                if type(item.get(key)) is int and item[key] >= 0: event[key]=item[key]
            if isinstance(item.get('location_id'),str) and item['location_id'] in s['locations']: event['location_id']=item['location_id']
            events[eid] = event
            self.history.events.append(event)
        for i, item in self.records(raw,'knowledge_gained'):
            source=item.get('source_event_id')
            event=events.get(source) if isinstance(source,str) else None
            actor, fact = item.get('actor_id'), item.get('fact_id')
            if not isinstance(actor,str) or not isinstance(fact,str):
                self.warn('knowledge_gained',i,'неправильный тип ссылки',code='knowledge_path_invalid');continue
            if (actor not in s['characters'] or fact not in s['facts'] or not event or
                actor not in event['witnesses'] or fact not in event['fact_ids'] or event['medium'] not in INFORMATION_MEDIA):
                self.warn('knowledge_gained',i,'нет подтверждённого пути передачи знания',code='knowledge_path_invalid'); continue
            entry = self.typed(Knowledge,dict(actor_id=actor,fact_id=fact,status=item.get('status','known')),'knowledge_gained',i)
            if entry:
                s['knowledge'][actor+':'+fact] = entry
                self.history.knowledge_acquisitions.append(dict(entry,source_event_id=event['id'],evidence=item['evidence'],turn_id=self.turn_id))
        for i, item in self.records(raw,'character_changes',evidence=False):
            cid = self.actor(item.get('id'),'character_changes',i)
            actor = s['characters'][cid]
            for key in ('situation','emotion','goals','intentions','obligations'):
                if key not in item: continue
                value = item[key]
                valid_type = isinstance(value,str) if key in ('situation','emotion') else isinstance(value,list) and all(isinstance(v,str) for v in value)
                if not valid_type:
                    self.warn('character_changes',i,'неправильный тип поля',key,cid); continue
                if cid == camera['controlled_actor_id'] and key in PLAYER_FIELDS:
                    evidence = item.get('player_evidence')
                    proof=evidence.get(key) if isinstance(evidence,dict) else None
                    if proof is None and isinstance(item.get('evidence'),str):
                        proof=item['evidence'] if key=='emotion' else [item['evidence']]
                    if not supported_player_field(key,value,actor[key],self.player_input,proof):
                        self.warn('character_changes',i,'состояние controlled actor не задано игроком',key,cid,'controlled_actor_unsupported'); continue
                elif not self.supported(item):
                    self.warn('character_changes',i,'нет подтверждённого источника',key,cid,'evidence_unsupported'); continue
                actor[key] = deepcopy(value)
        for i, item in self.records(raw,'relationship_changes'):
            source = self.actor(item.get('source_id'),'relationship_changes',i)
            target = self.actor(item.get('target_id'),'relationship_changes',i)
            key = source+':'+target
            entry = deepcopy(s['relationships'].get(key,Relationship(source_id=source,target_id=target).model_dump()))
            if 'context' in item:
                if isinstance(item['context'],str): entry['context']=item['context']
                else: self.warn('relationship_changes',i,'неправильный тип context','context',key)
            dimensions = item.get('dimensions',{})
            if not isinstance(dimensions,dict):
                self.warn('relationship_changes',i,'неправильный тип dimensions','dimensions',key); dimensions={}
            for dim,value in dimensions.items():
                if dim not in RELATION_DIMENSIONS or type(value) not in (int,float) or not math.isfinite(value) or not -100<=value<=100:
                    self.warn('relationship_changes',i,'неизвестное или некорректное измерение отношений','dimensions.'+dim,key,'relationship_dimension_invalid')
                else: entry['dimensions'][dim]=value
            s['relationships'][key]=entry
            self.history.relationship_changes.append(dict(entity=key,before=deepcopy(self.before['relationships'].get(key)),after=deepcopy(entry),turn_id=self.turn_id))
        for section, destination, model in (('thread_changes','threads',Thread),('scheduled_event_changes','scheduled_events',ScheduledEvent)):
            for i,item in self.records(raw,section):
                eid=item.get('id')
                if not isinstance(eid,str) or not eid:
                    self.warn(section,i,'отсутствует ID'); continue
                fields=deepcopy(s[destination].get(eid,{}))
                fields.update({key:item[key] for key in model.model_fields if key in item})
                entry=self.typed(model,fields,section,i)
                if entry:
                    for cid in entry['character_ids']: self.actor(cid,section,i)
                    s[destination][eid]=entry
        upserts = {section:{key:deepcopy(value) for key,value in s[section].items() if value != self.before[section].get(key)}
            for section in ('characters','locations','facts','knowledge','relationships','threads','scheduled_events')}
        digest = sha256(json.dumps(self.before,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        patch = StatePatch(digest,deepcopy(s['meta']),deepcopy(s['camera']),upserts)
        state = patch.apply(self.before)
        self.history.state_changes.append(dict(turn_id=self.turn_id,upserts=deepcopy(upserts)))
        record_id=identity('record',self.turn_id,self.narrative,self.observed)
        for event in self.history.events:
            event.update(source_record_id=record_id,source_sequence=self.turn_id-1)
        self.history.turns.append(dict(id=record_id,turn_id=self.turn_id,sequence=self.turn_id-1,
            narrative=self.narrative,player_input=self.player_input,
            camera_before=deepcopy(self.before['camera']),camera=deepcopy(state['camera']),
            game_time_before=self.before['meta']['world_time'],world_time=state['meta']['world_time'],
            player_observed=self.observed))
        return ResolvedTurn(state,patch,self.history.to_dict(),self.warnings,raw.choices,self.cards)
