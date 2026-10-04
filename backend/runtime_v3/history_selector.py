"""Disposable, bounded history selection; canonical state is never copied into memory."""
import json


class HistorySelector:
    def __init__(self, state, history):
        self.state, self.history = state, history or {}

    def select(self, actor_id, scene_id, involved_actor_ids, active_thread_ids, token_budget):
        involved = set(involved_actor_ids)
        thread_actors = {cid for tid in active_thread_ids for cid in self.state['threads'].get(tid, {}).get('character_ids', [])}
        pending_actors = {cid for cid, c in self.state['characters'].items()
                          if any(isinstance(o,dict) and o.get('status')=='active' for o in c['obligations'])}
        ranked = []
        for index, event in enumerate(self.history.get('events', [])):
            if not isinstance(event,dict) or not isinstance(event.get('text'),str): continue
            participants = event.get('participants', [])
            if not isinstance(participants,list) or any(not isinstance(x,str) for x in participants): continue
            ids = set(participants)
            score = 100*bool(scene_id and event.get('location_id')==scene_id)+80*bool(actor_id and actor_id in ids)
            score += 40*bool(ids & involved)+30*bool(ids & thread_actors)+20*bool(ids & pending_actors)
            if not score: continue
            ranked.append((score,index,event))
        selected, used = [], 0
        # Include JSON array framing and message overhead in the caller's budget.
        for _,index,event in sorted(ranked,key=lambda x:(-x[0],-x[1])):
            cost = (len(json.dumps(event,ensure_ascii=False,separators=(',',':')).encode())+1)//2+4
            if used+cost>max(0,token_budget-36): continue
            selected.append((index,event));used+=cost
        return [event for _,event in sorted(selected)]
