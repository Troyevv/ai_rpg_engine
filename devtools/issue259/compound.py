"""Pre-qualification compound consequences. No production default imports this.

The existing compiler owns every canonical record. Evidence is copied, not read.
"""
from copy import deepcopy
import json
from jsonschema import Draft202012Validator
from backend.runtime_v3.scene_repair import SceneCandidate, digest, record_key
from backend.runtime_v3.scene_steps import compile_scene, schema_diagnostics
from backend.runtime_v3.raw import OPTIONAL_SECTIONS
from backend.services.world_delta_errors import StructuralDeltaError
from devtools.issue257.destination_prototype import adapt, project as destination

RULES = '''Extract consequential changes established by the completed Narrative against before.
Return one structured result, not a chronological retelling. scene_steps are compound
sources: id, a short verbatim evidence excerpt, and effects. One source can establish
travel AND heard information AND contact. Do not select just one kind for compound
consequences. Do not put a consequence only in evidence. Omit incidental gestures.
A source with one effect uses its source id. Multiple effects have derived identity
id/zero-based-effect-index; domain references must identify the relevant effect,
never an ambiguous whole group. Domain source_event_id and during_step_id use these references. A speech effect may use
`during` with the index of a movement effect IN THE SAME source; this preserves actual
route-time hearing. Otherwise retain explicit during_step_id. Do not infer hearing.
Movement: explicit travellers, actual assertion and destination. A proposal, preparation
or attempt is not arrival. local_exit changes room/visibility within one canonical
address; leaving the building to an exterior is a different place. Use exact existing
place or new {name,anchor_id,relation}, including exterior/interior relation. Never
choose a broad town or similar name merely because its ID exists. Input authorizes
chosen travel but does not prove completion. Never derive arrival from visibility.
Information effects contain the actual learned propositions once, source speaker,
assertion (testimony/observation/etc), per-claim perceivers and status. A question or
greeting can be interaction without claims; an informative answer is information,
whose existing compiler also records contact. Do not duplicate that answer as an
interaction. Reported statement is not objective truth or the whole related secret.
Controlled actor effects need relevant input_source quote and meaning. NPC effects
never inherit player authority. A new significant decision in prose without player
choice belongs in agency_findings with actual evidence; incidental detail is allowed.
No self-assessed clean/verified flag. Substantial narrator dates and elapsed assertions
belong in chronology_claims; beliefs/quotes/lying retain their distinct assertion.
The existing Calendar judges concrete claims. Do not move time to legalize bad prose.
All existing domain outcomes remain available in their typed sections: birth/pregnancy,
death, relationships, personality, property, commitments, remote and scheduled events.
Use a concrete effect as their source; do not invent identity, consent, parentage,
biological elapsed time or knowledge. Unknown speaker/sex/location remains unknown.
scene contains elapsed time and only necessary explicit visibility, no retelling and
no repeated final location. Runtime computes positions and technical records.
choices are up to six optional FUTURE proposals, grounded solely in Choice context
actor-accessible facts/current perception. GM-only secrets never authorize a choice.
No choices authorize current outcomes. Preserve free input, all independent effects,
full input/Narrative and real competing entity references. Empty effects overall are
valid for a scene without meaningful change. Return only the provided JSON schema.
'''


def project(messages):
    out=destination(messages)
    from backend.runtime_v3.context_contract import SEMANTIC_RELATIONSHIP_CONTRACT
    out[0]['content']=RULES + SEMANTIC_RELATIONSHIP_CONTRACT
    for m in out:
        if not m['content'].startswith('JSON Schema\n'):continue
        s=json.loads(m['content'].split('\n',1)[1]);p=s['properties']
        effects=deepcopy(p['scene_steps']['items'])
        for arm in effects['oneOf']:
            props=arm['properties']
            for k in ('id','text','evidence'):props.pop(k,None)
            arm['required']=[k for k in arm.get('required',[]) if k not in ('id','text','evidence')]
            if props['kind'].get('const') in ('information','interaction'):
                props['during']={'type':'integer','minimum':0}
        p['scene_steps']['items']={'type':'object','additionalProperties':False,
            'required':['id','evidence','effects'],'properties':{
            'id':{'type':'string','minLength':1},'evidence':{'type':'string','minLength':1},
            'effects':{'type':'array','minItems':1,'maxItems':16,'items':effects}}}
        for k in ('situation','situation_evidence'):
            p['scene']['properties'].pop(k,None)
        p['scene']['required']=[k for k in p['scene'].get('required',[]) if k in p['scene']['properties']]
        m['content']='JSON Schema\n'+json.dumps(s,ensure_ascii=False,separators=(',',':'))
    return out


