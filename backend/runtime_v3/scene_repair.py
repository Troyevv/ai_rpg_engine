"""One-candidate bounded replacement protocol; never patches WorldState."""
from copy import deepcopy
from hashlib import sha256
import json
from backend.runtime_v3.models import fatal
from backend.runtime_v3.scene_steps import decode, compile_scene
from backend.runtime_v3.raw import SECTIONS


def digest(value):
    return sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def strings(value):
    if isinstance(value,dict):
        return set().union(*(strings(v) for v in value.values())) if value else set()
    if isinstance(value,list):
        return set().union(*(strings(v) for v in value)) if value else set()
    return {value} if isinstance(value,str) else set()


def references(value, key=''):
    """Exact typed references/identities, excluding prose and evidence strings."""
    if isinstance(value, dict):
        return set().union(*(references(v,k) for k,v in value.items())) if value else set()
    if isinstance(value, list):
        return set().union(*(references(v,key) for v in value)) if value else set()
    roles={'actor_id','actor_ids','source_actor_id','target_ids','intended_target_ids','character_ids',
           'owner_id','holder_id','decision_actor_id','source_id','target_id'}
    return {value} if isinstance(value,str) and key not in roles and (key in ('id','endpoint') or key.endswith(('_id','_ids'))) else set()


def record_key(item):
    return item.get('id') if isinstance(item,dict) and isinstance(item.get('id'),str) else digest(item)


