"""Reproduce assembled prompt estimates from either checkout (run at repository root).

python /absolute/path/to/devtools/measure_extraction136.py > /tmp/prompts.json
Uses synthetic test snapshots; no provider is called. Estimates are not billed tokens.
"""
import json, sys
from pathlib import Path
sys.path[:0]=[str(Path.cwd()),str(Path.cwd()/'tests')]
from test_protagonist import snapshot
from backend.runtime_v3.context import build_context
from context_builder import estimate
from backend.runtime_v3.models import Character
samples={}
for size in (4,124):
 s=snapshot()
 for i in range(size-4):
  cid='extra_'+str(i);s['world_state']['characters'][cid]=Character(id=cid).model_dump()
  s['character_cards'].append(dict(id=cid,name='Персонаж '+str(i),fields={},aliases=[],is_player=False))
 for length in (20,1800):
  narrative='Борис вошёл внутрь. '+('Он молча огляделся. '*length)
  m=build_context(s,[], 'Я жду.', 'turn',131072,4096,extraction_text=narrative)
  samples[f'{size}_actors_{length}_sentences']=dict(estimated_input_tokens=estimate(m),selection=m.selection,character_count=size,narrative_length=len(narrative),messages=m if size==4 and length==20 else None)
from test_remote_communication import phone, command, apply
from copy import deepcopy
active=command(phone(),'call',contact_id='a-b')
call=next(e for e in active['world_state']['remote_events'].values() if e['channel']=='VOICE_CALL')
active,_=apply(active,dict(action='answer',event_id=call['id'],operation_id='measure-answer'),actor_id='b',autonomous=True)
active['world_state']['meta']['interaction_focus']='call'
skip=snapshot();now=skip['world_state']['meta']['world_time']
skip['_time_skip']=dict(actual_target=now+60,elapsed_minutes=60)
for name,current in [('active_phone',active),('time_skip',skip)]:
 narrative='Собеседник ответил. Прошло две минуты.'
 m=build_context(current,[], 'Я жду.', 'turn',131072,4096,extraction_text=narrative)
 samples[name]=dict(estimated_input_tokens=estimate(m),selection=m.selection,narrative_length=len(narrative),messages=m)
print(json.dumps(samples,ensure_ascii=False,indent=2))