def effect_id(source,index):
    return source['id'] if len(source['effects'])==1 else f"{source['id']}/{index}"


def expand(value):
    result=deepcopy(value);steps=[];origins=[];errors=[]
    aliases={f"{s['id']}/0":s['id'] for s in value['scene_steps'] if len(s['effects'])==1}
    ambiguous={s['id'] for s in value['scene_steps'] if len(s['effects'])>1}
    def references(node,key='',path=()):
        if isinstance(node,dict):return {k:references(v,k,path+(k,)) for k,v in node.items()}
        if isinstance(node,list):return [references(v,key,path+(i,)) for i,v in enumerate(node)]
        if isinstance(node,str) and key in ('source_event_id','source_event_ids','during_step_id','involuntary_source_id'):
            if node in ambiguous and (not path or path[0] not in OPTIONAL_SECTIONS):
                suffix=''.join(f'[{part}]' if isinstance(part,int) else ('.' if j else '')+part for j,part in enumerate(path[2:]))
                errors.append(StructuralDeltaError('Select the specific effect of this compound source.',code='scene_schema_invalid',entity=node,section=path[0] if path else 'scene_steps',index=path[1] if len(path)>1 and isinstance(path[1],int) else None,field=suffix or key))
            return aliases.get(node,node)
        return node
    result=references(result)
    for i,source in enumerate(result['scene_steps']):
        for j,effect in enumerate(source['effects']):
            step=deepcopy(effect);step.update(id=effect_id(source,j),text=source['evidence'],evidence=source['evidence'])
            if 'during' in step:
                index=step.pop('during')
                if 'during_step_id' in step or index>=len(source['effects']) or source['effects'][index].get('kind')!='movement':
                    errors.append(StructuralDeltaError('during must identify one movement effect in this source, without another route reference.',code='scene_schema_invalid',section='scene_steps',index=i,field=f'effects[{j}].during'))
                else:step['during_step_id']=effect_id(source,index)
            steps.append(step);origins.append((i,j))
    result['scene_steps']=steps
    if errors:raise StructuralDeltaError.combine(errors)
    return result,origins


