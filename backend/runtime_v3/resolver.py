"""Deterministic claims -> patch, with field/record-local optional salvage."""
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
import math
import unicodedata
from typing import Literal
from pydantic import ValidationError
from backend.runtime_v3.models import (Character, Location, Fact, Relationship,
    Thread, ScheduledEvent, StatePatch, WorldHistoryV3, identity, fatal, assert_world_state_v3_invariants)
from backend.runtime_v3.lifecycle import active_texts, replace_active, apply_changes
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
    def __init__(self, before, narrative, player_input, *, turn_id=None, observed=True, actor_names=None, protected_actor_id=None, mode: Literal["turn", "background"] = "turn", protected_knowledge_actor_ids=None, milestone_query=None, development_query=None, death_policy=None, pacing_decision=None, initiative_decision=None, continuity_decision=None, minimal_promotion_ids=None, event_namespace=None):
        if mode not in ("turn", "background"):
            raise ValueError("Неизвестный режим StateResolver.")
        self.minimal_promotion_ids = set(minimal_promotion_ids or ())
        self.event_namespace = event_namespace
        self.protected_actor_id = protected_actor_id or before['camera']['controlled_actor_id']
        from backend.runtime_v3.pacing import NarrativeDeathPolicy
        self.death_policy = death_policy or NarrativeDeathPolicy()
        self.pacing_decision = pacing_decision
        self.initiative_decision = initiative_decision
        self.continuity_decision = continuity_decision
        self.mode = mode
        self.protected_knowledge_actor_ids = set(protected_knowledge_actor_ids or [self.protected_actor_id])
        self.milestone_query = milestone_query
        self.development_query = development_query
        self.actor_names=actor_names or {}
        self.before = assert_world_state_v3_invariants(before)
        self.state = deepcopy(self.before)
        from backend.runtime_v3.migration import initialize_calendar
        initialize_calendar(self.state)
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
            elif evidence and not self.supported(item) and not (section=='scheduled_event_changes' and self.remote_commitment_supported(item)):
                self.warn(section,i,'нет подтверждённого источника', code='evidence_unsupported')
            else:
                key=item.get('id')
                if section=='relationship_changes':
                    key=(item.get('source_id'),item.get('target_id')) if all(isinstance(item.get(k),str) for k in ('source_id','target_id')) else None
                if section not in ('movements','knowledge_gained') and (isinstance(key,str) or isinstance(key,tuple)):
                    if key in seen:fatal('повторный canonical ID записи','canonical_id_conflict',repairable=True,section=section,index=i)
                    seen.add(key)
                yield i, item

    def remote_commitment_supported(self, record):
        from backend.runtime_v3.remote import commitment_sources
        quote=record.get('evidence')
        return isinstance(quote,str) and bool(normalized(quote)) and any(
            normalized(quote) in normalized(e['content']) for e in commitment_sources(self.before,record))

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
        raw = deepcopy(payload) if isinstance(payload, RawTurnResult) else RawTurnResult.parse(payload)
        self.warnings.extend(raw.warnings)
        s = self.state
        from backend.runtime_v3.pacing import validate_risk
        validate_risk(self, raw)
        from backend.runtime_v3.residence import apply_locations
        apply_locations(self, raw)
        for i, item in self.records(raw,'promotions'):
            cid = item.get('id')
            if any(cid==ch['id'] for p in s['pregnancies'].values() for ch in p['children']):
                self.warn('promotions',i,'Reserved birth identity is created only by Runtime.',code='birth_identity_reserved'); continue
            fields = item.get('fields')
            from backend.services.world import CARD_FIELDS
            if not isinstance(cid,str) or not cid or not isinstance(item.get('name'),str) or not isinstance(fields,dict) or (cid not in self.minimal_promotion_ids and any(not isinstance(fields.get(k),str) or not fields[k].strip() for k in CARD_FIELDS)):
                self.warn('promotions',i,'значимая роль требует полную карточку'); continue
            if cid in s['characters']:
                fatal('конфликт canonical character ID', 'canonical_id_conflict', repairable=True)
            s['characters'][cid] = Character(id=cid).model_dump()
            self.cards.append(dict(id=cid,name=item['name'],fields=deepcopy(fields),aliases=[],is_player=False))
            from backend.runtime_v3.personality import initialize_profiles
            initialize_profiles(dict(world_state=s, character_cards=[self.cards[-1]]))
        scene = raw.final_scene
        lid, present = scene.get('location_id'), scene.get('present_character_ids')
        if lid is not None and (not isinstance(lid,str) or lid not in s['locations']):
            fatal('неизвестное конечное место камеры', 'camera_location_invalid', repairable=True)
        if not isinstance(present,list) or any(not isinstance(cid,str) for cid in present):
            fatal('повреждены участники final_scene', 'camera_invalid', repairable=True)
        reserved = {ch['id'] for p in s['pregnancies'].values() if p['status']!='born' for ch in p['children']}
        if reserved & set(present): self.warn('final_scene',0,'Runtime adds children only after accepted birth.',code='birth_presence_deferred')
        present = list(dict.fromkeys(cid for cid in present if cid not in reserved))
        from backend.runtime_v3.life import capabilities
        dead_present = [cid for cid in present if s['characters'].get(cid, {}).get('life_status') == 'dead']
        for cid in dead_present:
            self.warn('final_scene',0,'Мёртвый персонаж не участвует в текущей сцене.',entity=cid)
        present = [cid for cid in present if cid not in dead_present]
        for cid in present: self.actor(cid,'final_scene',0)
        camera = deepcopy(s['camera'])
        if camera['mode']=='actor' and camera['controlled_actor_id'] not in present and s['characters'].get(camera['controlled_actor_id'], {}).get('life_status') != 'dead':
            fatal('controlled actor отсутствует в final_scene', 'camera_actor_missing', repairable=True)
        elapsed = scene.get('elapsed_minutes',0)
        if type(elapsed) is not int or not 0 <= elapsed <= 10080:
            fatal('некорректная длительность хода', 'invalid_time', repairable=True)
        if self.mode == 'background' and elapsed:
            # The enclosing turn/Time Skip already owns the clock. Ignore the
            # proposal before deriving event/history timestamps or StatePatch.
            self.warn('final_scene', 0, 'Длительность фоновой симуляции проигнорирована: время задано Runtime.',
                      'elapsed_minutes', code='background_elapsed_ignored')
            self.warnings[-1].update(proposed_minutes=elapsed, applied_minutes=0)
            elapsed = 0
        from backend.runtime_v3.continuity import validate_compression
        validate_compression(self, scene, elapsed)
        situation = scene.get('situation',camera['situation'])
        if not isinstance(situation,str):
            fatal('некорректное описание камеры', 'camera_invalid', repairable=True)
        remote = []
        claims = scene.get('remote_interactions', [])
        if not isinstance(claims, list):
            claims = []
            self.warn('final_scene', 0, 'remote_interactions должен быть списком')
        for index, interaction in enumerate(claims):
            if not isinstance(interaction, dict) or not self.supported(interaction):
                self.warn('final_scene', index, 'нет evidence удалённого взаимодействия'); continue
            cid = interaction.get('actor_id')
            if not isinstance(cid, str) or cid not in s['characters'] or cid in present or any(r['actor_id'] == cid for r in remote):
                self.warn('final_scene', index, 'некорректный remote actor'); continue
            if not capabilities(s,cid)['can_act']:
                self.warn('final_scene',index,'Участник недоступен для взаимодействия.'); continue
            from backend.runtime_v3.models import RemoteInteraction
            record = self.typed(RemoteInteraction, dict(actor_id=cid, channel=interaction.get('channel'),
                                last_active_turn=self.turn_id), 'final_scene', index)
            if record: remote.append(record)
        from backend.runtime_v3.remote import active_call, participants
        call = active_call(s, camera['controlled_actor_id'])
        if any(s['meta']['communication'][channel] for channel in ('text_message','voice_call')):
            remote = [dict(actor_id=cid, channel='phone', last_active_turn=self.turn_id)
                      for cid in sorted(participants(call) - set(present))] if call and call['status']=='answered' else []
        camera['remote_interactions'] = remote
        camera.update(location_id=lid,present_character_ids=present,situation=situation)
        s['camera'] = camera
        s['meta'].update(turn_id=self.turn_id,world_time=s['meta']['world_time']+elapsed)
        moves = {}
        for i, item in self.records(raw,'movements'):
            cid = self.actor(item.get('actor_id'),'movements',i)
            if not capabilities(s,cid)['can_move']:
                self.warn('movements',i,'Персонаж не может самостоятельно перемещаться.',entity=cid); continue
            target = item.get('to_location_id')
            if not isinstance(target,str) or target not in s['locations']:
                fatal('неизвестное конечное место перемещения','movement_endpoint_invalid',repairable=True,index=i)
            order = item.get('order')
            if order is not None and (type(order) is not int or order < 0):
                self.warn('movements',i,'некорректный необязательный order',field='order'); order = None
            moves.setdefault(cid,[]).append((order,target,item['evidence']))
        for cid, route in moves.items():
            if len({r[1] for r in route}) > 1:
                if any(r[0] is None for r in route) or len({r[0] for r in route}) != len(route):
                    fatal('неоднозначное перемещение','movement_ambiguous',repairable=True,entity=cid)
                route.sort(key=lambda r:r[0])
            if cid in present:
                if route[-1][1] != lid:
                    fatal('конечное перемещение участника противоречит final_scene',
                          'scene_movement_conflict', repairable=True, entity=cid,
                          scene_location_id=lid, movement_location_id=route[-1][1])
                continue  # Consistent redundant route; final_scene owns the endpoint.
            origin = s['characters'][cid]['location_id']
            for order,target,evidence in route:
                self.history.movements.append(dict(actor_id=cid,from_location_id=origin,to_location_id=target,
                    evidence=evidence,order=order,turn_id=self.turn_id))
                origin = target
            s['characters'][cid]['location_id'] = origin
        for cid in present:
            origin = s['characters'][cid]['location_id']
            # #64 final_scene still owns the endpoint. For an off-camera actor
            # in a structured geography require evidence of joining this scene;
            # residence/affiliation alone cannot supply that movement evidence.
            geography = any(s['locations'].get(p,{}).get('parent_id') for p in (origin,lid))
            if (cid not in self.before['camera']['present_character_ids'] and origin != lid and geography
                    and cid not in moves and not self.supported({'evidence':scene.get('situation_evidence')})):
                fatal('появление персонажа требует основания перемещения', 'scene_arrival_unsupported', repairable=True, entity=cid)

            if origin != lid:
                self.history.movements.append(dict(actor_id=cid,from_location_id=origin,to_location_id=lid,
                    derived_from='final_scene',turn_id=self.turn_id))
            s['characters'][cid]['location_id'] = lid
        controlled=camera['controlled_actor_id']
        if controlled is not None and self.supported({'evidence':scene.get('situation_evidence')}):
            s['characters'][controlled]['situation']=situation
        for i, item in self.records(raw,'facts'):
            fields = {key:item[key] for key in ('id','text','visibility','character_ids','claim') if key in item}
            if 'claim' in fields and fields['claim'] is not None:
                from backend.runtime_v3.models import Claim
                try: fields['claim'] = Claim.model_validate(fields['claim']).model_dump()
                except ValidationError:
                    fields.pop('claim')
                    self.warn('facts', i, 'Некорректная идентичность утверждения.', field='claim', code='optional_schema_invalid')
            if 'claim' not in fields and isinstance(fields.get('id'), str) and fields['id'] in s['facts']:
                fields['claim'] = s['facts'][fields['id']].get('claim')
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
            from backend.runtime_v3.remote import validate_event_channel
            if not validate_event_channel(self.before,item):
                self.warn('events',i,'Свидетели или участники недоступны в этом канале.',code='remote_channel_boundary');continue
            event_id = identity('event',self.turn_id,eid,self.narrative,self.event_namespace) if self.event_namespace else identity('event',self.turn_id,eid,self.narrative)
            event = dict(id=event_id,local_id=eid,text=item['text'],
                **lists,medium=medium,evidence=item['evidence'],turn_id=self.turn_id,
                player_observed=self.observed,recorded_minute=s['meta']['world_time'])
            if item.get('interaction_channel')=='call':
                event['interaction_channel']='call'
            for key in ('minute','order'):
                if type(item.get(key)) is int and item[key] >= 0: event[key]=item[key]
            if isinstance(item.get('location_id'),str) and item['location_id'] in s['locations']: event['location_id']=item['location_id']
            if item.get('author_id') is not None:
                author = item['author_id']
                if isinstance(author, str) and author in lists['participants'] and medium == 'message':
                    event['author_id'] = author
                else: self.warn('events', i, 'неподтверждённый автор сообщения', 'author_id')
            from backend.runtime_v3.calendar import current_time
            if 'minute' in event: event['calendar_date'] = current_time(s,event['minute'])['date']
            events[eid] = event
            self.history.events.append(event)
        from backend.runtime_v3.initiative import validate_actions
        validate_actions(self, raw, events)
        from backend.runtime_v3.knowledge import apply_knowledge
        apply_knowledge(self, raw, events)
        from backend.runtime_v3.life import apply_life
        apply_life(self,raw)
        from backend.runtime_v3.residence import apply_residence
        apply_residence(self,raw)
        for i, item in self.records(raw,'character_changes',evidence=False):
            cid = self.actor(item.get('id'),'character_changes',i)
            actor = s['characters'][cid]
            for protected in ('personality','values','fields','appearance','portraits'):
                if protected in item:
                    self.warn('character_changes',i,'Личность изменяется только частичной evidence-bound дельтой.',protected,cid,'personality_full_replace_rejected')
            if actor['life_status'] == 'dead':
                self.warn('character_changes',i,'Мёртвый персонаж не получает обычные изменения состояния.',entity=cid); continue
            if 'birth_date' in item:
                from backend.runtime_v3.calendar import date_parts, profile_of, current_time
                try:
                    birth = item['birth_date']
                    date_parts(birth, profile_of(s))
                    if not self.supported(item) or birth not in item.get('evidence',''):
                        raise ValueError('birth date must be explicitly stated in evidence')
                    today = current_time(s)['date']
                    if today and birth > today: raise ValueError('birth date is in the future')
                    if actor.get('birth_date') not in (None,birth): raise ValueError('cannot overwrite an established birthday')
                    if actor.get('birth_date') != birth:
                        prior = deepcopy(actor)
                        actor['birth_date'] = birth
                        from backend.runtime_v3.life import _transition
                        _transition(self,'birth_date_established',cid,prior,actor,item)
                except (ValueError,TypeError):
                    self.warn('character_changes',i,'дата рождения не подтверждена или некорректна','birth_date',cid)
            if actor['developmental_stage']=='infant':
                for field in ('goals','intentions','obligations'):
                    if field in item or field+'_updates' in item:
                        self.warn('character_changes',i,'Infant motivation requires later development.',entity=cid,code='infant_motivation_invalid')
                        item.pop(field,None); item.pop(field+'_updates',None)
            for key in ('situation','physical_state','emotion','goals','intentions','obligations'):
                if key not in item: continue
                value = item[key]
                valid_type = isinstance(value,str) if key in ('situation','physical_state','emotion') else isinstance(value,list) and all(isinstance(v,str) for v in value)
                if not valid_type:
                    self.warn('character_changes',i,'неправильный тип поля',key,cid); continue
                if cid == self.protected_actor_id and key in PLAYER_FIELDS:
                    if self.mode == 'background':
                        self.warn('character_changes',i,'Фон не меняет EXTERNAL мотивацию.',key,cid,'controlled_actor_unsupported'); continue
                    evidence = item.get('player_evidence')
                    proof=evidence.get(key) if isinstance(evidence,dict) else None
                    if proof is None and isinstance(item.get('evidence'),str):
                        proof=item['evidence'] if key=='emotion' else [item['evidence']]
                    if not supported_player_field(key,value,active_texts(actor[key]) if key != 'emotion' else actor[key],self.player_input,proof,emotion_assertion=item.get('emotion_assertion')):
                        self.warn('character_changes',i,'состояние controlled actor не задано игроком',key,cid,'controlled_actor_unsupported'); continue
                elif not self.supported(item):
                    self.warn('character_changes',i,'нет подтверждённого источника',key,cid,'evidence_unsupported'); continue
                if key in ('goals','intentions','obligations'):
                    # Legacy NPC lists are additions only. A validated explicit
                    # player declaration retains its replacement semantics.
                    prior = deepcopy(actor[key])
                    texts = value if cid == self.protected_actor_id else list(dict.fromkeys([r['text'] for r in actor[key] if r['status']=='active']+value))
                    actor[key] = replace_active(actor[key], texts, cid, key, self.turn_id-1)
                    from backend.runtime_v3.lifecycle import record_change
                    for row in actor[key]:
                        old=next((r for r in prior if r['id']==row['id']),None)
                        if row != old:
                            row['evidence']=item.get('evidence','')
                            record_change(self,cid,key,old,row)
                else:
                    actor[key] = deepcopy(value)
                if key == 'emotion' and cid == camera['controlled_actor_id']: actor['emotion_source_sequence'] = self.turn_id-1
            apply_changes(self, item, cid, i, events)
        for i, item in self.records(raw,'relationship_changes'):
            source = self.actor(item.get('source_id'),'relationship_changes',i)
            target = self.actor(item.get('target_id'),'relationship_changes',i)
            if s['characters'][source]['life_status'] == 'dead':
                self.warn('relationship_changes',i,'Мёртвый персонаж не меняет чувства.',entity=source); continue
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
            self.history.relationship_changes.append(dict(entity=key,before=deepcopy(self.before['relationships'].get(key)),after=deepcopy(entry),turn_id=self.turn_id,player_observed=self.observed))
        for i, item in self.records(raw, 'thread_changes'):
            if not isinstance(item.get('id'), str) or not item['id']:
                self.warn('thread_changes', i, 'отсутствует ID'); continue
            fields = deepcopy(s['threads'].get(item.get('id'), {}))
            fields.update({key:item[key] for key in Thread.model_fields if key in item and key != 'source_event_id'})
            entry = self.typed(Thread, fields, 'thread_changes', i)
            if entry:
                for cid in entry['character_ids']: self.actor(cid, 'thread_changes', i)
                s['threads'][entry['id']] = entry
        from backend.runtime_v3.reproduction import apply_reproduction
        apply_reproduction(self, raw, events)
        from backend.runtime_v3.appearance import apply_appearance
        apply_appearance(self, raw, events)
        from backend.runtime_v3.possessions import apply_possessions
        apply_possessions(self, raw, events)
        from backend.runtime_v3.commitments import apply_commitments
        owned = set(s['pregnancies'])
        claims = raw.records['scheduled_event_changes']
        for i, item in enumerate(claims):
            if isinstance(item,dict) and isinstance(item.get('id'),str) and item['id'] in owned:
                self.warn('scheduled_event_changes',i,'Pregnancy schedule is Runtime-owned.',code='reproduction_schedule_owned')
        raw.records['scheduled_event_changes'] = [item for item in claims
            if not isinstance(item,dict) or not isinstance(item.get('id'),str) or item['id'] not in owned]
        apply_commitments(self, raw)
        from backend.runtime_v3.commitments import invalidate_dead_commitments
        invalidate_dead_commitments(self,{cid for cid,c in s['characters'].items() if c['life_status']=='dead'})
        from backend.runtime_v3.personality import apply_personality
        apply_personality(self, raw, events)
        from backend.runtime_v3.values import apply_values
        apply_values(self, raw, events)
        from backend.runtime_v3.lifecycle import queue_invalidations
        queue_invalidations(self)
        from backend.runtime_v3.protagonist import reconcile
        reconcile(s)
        from backend.runtime_v3.pacing import validate_developments, validate_threads, validate_resolved_consequences
        validate_resolved_consequences(self, raw)
        validate_threads(self, raw)
        accepted = validate_developments(self, raw)
        if accepted:
            s['meta']['pacing_recent'] = (s['meta']['pacing_recent'] + accepted)[-12:]
            self.history.state_changes.append(dict(kind='narrative_developments',accepted=accepted,turn_id=self.turn_id))
        from backend.runtime_v3.continuity import apply as apply_continuity, turn_signal, filter_choices
        apply_continuity(self, raw, events)
        from backend.runtime_v3.remote import advance as advance_remote
        advance_remote(s, self.history)
        upserts = {section:{key:deepcopy(value) for key,value in s[section].items() if value != self.before[section].get(key)}
            for section in ('characters','locations','facts','knowledge','relationships','threads','scheduled_events','objective_relations','conditions','residences','roles','organizations','reproductive_events','pregnancies','naming_decisions','possessions','contacts','conversations','remote_events')}
        digest = sha256(json.dumps(self.before,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        patch = StatePatch(digest,deepcopy(s['meta']),deepcopy(s['camera']),upserts)
        state = patch.apply(self.before)
        self.history.state_changes.append(dict(turn_id=self.turn_id,upserts=deepcopy(upserts),
            before_scheduled_events={eid:deepcopy(self.before['scheduled_events'].get(eid)) for eid in upserts['scheduled_events']},
            before_characters={cid:deepcopy(self.before['characters'].get(cid)) for cid in upserts['characters']},player_observed=self.observed))
        record_id=identity('record',self.turn_id,self.narrative,self.observed)
        for event in self.history.events:
            event.update(source_record_id=record_id,source_sequence=self.turn_id-1)
        for change in self.history.state_changes:
            if change.get('id'):
                change['source_record_id'] = record_id
        self.history.turns.append(dict(id=record_id,turn_id=self.turn_id,sequence=self.turn_id-1,
            narrative=self.narrative,player_input=self.player_input,
            continuity=turn_signal(self), camera_before=deepcopy(self.before['camera']),camera=deepcopy(state['camera']),
            game_time_before=self.before['meta']['world_time'],world_time=state['meta']['world_time'],
            player_observed=self.observed))
        choices = raw.choices if self.mode != 'background' and camera['mode'] == 'actor' and controlled and capabilities(state,controlled)['can_act'] else []
        if any(s['meta']['communication'][channel] for channel in ('text_message','voice_call')):
            choices = [c for c in choices if c.get('device_control') is None]
        choices = filter_choices(self, choices)
        if any(s['meta']['communication'][channel] for channel in ('text_message','voice_call')):
            choices = [dict(c, interaction_channel=s['meta']['interaction_focus']) for c in choices]
            remote_call = active_call(self.before, controlled)
            if remote_call:
                remote_ids = participants(remote_call) - set(self.before['camera']['present_character_ids'])
                if remote_ids & set(state['camera']['present_character_ids']):
                    fatal('Звонок не переносит собеседника в физическую сцену.', 'remote_false_colocation')
        return ResolvedTurn(state,patch,self.history.to_dict(),self.warnings,choices,self.cards)
