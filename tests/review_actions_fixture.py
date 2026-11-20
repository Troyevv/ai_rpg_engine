"""Offline reviewer with one calendar conflict, one incomplete card and two disputed notes."""
import json
from test_draft_creative import candidate, change
from backend.repositories.drafts import candidate_hash

BIO = 'В биографии реставратора пропущена работа в семейном архиве.'
DEAD = 'У умершего архивиста нет цели.'
UNKNOWN = 'Неизвестна дата закрытия архива.'
SOURCE = 'Марина родилась 2 марта 1990 и работала в семейном архиве. Дата закрытия неизвестна.'
FILLED = 'До отъезда работала реставратором в семейном архиве.'


def seed(repo, scenario=''):
    state = candidate()
    mar = state['characters'][1]
    mar['fields'].update(Возраст='24', Биография='Работала в городе.')
    state['world']['characters'][mar['id']].update(birth_date='1990-03-02',birth_date_provenance={'source':'manual'})
    state['world']['characters'][state['characters'][-1]['id']]['life_status']='dead'
    state.setdefault('authoring',{})['manual_paths']=['/campaign/title','/world/characters/'+mar['id']+'/birth_date']
    wid = repo.create_workspace('Семейный архив')['id']
    with repo.connect() as db:
        repo._write_draft(db,wid,state,'draft_world',source=SOURCE + (' '+scenario if scenario else ''),review=dict(status='completed',
            advisory=True,issues=[dict(message=text,severity='warning') for text in (BIO,DEAD,UNKNOWN)]))
    return {'wid':wid}


def reply(messages):
    data = json.loads(messages[-1]['content'])
    decisions=[];changes=[]
    fix='response_schema' in data
    if fix and data['author_context']['original_idea'].endswith('empty-conflicts'):
        return json.dumps(dict(candidate_hash=data['candidate_hash'], rationale='Источники оставляют точную дату открытой.',
            changes=[], conflicts=['Известен только год рождения.', 'Дата окончания брака условна.'],
            decisions=[dict(issue_id=n['issue_id'],outcome='ambiguous',category='uncertainty',
                reason='Нужна точная дата от автора.') for n in data['findings']]),ensure_ascii=False)
    for issue in data['findings']:
        msg=issue['message']
        if msg == BIO:
            reason='Работа в семейном архиве указана автором.'
            status='proposed' if fix else 'fixed'
            if fix:changes.append(change('/characters/character_2/fields/Биография',FILLED,'replace'))
        elif '/birth_date' in msg:
            reason='На 23 октября 2026 года при дате рождения 2 марта 1990 года Марине 36 лет.'
            status='proposed' if fix else 'fixed'
            if fix:changes.append(change('/characters/character_2/fields/Возраст','36','replace'))
        elif msg==DEAD:
            reason='Архивист умер до начала истории. Текущая цель не требуется.'
            status='disproved'
        else:
            reason='Автор оставил дату неизвестной.'
            status='ambiguous'
        decision=dict(issue_id=issue['issue_id'],outcome=status,reason=reason)
        if status=='proposed':decision['change_indices']=[len(changes)-1]
        decisions.append(decision)
    if fix:
        if data['author_context']['original_idea'].endswith('invalid-write'):
            changes[-1]['path']='/campaign/title'
        return json.dumps(dict(candidate_hash=candidate_hash(data['candidate']),rationale='Уточнить карточку Марины по замыслу автора.',
                          changes=changes,decisions=decisions),ensure_ascii=False)
    return json.dumps(dict(issues=[],decisions=decisions),ensure_ascii=False)
