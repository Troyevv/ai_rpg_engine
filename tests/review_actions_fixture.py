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
    if 'response_schema' in data and data['author_context']['original_idea'].startswith(FAMILY_SOURCE):
        fn=direct_family_reply if data['author_context']['original_idea'].endswith('direct-family') else family_reply
        return json.dumps(fn(data),ensure_ascii=False)
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
            changes[-1]['path']='/world_clock/minute'
        return json.dumps(dict(candidate_hash=candidate_hash(data['candidate']),rationale='Уточнить карточку Марины по замыслу автора.',
                          changes=changes,decisions=decisions),ensure_ascii=False)
    return json.dumps(dict(issues=[],decisions=decisions),ensure_ascii=False)


FAMILY_SOURCE = ('Сегодня у Ильи день рождения. Илье 30 лет. Мёрфи родилась в 2015 году. '
                 'Лиза умерла при родах в 19 лет. Лиза родилась в 1996 году.')


def seed_family(repo, *, both_nineteen=False, scenario=''):
    state=candidate()
    ids=[c['id'] for c in state['characters'][:3]]
    father,child,mother=ids
    clock=state['world_clock']['calendar']
    clock.update(start_date='2026-07-10',start_weekday=4)
    ledger=state.setdefault('authoring',{}).setdefault('calendar_completion',{}).setdefault('birth_dates',{})
    for card,name,age,day in zip(state['characters'],('Илья','Мёрфи','Лиза'),('30','11','19'),
                                 ('1995-11-27','2014-09-27','1996-11-30')):
        cid=card['id'];card.update(name=name)
        card['fields']['Возраст']=age
        state['world']['characters'][cid].update(birth_date=day,birth_date_provenance={'source':'authoring_automatic'},
                                               life_status='dead' if cid==mother else 'alive')
        ledger[cid]=dict(source='automatic',value=day)
    state['world']['characters'][mother]['scene_id']=None
    for scene in state['world']['scenes'].values():
        scene['participants']=[cid for cid in scene['participants'] if cid!=mother]
    rels=state['world']['objective_relations']={}
    state['world']['events']['delivery']=dict(id='delivery',text='Лиза умерла при родах в 19 лет.',
        participants=[mother,child],witnesses=[],minute=None,scene_id=None,fact_ids=[],player_observed=False)
    for parent in (father,mother):
        key='parent_'+parent
        rels[key]=dict(id=key,kind='parent',source_id=parent,target_id=child)
    rels['old_marriage']=dict(id='old_marriage',kind='spouse',source_id=father,target_id=mother,
            status='closed',outcome='widowed',since_date='2014-01-01',until_date='2015-01-01',
            context='Точные даты брака и смерти условны.')
    idea=FAMILY_SOURCE+(' Илье при рождении дочери было 19 лет.' if both_nineteen else '')
    if scenario:idea+=' '+scenario
    wid=repo.create_workspace('Семейная хронология')['id']
    with repo.connect() as db:
        repo._write_draft(db,wid,state,'draft_world',source=idea,review=dict(status='completed',
            advisory=True,issues=[dict(message='Уточнить хронологию семьи.',severity='warning')]))
    return {'wid':wid}


def family_reply(payload):
    father,child,mother=[c['id'] for c in payload['candidate']['characters'][:3]]
    parents=[dict(actor_id=mother,quote='Лиза умерла при родах в 19 лет',age=19,died_at_birth=True,
                  birth_year=1996,birth_year_quote='Лиза родилась в 1996 году')]
    if 'Илье при рождении дочери' in payload['author_context']['original_idea']:
        parents.append(dict(actor_id=father,quote='Илье при рождении дочери было 19 лет',age=19))
    year=dict(kind='creative_year',year=2015,quote='Мёрфи родилась в 2015 году',preferred_date='2015-06-12',parents=parents,
              event_ids=['delivery'],conditional_marriages=[dict(relation_id='old_marriage',quote='Точные даты брака и смерти условны.')])
    birthday=dict(kind='birthday_at_start',quote='Сегодня у Ильи день рождения',age_quote='Илье 30 лет')
    return dict(candidate_hash=payload['candidate_hash'],rationale='Согласовать рождение и семейную историю.',
                changes=[dict(change('/world/characters/'+cid+'/birth_date',None,'replace'),date_basis=basis)
                         for cid,basis in [(child,year),(father,birthday)]],
                decisions=[dict(issue_id=payload['findings'][0]['issue_id'],reason='Общая дата для связанных записей.',
                                outcome='proposed',change_indices=[0,1])])


