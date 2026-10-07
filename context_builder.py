"""Named, bounded prompt blocks. Saved verbatim for reproducible regeneration."""
import json
from pathlib import Path

PROMPTS = Path(__file__).resolve().parent / 'prompts'


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def estimate(messages):
    # Conservative multilingual UTF-8 estimate, not a provider tokenizer.
    return sum((len(m['content'].encode('utf-8'))+1)//2+32 for m in messages)+256


def describe_context(messages):
    parts = []
    for i,m in enumerate(messages):
        title = m['content'].split('\n',1)[0]
        if len(title)>100:
            title = 'Сообщение ' + str(i+1)
        parts.append({'name':title,'role':m['role'],'estimated_tokens':estimate([m])-256,'content':m['content']})
    return {'parts':parts,'overhead_tokens':256,'estimated_tokens':estimate(messages),
            'selection':getattr(messages, 'selection', None),
            'token_method':'Оценка UTF-8, не точный токенизатор. Фактический input — из usage API.'}


def build_context(state, history, user_text, kind, context_length, reserve, extraction_text=None,
                  validation_feedback=None, recent_turns=6, prompts=None, world_history=None, target_context_budget=18000):
    from backend.runtime_v3.context import build_context as build_v3
    if state.get('schema_version') != 3:
        # Explicit read-only draft preview boundary. Saved runtime jobs enter as v3.
        from backend.runtime_v3.migration import migrate_v2
        state = migrate_v2(state).snapshot
    return build_v3(state, history, user_text, kind, context_length, reserve,
                    extraction_text, validation_feedback, recent_turns, prompts, world_history, target_context_budget)