class SceneCandidate:
    def __init__(self, before, narrative, player_input, turn_id, *, namespace=None, on_record=None):
        self.before,self.narrative,self.player_input,self.turn_id=before,narrative,player_input,turn_id
        self.namespace=namespace
        self.on_record=on_record
        self.base=None;self.raw=None;self.scope=None;self.hash=None;self.revisions=[]
        self.binding=digest([before,narrative,player_input,turn_id,namespace,6])

    def parse(self, payload):
        self.raw = None
        mode = 'targeted' if self.scope is not None else 'full'
        try:
            return self._parse(payload)
        finally:
            if self.on_record:
                from dataclasses import asdict
                self.on_record(dict(contract=6, binding=self.binding, mode=mode,
                    candidate_hash=digest([self.binding,self.base]) if self.base is not None else None,
                    candidate=self.base, compiled=asdict(self.raw) if self.raw is not None else None,
                    turn_id=self.turn_id, namespace=self.namespace))

    def _parse(self, payload):
        if self.scope is not None:
            candidate=self.apply(payload)
        else:
            candidate=decode(payload)
        self.base=deepcopy(candidate) if all(isinstance(s,dict) and isinstance(s.get('id'),str) and s['id'] for s in candidate['scene_steps']) and len({s['id'] for s in candidate['scene_steps']})==len(candidate['scene_steps']) else None
        self.raw=compile_scene(candidate,self.before,self.narrative,self.turn_id,namespace=self.namespace)
        self.raw.warnings.extend(self.revisions)
        return self.raw

    def feedback(self, diagnostics, original):
        rows=diagnostics if isinstance(diagnostics,list) else [diagnostics]
        if self.base is None:
            return json.dumps(dict(repair_mode='full',diagnostics=rows,original_extraction=original,
                contract='Return one complete Extraction/6 scene_steps + scene. No patch base exists. Never rewrite Narrative/input/before.'),ensure_ascii=False)
        steps=self.base['scene_steps']
        selected=set(); sections=set(); selected_records={}
        # Map derived paths back to their semantic source, never ask the model
        # to edit compiler-owned Event/Movement identifiers.
        for row in rows:
            section=row.get('section',row.get('domain'))
            section={'relationships':'relationship_changes','characters':'character_changes',
                'scheduled_events':'scheduled_event_changes','threads':'thread_changes'}.get(section,section)
            index=row.get('index')
            source=None
            if self.raw and section=='events': source=self.raw.event_sources.get(index)
            if self.raw and section=='movements' and index in self.raw.movement_sources:
                source=dict(section='scene_steps',index=self.raw.movement_sources[index])
            if source:
                row.update(source, path=f"scene_steps[{source['index']}]")
                section,index='scene_steps',source['index']
            if section=='scene_steps' and isinstance(index,int) and index<len(steps): selected.add(steps[index]['id'])
            elif section in ('events','movements','player_agency','information_events','knowledge_gained','final_scene','scene','runtime',None):
                selected.update(s['id'] for s in steps);sections.add('scene')
            elif section in SECTIONS or section in self.base:
                sections.add(section)
                values=self.base.get(section,[])
                if isinstance(values,list):
                    selected_records.setdefault(section,set()).update(
                        {index} if isinstance(index,int) and 0<=index<len(values) else range(len(values)))
        # Route/presence dependencies share explicit actors. ID references bind
        # other domains. This deliberately errs toward rechecking dependencies,
        # while unconnected proposals remain byte-for-byte unchanged.
        changed=True
        while changed:
            old=(set(selected),set(sections))
            actors=set()
            for s in steps:
                if s['id'] in selected:
                    for key in ('actor_id','source_actor_id','actor_ids','target_ids'):
                        actors.update(strings(s.get(key)))
            for s in steps:
                roles=set().union(*(strings(s.get(k)) for k in ('actor_id','source_actor_id','actor_ids','target_ids','claims')))
                if roles & actors or strings(s)&selected: selected.add(s['id'])
            dependencies=set(selected)
            for step in steps:
                if step['id'] in selected:dependencies.update(references(step))
            for section,indexes in selected_records.items():
                for index in indexes:dependencies.update(references(self.base[section][index]))
            for step in steps:
                if references(step)&dependencies:selected.add(step['id'])
            record_count=sum(map(len,selected_records.values()))
            for section,values in self.base.items():
                if section in ('scene_steps','scene','choices','agency_findings','chronology_claims') or not isinstance(values,list):continue
                for index,item in enumerate(values):
                    role_dependent=section in ('promotions','character_changes') and isinstance(item,dict) and item.get('id') in actors
                    if references(item)&dependencies or role_dependent:
                        sections.add(section);selected_records.setdefault(section,set()).add(index)
            changed=(selected,sections)!=old or record_count!=sum(map(len,selected_records.values()))
        # Missing declarations are repairable dependencies, not a reason to ban
        # new places/people. Added records must be referenced by the repaired group.
        if selected:
            sections.update(('scene','locations','promotions','facts'))
        sections.update(('agency_findings','chronology_claims'))
        self.hash=digest([self.binding,self.base])
        self.scope=dict(step_ids=sorted(selected),sections=sorted(sections),
            record_keys={section:[record_key(self.base[section][i]) for i in sorted(indexes)]
                         for section,indexes in selected_records.items()}, dependencies=sorted(dependencies),actor_ids=sorted(actors))
        return json.dumps(dict(repair_mode='targeted',candidate_hash=self.hash,scope=self.scope,
            diagnostics=rows,original_extraction=self.base,record_keys={k:[record_key(item) for item in v] for k,v in self.base.items() if k in sections and isinstance(v,list)},
            contract='Return candidate_hash, replacements, sections, reason only. Replace listed step IDs in place; no deletions or reordering. '
                'sections arrays contain only keyed edits/additions; code keeps unmentioned records, also within the same section. scene is a partial field update. New declarations must be referenced by affected steps. '
                'Remove a mistaken scoped record only with withdrawals listing section, record_key (id or digest), and individual reason. '
                'New dependencies may be supplied as additions after an allowed step. Reinterpret the full unchanged Narrative/input. '
                'All connected affected consequences must agree; independent records are retained by code. '
                'Do not erase a confirmed outcome or invent arrival/consent to pass. Semantic correction of a mistaken assertion needs an explicit reason. '
                'Invalid prose uses agency_findings/chronology_claims for existing narrative recovery. One automatic repair only.'),ensure_ascii=False,separators=(',',':'))

    def apply(self,payload):
        try:p=json.loads(payload) if isinstance(payload,str) else deepcopy(payload)
        except (ValueError,TypeError):fatal('Некорректный repair JSON.', 'scene_repair_invalid')
        if not isinstance(p,dict) or set(p)-{'candidate_hash','replacements','sections','additions','withdrawals','reason'} or p.get('candidate_hash')!=self.hash:
            fatal('Repair относится к другому кандидату или имеет неверную форму.', 'scene_repair_stale')
        if not isinstance(p.get('reason'),str) or not p['reason'].strip():fatal('Нужна причина смысловой коррекции.', 'scene_repair_invalid')
        replacements=p.get('replacements',[]);sections=p.get('sections',{});additions=p.get('additions',[])
        if not isinstance(replacements,list) or not isinstance(sections,dict) or not isinstance(additions,list):fatal('Неверный repair envelope.', 'scene_repair_invalid')
        ids=[s.get('id') if isinstance(s,dict) else None for s in replacements]
        if any(not isinstance(s,str) for s in ids) or len(set(ids))!=len(ids) or set(ids)-set(self.scope['step_ids']) or set(sections)-set(self.scope['sections']):
            fatal('Repair изменяет запись вне разрешённой области.', 'scene_repair_scope')
        result=deepcopy(self.base)
        edits={s['id']:s for s in replacements}
        result['scene_steps']=[edits.get(s['id'],s) for s in result['scene_steps']]
        added_ids=set(s['id'] for s in result['scene_steps'])
        insertion_tail={}
        for addition in additions:
            if not isinstance(addition,dict) or set(addition)!={'after_id','step'} or addition['after_id'] not in self.scope['step_ids']:
                fatal('Добавление вне области repair.', 'scene_repair_scope')
            step=addition['step']
            if not isinstance(step,dict) or not isinstance(step.get('id'),str) or step['id'] in added_ids:
                fatal('Повторная/неизвестная запись repair.', 'scene_repair_invalid')
            added_ids.add(step['id'])
            anchor=insertion_tail.get(addition['after_id'],addition['after_id'])
            at=next(i for i,s in enumerate(result['scene_steps']) if s['id']==anchor)
            result['scene_steps'].insert(at+1,step)
            insertion_tail[addition['after_id']]=step['id']
        dependencies=set(self.scope['dependencies'])
        actor_ids=set(self.scope['actor_ids'])
        for step in result['scene_steps']:
            if step['id'] in set(self.scope['step_ids']) | (added_ids-set(s['id'] for s in self.base['scene_steps'])):
                dependencies.update(references(step))
                actor_ids.update(set().union(*(strings(step.get(k)) for k in ('actor_id','source_actor_id','actor_ids','target_ids'))))
        # Section arrays are keyed edits, not whole replacements. Code retains
        # unmentioned records; explicit withdrawals are the only deletion path.
        withdrawals=p.get('withdrawals',[])
        if not isinstance(withdrawals,list):fatal('Неверные withdrawals.', 'scene_repair_invalid')
        removed=set()
        self.revisions=[]
        for item in withdrawals:
            if not isinstance(item,dict) or set(item)!={'section','record_key','reason'} or not all(isinstance(item[k],str) and item[k].strip() for k in item):
                fatal('Каждый пересмотр требует отдельной причины.', 'scene_repair_invalid')
            section,key=item['section'],item['record_key']
            allowed=set(self.scope['record_keys'].get(section,[]))
            if section in ('agency_findings','chronology_claims'):
                allowed={record_key(v) for v in self.base.get(section,[])}
            if section not in self.scope['sections'] or key not in allowed or (section,key) in removed:
                fatal('Удаление вне исправляемой группы или повторная операция.', 'scene_repair_scope')
            removed.add((section,key))
            result[section]=[v for v in result.get(section,[]) if record_key(v)!=key]
            self.revisions.append(dict(code='semantic_reinterpretation',action='recheck_candidate',**item))
        for section,value in sections.items():
            if section=='scene':
                if not isinstance(value,dict):fatal('Неверная сцена repair.', 'scene_repair_invalid')
                result['scene'].update(deepcopy(value));continue
            if not isinstance(value,list):fatal('Секция repair должна оставаться списком.', 'scene_repair_invalid',section=section)
            old=self.base.get(section,[])
            if not isinstance(old,list):old=[]
            current=result.setdefault(section,[])
            if not isinstance(current,list):current=[];result[section]=current
            old_by_key={record_key(item):item for item in old}
            editable=set(self.scope['record_keys'].get(section,[]))
            findings=section in ('agency_findings','chronology_claims')
            keys=set()
            for item in value:
                key=record_key(item)
                if key in keys or (section,key) in removed: fatal('Повторная операция repair.', 'scene_repair_invalid')
                keys.add(key)
                if key in old_by_key:
                    if item==old_by_key[key]:continue
                    if key not in editable and not findings:
                        fatal('Repair меняет независимую запись внутри секции.', 'scene_repair_scope',section=section)
                    current[:]=[deepcopy(item) if record_key(v)==key else v for v in current]
                    self.revisions.append(dict(code='semantic_reinterpretation',action='recheck_candidate',
                        section=section,record_key=key,reason=p['reason']))
                else:
                    role_dependent=section in ('promotions','character_changes') and isinstance(item,dict) and item.get('id') in actor_ids
                    if not references(item)&dependencies and not role_dependent and not findings:
                        fatal('Новая запись не связана с исправляемой группой.', 'scene_repair_scope',section=section)
                    current.append(deepcopy(item))
        for i,old in enumerate(self.base['scene_steps']):
            replacement=edits.get(old['id'])
            if replacement is not None and replacement!=old:
                self.revisions.append(dict(code='semantic_reinterpretation',action='recheck_candidate',
                    section='scene_steps',index=i,source_ids=[old['id']],reason=p['reason']))
        return result