def direct_family_reply(data):
    father,child,mother=[c['id'] for c in data['candidate']['characters'][:3]]
    day='2015-06-15'
    def field(cid,key,value,detail,op='replace'):
        return dict(op=op,path=f'/world/characters/{cid}/{key}',value=value,detail=detail)
    changes=[field(child,'birth_date',day,'new_detail'),field(father,'birth_date','1996-07-10','author_fact'),
             field(mother,'birth_date','1996-03-23','new_detail'),field(mother,'death_date',day,'new_detail','add'),
             dict(op='replace',path='/world/objective_relations/old_marriage/until_date',value=day),
             dict(op='replace',path='/world/events/delivery/text',value='15 июня Лиза умерла при родах Мёрфи.')]
    return dict(candidate_hash=data['candidate_hash'],changes=changes,
                conflicts=['При выбранной дате Илье 18. Если обоим родителям должно быть 19, возможен день 10 июля.'],
                rationale='День рождения Мёрфи предложен моделью. Лизе при родах было 19 лет.')


def legacy_year_packet(payload):
    packet=family_reply(payload)
    basis=packet['changes'][0]['date_basis']
    packet['changes'][0]['date_basis']=dict(kind='year_only',year=basis['year'],quote=basis['quote'])
    return packet


def legacy_year_result(edit,raw):
    from copy import deepcopy
    from backend.services.draft_editor import differences
    packet=json.loads(raw)
    trial=deepcopy(edit['base']['state'])
    father,child=[card['id'] for card in trial['characters'][:2]]
    trial['world']['characters'][child]['birth_date']=None
    trial['world']['characters'][father]['birth_date']='1996-07-10'
    notes=[dict(edit['findings'][0],**packet['decisions'][0])]
    changes=[{k:v for k,v in c.items() if k!='date_basis'} for c in packet['changes']]
    changes[1]['value']='1996-07-10'
    return dict(status='preview',candidate=trial,outcomes=notes,diff=differences(edit['base']['state'],trial),
                proposal=dict(candidate_hash=edit['before_hash'],changes=changes,rationale=packet['rationale']),
                calendar_decisions={child:dict(value=None,known_year=2015,source='unknown'),
                                    father:dict(value='1996-07-10',source='explicit')})


def seed_legacy_family(repo):
    from backend.services.draft_response import digest
    from backend.services.draft_review_actions import response_key
    from test_api import REMOTE
    wid=seed_family(repo)['wid']
    base=repo.draft(wid,True)
    cfg=dict(REMOTE,_draft_input='Исправить замечания с помощью ИИ',_editor_request_id='old',_review_action='fix')
    jid=repo.begin_preparation(wid,'draft_editor','',cfg,base['revision'])
    journal=json.loads(repo.preparation_job(jid)['response_journal'])
    edit=journal['editor']
    packet=legacy_year_packet(dict(candidate=edit['base']['state'],candidate_hash=edit['before_hash'],findings=edit['findings'],
                                  author_context=dict(original_idea=edit['base']['source'])))
    raw=json.dumps(packet)
    journal['responses']={response_key(edit):dict(complete=True,parts=[dict(text=raw,sha256=digest(raw),offset=0,request_id='archived')])}
    repo.save_response_journal(jid,journal)
    repo.finish_review_action(jid,0,legacy_year_result(edit,raw))
    return dict(wid=wid)
