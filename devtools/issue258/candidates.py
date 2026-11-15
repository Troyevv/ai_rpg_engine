"""Unselected semantic projections for bounded #258 experiments, never production.

S: one speech record owns contact plus explicit perceptions.
R: explicit model assessment reuses the existing findings/chronology owners.
Neither projection interprets prose or grants authority from a model status.
"""
from copy import deepcopy
import json
from devtools.issue257.destination_prototype import DestinationCandidate, project as destination, adapt
from backend.runtime_v3.scene_steps import decode, compile_scene
from backend.runtime_v3.scene_repair import digest
from backend.runtime_v3.models import fatal
from jsonschema import Draft202012Validator


def project(messages, *, speech=False, review=False):
    out=destination(messages)
    for message in out:
        if not message['content'].startswith('JSON Schema\n'):continue
        schema=json.loads(message['content'].split('\n',1)[1])
        props=schema['properties']
        if speech:
            arms=props['scene_steps']['items']['oneOf']
            # Wire schema has expanded step alternatives, except shared domain defs.
            info=next(a for a in arms if a.get('properties',{}).get('kind',{}).get('const')=='information')
            spoken=deepcopy(info);sp=spoken['properties'];sp['kind']={'const':'speech','type':'string'}
            sp['claims']['minItems']=0
            interaction=next(a for a in arms if a.get('properties',{}).get('kind',{}).get('const')=='interaction')
            sp['outcome']=deepcopy(interaction['properties']['outcome']);spoken['required'].append('outcome')
            sp['medium']['enum']=['conversation','testimony']
            spoken.setdefault('allOf',[]).append({'if':{'properties':{'outcome':{'enum':['attempted','deferred','not_performed']}}},'then':{'properties':{'claims':{'maxItems':0}}}})
            info['properties']['medium']['enum']=['observation','discovery','message']
            arms.append(spoken)
        if review:
            findings=props.pop('agency_findings');claims=props.pop('chronology_claims')
            props['semantic_reviews']={'type':'array','minItems':2,'maxItems':2,'items':{'oneOf':[
                dict(type='object',additionalProperties=False,required=['domain','assessment','findings'],properties=dict(domain=dict(const='agency'),assessment=dict(enum=['conflict','no_significant_conflict','unassessed','not_applicable']),findings=findings)),
                dict(type='object',additionalProperties=False,required=['domain','assessment','claims'],properties=dict(domain=dict(const='time'),assessment=dict(enum=['conflict','no_significant_conflict','unassessed','not_applicable']),claims=claims))]}}
            props['semantic_reviews']['allOf']=[{'contains':{'properties':{'domain':{'const':domain}},'required':['domain']}} for domain in ('agency','time')]
            schema['required'].append('semantic_reviews')
        message['content']='JSON Schema\n'+json.dumps(schema,ensure_ascii=False,separators=(',',':'))
    if speech:out[0]['content']+='\nExperimental speech projection: every spoken interaction uses kind=speech, with source_actor_id, actual target_ids, outcome, channel, medium and explicit perceived claims in ONE step. interaction is for nonverbal contact; information is for observation/discovery/messages. Empty claims are valid for a greeting/question or no significant new information. Preserve during_step_id for speech along a route. Targets never imply perceivers. Testimony is not objective truth; partial disclosure is not the full secret. Unknown speaker remains null. No duplicate interaction/information copy of speech.\n'
    if review:out[0]['content']+='\nExperimental semantic_reviews replaces top-level agency_findings/chronology_claims: exactly one agency and one time record. Explicitly assess substantial new player decisions and objective time assertions; retain existing findings/claims in their respective record. Distinguish conflict, no_significant_conflict, unassessed, not_applicable. Assessment is model interpretation, not permission. Do not inventory everyday gestures. Quotes/beliefs are distinct from narrator facts. Uncertainty alone does not block a turn. Never infer a clean assessment merely from absent records.\n'
    return out


