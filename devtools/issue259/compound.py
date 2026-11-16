"""Pre-qualification compound consequences. No production default imports this.

The existing compiler owns every canonical record. Evidence is copied, not read.
"""
from copy import deepcopy
import json
from jsonschema import Draft202012Validator
from backend.runtime_v3.scene_repair import SceneCandidate, digest
from backend.runtime_v3.scene_steps import compile_scene, schema_diagnostics
from backend.services.world_delta_errors import StructuralDeltaError
from devtools.issue257.destination_prototype import adapt, project as destination

RULES = '''Extract consequential changes established by the completed Narrative against before.
Return one structured result, not a chronological retelling. scene_steps are compound
sources: id, a short verbatim evidence excerpt, and effects. One source can establish
travel AND heard information AND contact. Do not select just one kind for compound
consequences. Do not put a consequence only in evidence. Omit incidental gestures.
Effects have server-derived identity id/zero-based-effect-index. Domain source_event_id
and cross-source during_step_id reference that identity. A speech effect may use
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
    out[0]['content']=RULES
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


def expand(value):
    result=deepcopy(value);steps=[];origins=[]
    for i,source in enumerate(value['scene_steps']):
        for j,effect in enumerate(source['effects']):
            step=deepcopy(effect);step.update(id=f"{source['id']}/{j}",text=source['evidence'],evidence=source['evidence'])
            if 'during' in step:
                index=step.pop('during')
                if 'during_step_id' in step or index>=len(source['effects']) or source['effects'][index].get('kind')!='movement':
                    raise StructuralDeltaError('during must identify one movement effect in this source, without another route reference.',code='scene_schema_invalid',section='scene_steps',index=i,field=f'effects[{j}].during')
                step['during_step_id']=f"{source['id']}/{index}"
            steps.append(step);origins.append((i,j))
    result['scene_steps']=steps
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

    def feedback(self,diagnostics,original):
        result=json.loads(super().feedback(diagnostics,original))
        result['contract']+=' Source records contain evidence and effects; never return flattened compiler steps. Preserve independent effects within each replacement.'
        return json.dumps(result,ensure_ascii=False)

    def apply(self,payload):
        result=super().apply(payload)
        for old,new in zip(self.base['scene_steps'],[s for s in result['scene_steps'] if s['id'] in {v['id'] for v in self.base['scene_steps']}]):
            allowed=self.effect_scope.get(old['id'])
            if allowed is None:continue
            if len(new['effects'])<len(old['effects']) or any(v!=new['effects'][i] for i,v in enumerate(old['effects']) if i not in allowed):
                raise StructuralDeltaError('Repair removed or changed independent effects.',code='scene_repair_scope',section='scene_steps',entity=old['id'])
        return result
