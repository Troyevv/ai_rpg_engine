"""Disposable, bounded history selection; canonical state is never copied into memory."""
import json


class HistorySelector:
    def __init__(self, state, history):
        self.state, self.history = state, history or {}

    def select(self, actor_id, scene_id, involved_actor_ids, active_thread_ids, token_budget):
        # Backward-compatible signature; one ranking algorithm for every caller.
        from backend.runtime_v3.scope import ContextScope
        scope = ContextScope(actor_id, present_actor_ids=set(involved_actor_ids),
                             location_ids=[scene_id] if scene_id else [], thread_ids=list(active_thread_ids))
        return self.select_scope(scope, token_budget)

    def select_scope(self, scope, token_budget):
        """Scene causes outrank protagonist participation; age weakens incidental links."""
        from backend.runtime_v3.scope import words, string_ids
        ranked = []
        events = self.history.get('events', [])
        now = self.state['meta']['turn_id']
        core = scope.present_actor_ids | scope.remote_actor_ids | scope.active_actor_ids
        selected_facts = set(scope.fact_ids)
        for index, event in enumerate(events):
            if not isinstance(event, dict) or not isinstance(event.get('text'), str): continue
            participants = event.get('participants', [])
            if not isinstance(participants, list) or any(not isinstance(cid, str) for cid in participants): continue
            ids = set(participants)
            turn = event.get('turn_id')
            age = max(0, now-turn) if type(turn) is int else len(events)-index-1
            score = 100*bool(words(event['text']) & scope.query_words)
            score += 100*scope.semantic_scores.get(('history_events', event.get('id')), 0)
            score += 60*bool(string_ids(event.get('fact_ids')) & selected_facts)
            score += 40*bool(ids & (scope.structural_actor_ids - core))
            score += 50*bool(event.get('thread_id') in scope.thread_ids)
            if age < 3:
                score += (60, 30, 10)[age]*bool(ids & core)
                score += (40, 20, 5)[age]*bool(event.get('location_id') in scope.location_ids)
            if score: ranked.append((score, index, event))
        selected, used = [], 0
        for _, index, event in sorted(ranked, key=lambda row: (-row[0], -row[1])):
            cost = (len(json.dumps(event, ensure_ascii=False).encode())+1)//2 + 4
            if used + cost > max(0, token_budget-36): continue
            selected.append((index, event)); used += cost
            if len(selected) == 16: break
        return [event for _, event in sorted(selected)]
