"""Unselected, offline D prototype. No production imports this module.

One destination declaration replaces endpoint + the route's Location declaration.
The model supplies identity/relation; this adapter only creates ordinary records.
No prose interpretation, address inference, parent inference or Knowledge changes.
"""
from copy import deepcopy
import hashlib
import json
from jsonschema import Draft202012Validator
from backend.runtime_v3.scene_repair import SceneCandidate, digest
from backend.runtime_v3.scene_steps import decode, compile_scene
from backend.services.world_delta_errors import StructuralDeltaError

TEXT={'type':'string','minLength':1,'pattern':r'\S'}
DESTINATION={'anyOf':[
    {'type':'null'},
    {'type':'object','additionalProperties':False,'required':['existing_id'], 'properties':{'existing_id':TEXT}},
    {'type':'object','additionalProperties':False,'required':['name','anchor_id','relation'],
     'properties':{'name':TEXT,'anchor_id':TEXT,'relation':TEXT}},
]}
INSTRUCTION='''
Experimental destination projection (not production Extraction/7): movement has
one destination instead of endpoint. Use {existing_id} for exactly that canonical
place, or {name,anchor_id,relation} for a new place relative to a known landmark.
relation describes the actual spatial relation, including inside/outside when known.
A new destination creates one ordinary Location automatically; do not repeat that
place in locations. Other new locations remain allowed in locations. This replaces
route endpoint/declaration bookkeeping only. No extra destination evidence copy.
Null destination for local_exit or unknown departure. Intent/preparation/attempt
remain incomplete; a named destination alone does not assert arrival. Existing IDs
remain available. Preserve agency, companions, conversation, Knowledge and time.
'''


def project(messages):
    out=deepcopy(messages)
    def walk(value):
        if isinstance(value,dict):
            props=value.get('properties',{})
            if props.get('kind',{}).get('const')=='movement' and 'endpoint' in props:
                props.pop('endpoint');props['destination']=deepcopy(DESTINATION)
                value['required']=[k for k in value.get('required',[]) if k!='endpoint']
                value['allOf']=[
                    {'if':{'properties':{'assertion':{'enum':['departure','local_exit']}}},'then':{'properties':{'destination':{'type':'null'}}}},
                    {'if':{'properties':{'assertion':{'const':'completed_arrival'}}},'then':{'required':['destination'],'properties':{'destination':{'type':'object'}}}},
                ]
            for child in value.values():walk(child)
        elif isinstance(value,list):
            for child in value:walk(child)
    for message in out:
        if message['content'].startswith('JSON Schema\n'):
            schema=json.loads(message['content'].split('\n',1)[1]);walk(schema)
            message['content']='JSON Schema\n'+json.dumps(schema,ensure_ascii=False,separators=(',',':'))
    # Remove superseded interface instructions, without changing domain rules.
    out[0]['content']=out[0]['content'].replace('A new reached shore may be declared in locations;', 'A new reached place may be declared in destination;').replace('endpoint','destination')+INSTRUCTION
    return out


def adapt(payload,before,turn_id,namespace=None):
    out=deepcopy(payload)
    errors=[]
    for index,step in enumerate(out['scene_steps']):
        if not isinstance(step,dict) or step.get('kind')!='movement':continue
        def error(reason):errors.append(StructuralDeltaError(reason,code='experimental_destination_invalid',section='scene_steps',index=index,field='destination',entity=step.get('id')))
        if 'endpoint' in step:error('Experimental D uses destination, not a second endpoint.');continue
        value=step.pop('destination',None)
        if list(Draft202012Validator(DESTINATION).iter_errors(value)):
            error('Use null, {existing_id}, or {name,anchor_id,relation}.');continue
        if value is None:step['endpoint']=None;continue
        if 'existing_id' in value:step['endpoint']=value['existing_id'];continue
        anchor=before['locations'].get(value['anchor_id'])
        if anchor is None:error('New destination must reference a known canonical anchor_id.');continue
        identity=json.dumps([namespace,turn_id,step.get('id'),'destination'],ensure_ascii=False)
        lid='destination_'+hashlib.sha256(identity.encode()).hexdigest()[:20]
        location=dict(id=lid,name=value['name'],description=value['relation']+'; ориентир: '+anchor['name'])
        if lid in before['locations']:error('Generated destination identity already exists; reference its existing_id.');continue
        if any(x.get('id')==lid for x in out.get('locations',[])):error('Do not duplicate this destination in locations.');continue
        out.setdefault('locations',[]).append(location);step['endpoint']=lid
    if errors:raise StructuralDeltaError.combine(errors)
    return out


class DestinationCandidate(SceneCandidate):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.binding=digest([self.binding,'issue257-D-prototype'])

    def _parse(self,payload,*,defer_errors=False):
        value=self.apply(payload) if self.scope is not None else decode(payload)
        ids=[s.get('id') for s in value['scene_steps'] if isinstance(s,dict)]
        self.base=deepcopy(value) if len(ids)==len(value['scene_steps']) and all(isinstance(i,str) and i for i in ids) and len(set(ids))==len(ids) else None
        compiled=adapt(value,self.before,self.turn_id,self.namespace)
        self.raw=compile_scene(compiled,self.before,self.narrative,self.turn_id,namespace=self.namespace,version=7,defer_errors=defer_errors)
        self.raw.warnings.extend(self.revisions)
        return self.raw