def repair_schema(full_schema, feedback):
    """Same step/domain types as the first answer, projected to scoped edits."""
    info=json.loads(feedback)
    if info.get('repair_mode')!='targeted':return full_schema
    steps=full_schema['properties']['scene_steps']['items']
    schema = dict(type='object',additionalProperties=False,
        **{'$defs':deepcopy(full_schema.get('$defs',{}))},
        properties=dict(candidate_hash=dict(type='string',const=info['candidate_hash']),
            replacements=dict(type='array',items=deepcopy(steps)),
            sections=dict(type='object',additionalProperties=False,properties={k:deepcopy(v) for k,v in full_schema['properties'].items() if k in info['scope']['sections']}),
            additions=dict(type='array',items=dict(type='object',additionalProperties=False,properties=dict(after_id=dict(type='string',enum=info['scope']['step_ids']),step=deepcopy(steps)),required=['after_id','step'])),
            withdrawals=dict(type='array',items=dict(type='object',additionalProperties=False,properties={k:dict(type='string',minLength=1) for k in ('section','record_key','reason')},required=['section','record_key','reason'])),
            reason=dict(type='string',minLength=1)),required=['candidate_hash','replacements','sections','reason'])

    scene=schema['properties']['sections']['properties'].get('scene')
    if scene is not None:scene['required']=[]
    from backend.runtime_v3.raw import prune_schema_definitions
    return prune_schema_definitions(schema)
