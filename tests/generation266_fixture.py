"""An archived Creative reply with a later user-visible world revision."""
import json
from copy import deepcopy
from backend.repositories.drafts import candidate_hash
from test_draft_creative import candidate, proposal, change


def seed(repo, *, newer=True):
    state=candidate()
    wid=repo.create_workspace('Мастерская у моря')['id']
    jid=repo.begin_preparation(wid,'draft_world','',{'_draft_task':'world','_draft_input':'Соседи восстанавливают мастерскую.'},0)
    repo.save_draft_candidate(jid,state,[],review=dict(status='not_started',issues=[]))
    def packet(base):
        card=base['characters'][1]
        raw=proposal(base,[change('/characters/'+card['id']+'/fields/Внешность','У левого виска светлая прядь.','replace')])+'\n}'
        return dict(status='rejected',before_hash=candidate_hash(base),current_reply=raw,original_reply=raw,
                    validation_version=2,reason='Extra data',correction_complete=True)
    first=packet(state)
    journal={'creative':first,'actual_tokens':790,'actual_cost':'0.001','creative_history':[]}
    if newer:
        edited=deepcopy(state)
        edited['campaign']['title']='Поздняя редакция автора'
        repo.save_draft_candidate(jid,edited,[],review=dict(status='failed',reason='Отчёт не завершён.',issues=[dict(message='Проверьте дату встречи.')]))
        journal.update(creative_history=[first],creative=packet(edited))
    repo.save_response_journal(jid,journal)
    repo.draft_phase(jid,'reviewing')
    repo.preparation_progress(jid,'','error','Отчёт не завершён.')
    return dict(wid=wid,jid=jid,base=first['before_hash'])
