"""Deterministic external provider fixture shared by API and Chromium acceptance."""
import json

FIRST = 'Олег, фотографии карты готовы. Покажешь альбом?'
QUESTION = 'Покажу завтра. Кирилл, ты придёшь?'
ANSWER = 'Нет, завтра не приду.'
HELLO = 'Привет всем! Как ваши дела?'
ARRIVAL_REQUEST = 'Привет, как у вас дела?'
LONG_REQUEST = 'Расскажи подробнее про фотографии.'
LONG_REPLY = '\n\n'.join(f'Фотография {i}: мы обсуждали свет, цвета и старые воспоминания. ' * 4 for i in range(1, 13))
ACCEPT = 'Да, Олег, завтра приду.'
CONTINUED = 'Тогда обсудим фотографии вдвоём.'


def response(messages, structured=False):
    system = messages[0]['content']
    if system.startswith('Group communication reaction/'):
        data=json.loads(messages[1]['content']);source=data['source_message']
        texts=([CONTINUED,'Хорошо, Тимур, обсудим альбом.','Отлично.'] if source['content']==ANSWER else
               ['Привет! Фотографии готовы.','Тимур, здорово! Покажешь потом?','Да, Олег, покажу.'] if source['content']==HELLO else
               ['Хорошо, Кирилл. Встреча завтра в силе.','Олег, я передам альбом.','Спасибо, Тимур.'])
        speakers = ['qa_timur','qa_oleg','qa_timur']
        if source['content'] == ARRIVAL_REQUEST:
            texts = ['Привет! Сегодня разбираю фотографии.', 'Тимур, а альбом уже готов?', 'Олег, он ещё выбирает снимки.']
            speakers = ['qa_timur','qa_oleg','qa_vera']
        if source['content'] == LONG_REQUEST:
            texts = [LONG_REPLY, 'Тимур, мне особенно понравилась третья фотография.', 'Да, Олег, у неё интересная история.']
        return json.dumps(dict(messages=[dict(actor_id=a,content=t,basis_ids=[source['id']],read_previous=i>0)
            for i,(a,t) in enumerate(zip(speakers,texts))]),ensure_ascii=False)
    if system.startswith('Group response extraction/'):

        data=json.loads(messages[1]['content'])
        requests=[dict(message_index=i,target_id=data['controlled_actor_id'], evidence=QUESTION,
            expires_at=data['world_time']+180) for i,m in enumerate(data['series']['messages']) if m['content']==QUESTION]
        return json.dumps(dict(requests=requests),ensure_ascii=False)
    if system.startswith('Select at most ONE'):
        data=json.loads(messages[1]['content'])
        if data.get('groups'):
            group=data['groups'][0]
            answered=any(ANSWER in h['content'] for a in group['actors'] for h in a['history'])
            basis=group['basis']['qa_timur']
            return json.dumps(dict(action=None,group_series=dict(conversation_id=group['conversation_id'],messages=[
                dict(actor_id='qa_timur',content=CONTINUED if answered else FIRST,basis_ids=basis),
                dict(actor_id='qa_oleg',content='Договорились, возьму альбом.' if answered else QUESTION,
                     basis_ids=basis,read_previous=True),
                dict(actor_id='qa_timur',content='Отлично.',basis_ids=basis,read_previous=True)])),ensure_ascii=False)
        option=next((o for o in data['options'] if 'read' in o['actions']),None)
        return json.dumps(dict(action=dict(actor_id=option['actor_id'],action='read',event_id=option['event_id'],basis_ids=option['basis_ids']) if option else None))
    if system.startswith('Remote semantic extraction/'):
        data=json.loads(messages[1]['content'])
        value=dict(final_scene=data['final_scene'])
        answers=[e for e in data['accepted_messages'] if e['content'] in (ANSWER,ACCEPT) and e['sender_id']==data['controlled_actor_id']]
        if answers:
            value['group_response_changes']=[dict(request_event_id=r['event_id'],response_event_id=answers[-1]['id'],
                assertion='refused' if answers[-1]['content']==ANSWER else 'answered',evidence=answers[-1]['content']) for r in data.get('pending_group_requests',[]) if not r['resolved_by']]
        proposal=next((e for e in data['accepted_messages'] if e['content']==QUESTION),None)
        assent=next((e for e in answers if e['content']==ACCEPT),None)
        if proposal and assent and 'scheduled_event_changes' in data['schema']['properties']:
            value['scheduled_event_changes']=[dict(id='group152-meeting',description='Посмотреть альбом завтра',
                assertion='agreed',character_ids=[proposal['sender_id'],assent['sender_id']],
                temporal=dict(day_offset=1),location_id=None,evidence=assent['content'],
                remote_source_ids=[proposal['id'],assent['id']],remote_time_source_id=proposal['id'],
                player_assertion='explicit_choice',player_source_id=assent['id'],player_evidence=assent['content'])]
        return json.dumps(value,ensure_ascii=False)
    current=json.loads(next(m['content'].split('\n',1)[1] for m in messages if m['content'].startswith('Текущее состояние / GM-only\n')))
    if not structured:
        return 'За окном шёл дождь. В комнате было тихо.'
    camera=current['camera']
    return json.dumps(dict(final_scene=dict(location_id=camera['location_id'],
        present_character_ids=camera['present_character_ids'],elapsed_minutes=0 if any('Фоновая симуляция:' in m['content'] for m in messages) else 31),
        choices=[dict(action='Посмотреть в окно',speech=''),dict(action='Рассмотреть карту',speech='')]),ensure_ascii=False)
