"""Offline full-request measurements; estimates are not provider usage or bills.

Run from the repository root: python scripts/measure_creative_context.py
Uses historical provider canon and the existing controlled scenario/cast fixtures.
"""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import sys
from time import perf_counter

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from backend.services import draft_creative
from backend.services.draft_generation import messages_for as generation_messages

def messages_for(repo,job,config):
    config=dict(config,_prompts={'draft_world_prompt.md':{'content':(ROOT/'prompts/draft_world_prompt.md').read_text()}})
    return generation_messages(repo,job,config)
from backend.services.draft_response import stage_output_limit
from backend.services.usage import price_snapshot
from context_builder import estimate
from test_generation_scenarios import SCENARIOS, controlled_world
from test_initial_draft_v4 import rich


def measure(name,state,source):
    started=perf_counter();request=draft_creative.messages(state,source);elapsed=(perf_counter()-started)*1000
    config=dict(provider='deepseek',model='deepseek-flash',max_tokens=24000)
    bound=estimate(request)+512;output=stage_output_limit('creative_measure',request,config)
    rate=price_snapshot(config,datetime(2026,11,2,2,tzinfo=timezone.utc))
    cost=(bound*Decimal(rate['input'])+output*Decimal(rate['output']))/1000000
    return dict(world=name,characters=len(state['characters']),request_bytes=sum(len(m['content'].encode()) for m in request),
                input_bound=bound,output_ceiling=output,minimum_context=bound+256,
                full_output_context=bound+output,build_ms=round(elapsed,2),
                uncached_reservation_usd=str(cost),tariff_snapshot=rate['version'])


def main():
    rows=[]
    for scenario in SCENARIOS:
        state=controlled_world(scenario)
        config=dict(_draft_task='world',_draft_source=scenario['idea'],_creation_settings=dict(scenario.get('settings',{}),calendar_start=scenario['start']))
        source=messages_for(None,{'workspace_id':'measure'},config)[-1]['content']
        rows.append(measure(scenario['id'],state,source))
    evidence=json.loads((ROOT/'tests/fixtures/initial_world/generation_response_final.json').read_text())
    rows.append(measure('historical_real_DeepSeek',evidence['candidate_snapshot'],json.dumps(evidence['author_input'],ensure_ascii=False)))
    for count in (36,56):
        state=rich();template=deepcopy(state['characters'][1]);actor=deepcopy(state['world']['characters'][template['id']])
        while len(state['characters'])<count:
            cid='extra_'+str(len(state['characters']));card=deepcopy(template);card.update(id=cid,name='Житель '+cid,aliases=[])
            state['characters'].append(card);state['world']['characters'][cid]=dict(deepcopy(actor),id=cid)
        source=messages_for(None,{'workspace_id':'measure'},dict(_draft_task='world',_draft_source='Город ремесленников.',_creation_settings=dict(cast_preset='large') if count==36 else dict(cast_preset='custom',core_npcs=15,secondary_npcs=40)))[-1]['content']
        rows.append(measure('cast_'+str(count),state,source))
    print(json.dumps(rows,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
