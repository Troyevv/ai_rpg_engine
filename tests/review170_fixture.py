"""Synthetic public fixture; optionally replay a private export locally.

RPG_REVIEW170_EXPORT selects an original export outside the repository. It has
no config_json/messages: High remains an assumption in the reconstructed job.
Never commit private author text or billing exports as regression fixtures.
"""
import json
import os
from pathlib import Path
from backend.services.draft_generation import messages_for


def exported():
    if os.environ.get('RPG_REVIEW170_EXPORT'):
        return json.loads(Path(os.environ['RPG_REVIEW170_EXPORT']).read_text())
    from test_initial_draft_v4 import rich
    from backend.services.draft_response import digest
    state=rich();text=json.dumps(state,ensure_ascii=False)
    def part(value,finish='stop',usage=None):
        return dict(text=value,offset=0,sha256=digest(value),finish_reason=finish,
                    provider_finish_reason=finish,usage=usage)
    usage=dict(prompt_tokens=24032,completion_tokens=10984,
               completion_tokens_details=dict(reasoning_tokens=10984))
    return dict(candidate_snapshot=state,author_input=dict(source_text='TEST_REVIEW170. Соседи разговаривают на кухне.'),
                current_diagnostics=[],requests=[dict(stage='draft_world_validation',finish_reason='length',output_tokens=10984,usage_json=json.dumps(usage)) for _ in range(5)],
                responses={'world':dict(parts=[part(text)],complete=True),
                    'completeness_legacy_review':dict(parts=[part('','length',usage) for _ in range(4)],complete=False),
                    'completeness_older_review':dict(parts=[part('','length',usage)],complete=False)},
                pending=None,errors=[],review_failures=[],review_strategies={},accepted_reviews={},
                reserved_tokens=0,reserved_cost='0',actual_tokens=175080,actual_cost='.03',
                recovery=dict(review=dict(status='failed',issues=[],reason='Пустое продолжение: ответ сохранён, автоматический повтор остановлен.')))


def restore(repo, thinking='high'):
    data=exported();state=data['candidate_snapshot'];source=data['author_input']['source_text']
    w=repo.create_workspace('Issue 170 saved candidate')
    config=dict(provider='deepseek',model='deepseek-flash',thinking=thinking,temperature=.7,
                max_tokens=24000,context_length=65536,_draft_task='world',_draft_input=source,
                _creation_settings=state['creation_settings'],_use_idea=False)
    jid=repo.begin_preparation(w['id'],'draft_world',source,config,0)
    job=repo.preparation_job(jid);config=json.loads(job['config_json'])
    journal={k:data[k] for k in ('responses','pending','errors','review_failures','review_strategies',
             'accepted_reviews','reserved_tokens','reserved_cost','actual_tokens','actual_cost')}
    journal.update(candidate_text=json.dumps(state,ensure_ascii=False),messages=messages_for(repo,job,config))
    repo.save_response_journal(jid,journal)
    repo.save_draft_candidate(jid,state,[],review=data['recovery']['review'])
    repo.preparation_progress(jid,'','error',data['recovery']['review']['reason'])
    return w['id'],jid
