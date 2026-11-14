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
    return {value} if isinstance(value,str) and (key=='id' or key.endswith(('_id','_ids'))) else set()


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
        selected=set(); sections=set()
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
            elif section in SECTIONS or section in self.base: sections.add(section)
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
            for section in sections:
                dependencies.update(references(self.base.get(section)))
            for s in steps:
                if references(s)&dependencies:selected.add(s['id'])
            for section,value in self.base.items():
                if section not in ('scene_steps','scene','choices') and references(value)&dependencies:sections.add(section)
                if section in sections:
                    selected.update(s['id'] for s in steps if s['id'] in strings(value))
            changed=(selected,sections)!=old
        if selected:sections.update(('scene','agency_findings'))
        # Always permit semantic reporting that the unchanged Narrative is bad.
        sections.add('agency_findings')
        self.hash=digest([self.binding,self.base])
        self.scope=dict(step_ids=sorted(selected),sections=sorted(sections))
        return json.dumps(dict(repair_mode='targeted',candidate_hash=self.hash,scope=self.scope,
            diagnostics=rows,original_extraction=self.base,record_keys={k:[item.get('id') if isinstance(item,dict) and isinstance(item.get('id'),str) else digest(item) for item in v] for k,v in self.base.items() if k in sections and isinstance(v,list)},
            contract='Return candidate_hash, replacements, sections, reason only. Replace listed step IDs in place; no deletions or reordering. '
                'Section records cannot disappear silently: withdrawals lists section, record_key (id or digest), and individual reason. '
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
        for addition in additions:
            if not isinstance(addition,dict) or set(addition)!={'after_id','step'} or addition['after_id'] not in self.scope['step_ids']:
                fatal('Добавление вне области repair.', 'scene_repair_scope')
            step=addition['step']
            if not isinstance(step,dict) or not isinstance(step.get('id'),str) or step['id'] in added_ids:
                fatal('Повторная/неизвестная запись repair.', 'scene_repair_invalid')
            added_ids.add(step['id'])
            at=next(i for i,s in enumerate(result['scene_steps']) if s['id']==addition['after_id'])
            result['scene_steps'].insert(at+1,step)
        # No loss by section omission: only explicit scoped replacements apply.
        # An omitted domain outcome is not an implicit fix. Require a named,
        # auditable reinterpretation, bounded to the same affected group.
        withdrawals=p.get('withdrawals',[])
        if not isinstance(withdrawals,list):fatal('Неверные withdrawals.', 'scene_repair_invalid')
        expected=set()
        for section,value in sections.items():
            old=self.base.get(section)
            if isinstance(old,list) and isinstance(value,list):
                def record_key(item):return item.get('id') if isinstance(item,dict) and isinstance(item.get('id'),str) else digest(item)
                kept={record_key(item) for item in value}
                expected.update((section,record_key(item)) for item in old if record_key(item) not in kept)
        declared=set()
        for withdrawal in withdrawals:
            if not isinstance(withdrawal,dict) or set(withdrawal)!={'section','record_key','reason'} or not isinstance(withdrawal['reason'],str) or not withdrawal['reason'].strip():
                fatal('Каждый пересмотр требует отдельной причины.', 'scene_repair_invalid')
            key=(withdrawal['section'],withdrawal['record_key'])
            if key in declared: fatal('Повторный withdrawal.', 'scene_repair_invalid')
            declared.add(key)
        if declared!=expected:
            fatal('Потеря исхода без явного смыслового пересмотра.', 'scene_repair_outcome_loss')
        self.revisions=[dict(code='semantic_reinterpretation',action='recheck_candidate',**item) for item in withdrawals]
        for i,old in enumerate(self.base['scene_steps']):
            replacement=edits.get(old['id'])
            if replacement is not None and replacement!=old:
                self.revisions.append(dict(code='semantic_reinterpretation',action='recheck_candidate',
                    section='scene_steps',index=i,source_ids=[old['id']],reason=p['reason']))
        result.update(deepcopy(sections))
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

    from backend.runtime_v3.raw import prune_schema_definitions
    return prune_schema_definitions(schema)
