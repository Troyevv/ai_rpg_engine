"""Split the existing workshop fixture across real validated generation stages."""
import re
from backend.services.initial_world_v2 import normalize
from backend.services.initial_world_stages import LifePart
from test_draft_world import fixture


def staged_result(stage,data):
    snapshot=normalize(fixture()).snapshot
    state=snapshot['world_state'];cards=snapshot['character_cards']
    if stage=='interpret':return {'entities':[],'claims':[]}
    if stage=='setting':return dict(campaign={'title':'Вечер в общем доме'},entities=[
        dict(key=cid,kind='character',name=a['display_name'],tier='protagonist' if cid==state['meta']['current_protagonist_id'] else 'core') for cid,a in state['characters'].items()]+[
        dict(key=lid,kind='location',name=p['name']) for lid,p in state['locations'].items()])
    registry=data['registry']
    ids={old:next(r['id'] for r in registry if r['name']==a['display_name'] and r['kind']=='character') for old,a in state['characters'].items()}
    ids.update({old:next(r['id'] for r in registry if r['name']==p['name'] and r['kind']=='location') for old,p in state['locations'].items()})
    def remap(v):
        if isinstance(v,str):return re.sub('|'.join(re.escape(k) for k in ids),lambda m:ids[m[0]],v)
        if isinstance(v,list):return [remap(x) for x in v]
        if isinstance(v,dict):return {remap(k):remap(x) for k,x in v.items()}
        return v
    state=remap(state);cards=remap(cards)
    if stage=='places':return dict(locations=state['locations'],organizations=state['organizations'])
    if stage=='characters':return dict(characters={cid:state['characters'][cid] for cid in data['assigned_ids']},cards={c['id']:{k:c[k] for k in ('id','name','fields')} for c in cards if c['id'] in data['assigned_ids']})
    if stage=='life':return {k:state[k] for k in LifePart.model_fields}
    if stage=='lore':return {k:state[k] for k in ('facts','knowledge','threads')}
    if stage=='opening':return dict(world_time=state['meta']['world_time'],calendar=state['meta']['calendar'],camera=state['camera'],scheduled_events=state['scheduled_events'])
    raise AssertionError(stage)
