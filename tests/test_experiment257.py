"""Experimental context projection only; no provider calls or product defaults."""
import json
from copy import deepcopy
from devtools.issue257.prepare import compact


def test_projection_preserves_private_boundary_and_schema():
    state={'facts':{'secret':{'text':'Private'}},'characters':{'a':{'goals':[{'text':'A long meaningful goal repeated in both contexts, with all original content retained.'}]}}}
    choice={'enabled':True,'actor_id':'a','goals':deepcopy(state['characters']['a']['goals']),'knowledge':[]}
    messages=[{'role':'system','content':'Rules'},*({'role':'user','content':title+'\n'+json.dumps(value)} for title,value in [('Текущее состояние / GM-only',state),('Choice context / controlled actor',choice),('JSON Schema',{'type':'object','properties':{}}),('completed_narrative','Unchanged prose')])]
    before=deepcopy(messages);out=compact(messages)
    projected=json.loads(out[2]['content'].split('\n',1)[1])
    def expand(v):
        if isinstance(v,dict) and set(v)=={'state_ref'}:
            value=state
            for part in v['state_ref'].split('/')[1:]:value=value[int(part)] if isinstance(value,list) else value[part.replace('~1','/').replace('~0','~')]
            return value
        if isinstance(v,dict):return {k:expand(x) for k,x in v.items()}
        if isinstance(v,list):return [expand(x) for x in v]
        return v
    assert expand(projected)==choice
    assert projected['knowledge']==[]
    assert messages==before and out[1]==before[1] and out[3:]==before[3:]