class CompoundCandidate(SceneCandidate):
    def __init__(self,*args,schema,**kwargs):
        super().__init__(*args,**kwargs);self.schema=schema;self.origins=[];self.effect_scope={}
        self.binding=digest([self.binding,'compound259',schema])

    def _parse(self,payload,*,defer_errors=False):
        value=self.apply(payload) if self.scope is not None else deepcopy(payload)
        self.base=None
        errors=[row for e in Draft202012Validator(self.schema).iter_errors(value) for row in schema_diagnostics(e,value)]
        if errors:raise StructuralDeltaError.combine(errors)
        ids=[s['id'] for s in value['scene_steps']]
        if len(set(ids))!=len(ids):raise StructuralDeltaError('Duplicate source IDs',code='scene_schema_invalid',section='scene_steps')
        self.base=deepcopy(value)
        self.origins=[]
        expanded,self.origins=expand(value)
        expanded=adapt(expanded,self.before,self.turn_id,self.namespace)
        self.raw=compile_scene(expanded,self.before,self.narrative,self.turn_id,version=8,namespace=self.namespace,defer_errors=defer_errors)
        self.raw.warnings.extend(self.revisions)
        return self.raw

    def external_feedback(self,rows):
        if self.base is None:return
        self.effect_scope={}
        for row in rows:
            i=row.get('index')
            if row.get('section')=='scene_steps' and isinstance(i,int) and i<len(self.origins):
                group,effect=self.origins[i];self.effect_scope.setdefault(self.base['scene_steps'][group]['id'],set()).add(effect);row['compiled_path']=row.get('path')
                row.update(index=group,local_id=self.base['scene_steps'][group]['id'],path=f'scene_steps[{group}].effects[{effect}]')
                if 'claim_index' in row:
                    row['path']+=f".claims[{row.pop('claim_index')}]"
                row['player_input']=self.player_input
                row['source_evidence']=self.base['scene_steps'][group]['evidence']
                if row.get('code') in ('player_action_source_invalid','movement_agency') or (row.get('code')=='player_action_event_mismatch' and row.get('reason') in ('missing_player_action_id','missing_player_evidence')):
                    row['compiled_reason']=row.get('repair_reason')
                    row['repair_reason']='This effect lacks a valid source of controlled-actor authority. Compare its actual decision with player_input; an unrelated genuine input quote does not authorize it. For an actually chosen effect use input_source with the relevant input quote and meaning. For a substantial unchosen decision in Narrative, retain the consequence and add agency_findings unauthorized_choice with its evidence. NPC effects have no player input_source. Do not fabricate a source, remove a significant outcome, or edit internal compiler records.'
                    row['path']+='.input_source'

    def feedback(self,diagnostics,original):
        result=json.loads(super().feedback(diagnostics,original))
        if self.scope is not None:
            # The existing scope owner selects semantic sources. Their derived
            # identities are the same dependency, not unrelated new records.
            derived={effect_id(s,j) for s in self.base['scene_steps'] if s['id'] in self.scope['step_ids'] for j in range(len(s['effects']))}
            self.scope['dependencies']=sorted(set(self.scope['dependencies'])|derived)
            result['scope']=deepcopy(self.scope)
        result['contract']+=' Source records contain evidence and effects; never return flattened compiler steps. Preserve independent effects within each replacement.'
        return json.dumps(result,ensure_ascii=False)

    def apply(self,payload):
        payload=deepcopy(payload)
        if (not isinstance(payload.get('sections',{}),dict)
                or not isinstance(payload.get('withdrawals',[]),list)
                or any(not isinstance(v,dict) for v in payload.get('withdrawals',[]))):
            return super().apply(payload)
        # A model explicitly selecting an effect of the SAME scoped source is
        # a reference refinement. Digest-keyed domain records otherwise become
        # additions and leave their damaged predecessor behind. Match all other
        # fields exactly; never infer which effect the model intended.
        parents={effect_id(s,j):s['id'] for s in self.base['scene_steps'] if s['id'] in self.scope['step_ids'] and len(s['effects'])>1 for j in range(len(s['effects']))}
        def parent_refs(node,key=''):
            if isinstance(node,dict):return {k:parent_refs(v,k) for k,v in node.items()}
            if isinstance(node,list):return [parent_refs(v,key) for v in node]
            return parents.get(node,node) if isinstance(node,str) and key in ('source_event_id','source_event_ids','during_step_id','involuntary_source_id') else node
        for section,items in payload.get('sections',{}).items():
            if not isinstance(items,list):continue
            editable=set(self.scope['record_keys'].get(section,[]))
            old=self.base.get(section,[])
            if not isinstance(old,list):continue
            for item in items:
                if record_key(item) in {record_key(v) for v in old}:continue
                matches=[v for v in old if record_key(v) in editable and not v.get('id') and parent_refs(item)==v and item!=v]
                if len(matches)==1:
                    key=record_key(matches[0])
                    withdrawals=payload.setdefault('withdrawals',[])
                    if not any(v.get('section')==section and v.get('record_key')==key for v in withdrawals):
                        withdrawals.append(dict(section=section,record_key=key,reason='Explicit typed reference refined to an effect of the same source; all other fields unchanged.'))
        result=super().apply(payload)
        for old,new in zip(self.base['scene_steps'],[s for s in result['scene_steps'] if s['id'] in {v['id'] for v in self.base['scene_steps']}]):
            allowed=self.effect_scope.get(old['id'])
            if allowed is None:continue
            if len(new['effects'])<len(old['effects']) or any(v!=new['effects'][i] for i,v in enumerate(old['effects']) if i not in allowed):
                raise StructuralDeltaError('Repair removed or changed independent effects.',code='scene_repair_scope',section='scene_steps',entity=old['id'])
        return result