class SemanticCandidate(DestinationCandidate):
    """QA projection; production defaults never reference this class."""
    def __init__(self,*args,speech=False,review=False,**kwargs):
        super().__init__(*args,**kwargs)
        self.speech,self.review=speech,review
        from backend.runtime_v3.scene_steps import input_schema
        from backend.services.structured_extraction import request_schema
        self.schema=request_schema(project([dict(role='system',content=''),dict(role='user',content='JSON Schema\n'+json.dumps(input_schema(self.version,self.before['camera']['mode'])))],speech=speech,review=review))
        self.binding=digest([self.binding,'issue258-semantic',speech,review])

    def _parse(self,payload,*,defer_errors=False):
        value=self.apply(payload) if self.scope is not None else decode(payload)
        ids=[s.get('id') for s in value['scene_steps'] if isinstance(s,dict)]
        self.base=deepcopy(value) if len(ids)==len(value['scene_steps']) and all(isinstance(i,str) and i for i in ids) and len(set(ids))==len(ids) else None
        from backend.runtime_v3.scene_steps import schema_diagnostics
        from backend.services.world_delta_errors import StructuralDeltaError
        errors=[row for error in Draft202012Validator(self.schema).iter_errors(value) for row in schema_diagnostics(error,value)]
        if errors:raise StructuralDeltaError.combine(errors)
        compiled=adapt(value,self.before,self.turn_id,self.namespace)
        outcomes={}
        for index,step in enumerate(compiled['scene_steps']):
            if step.get('kind')!='speech':continue
            if not self.speech:fatal('Speech projection disabled','scene_schema_invalid')
            outcomes[step['id']]=step.pop('outcome')
            if step.get('claims'):
                if outcomes[step['id']] in ('deferred','not_performed','attempted'):
                    fatal('Unperformed speech cannot transmit claims','scene_schema_invalid',section='scene_steps',index=index,field='claims')
                step['kind']='information'
            else:
                step['kind']='interaction';step['actor_id']=step.pop('source_actor_id')
                step.pop('medium');step.pop('claims');step['outcome']=outcomes[step['id']]
        reviews=compiled.pop('semantic_reviews',None)
        if self.review:
            if not isinstance(reviews,list) or len(reviews)!=2 or {x.get('domain') for x in reviews} != {'agency','time'}:
                fatal('Exactly one agency and time assessment required','scene_schema_invalid',section='semantic_reviews')
            for row in reviews:
                compiled['agency_findings' if row['domain']=='agency' else 'chronology_claims']=row['findings' if row['domain']=='agency' else 'claims']
        self.raw=compile_scene(compiled,self.before,self.narrative,self.turn_id,namespace=self.namespace,version=self.version,defer_errors=defer_errors)
        # Information already compiles its contact, perceptions and source links.
        # Retain partial speech outcome on the same generated action, no duplicate event.
        from backend.runtime_v3.models import identity
        for action in self.raw.player_agency['actions']:
            for sid,outcome in outcomes.items():
                if action['id']==identity('scene-action',self.turn_id,self.namespace,sid):action['outcome']=outcome
        if reviews:self.raw.warnings.append(dict(code='experimental_semantic_assessment',reviews=deepcopy(reviews),action='record_only'))
        self.raw.warnings.extend(self.revisions)
        return self.raw

    def feedback(self,diagnostics,original):
        result=json.loads(super().feedback(diagnostics,original))
        if self.review and self.scope is not None:
            self.scope['sections']=[s for s in self.scope['sections'] if s not in ('agency_findings','chronology_claims')]+['semantic_reviews']
            result['scope']=self.scope
            result['contract']=result['contract'].replace('agency_findings/chronology_claims','semantic_reviews findings/claims')
            for row in result['diagnostics']:
                if 'repair_reason' in row:row['repair_reason']=row['repair_reason'].replace('agency_findings','semantic_reviews agency findings')
        return json.dumps(result,ensure_ascii=False)

    def apply(self,payload):
        from backend.runtime_v3.structured_payload import object_payload
        patch=deepcopy(object_payload(payload)[0]);reviews=patch.get('sections',{}).pop('semantic_reviews',None)
        result=super().apply(patch)
        if reviews is not None:
            if not self.review or 'semantic_reviews' not in self.scope['sections']:fatal('Review outside scope','scene_repair_scope')
            result['semantic_reviews']=reviews
        return result
