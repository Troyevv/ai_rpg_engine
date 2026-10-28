"""Controlled multi-turn provider. Shared by real API and browser regressions."""
OFFER='Встретимся через час?'
ASSENT='Да, договорились.'
KNOCK='Виктория трижды стучит в дверь кабинета. Деревянная створка глухо отзывается.'
DEMAND='За дверью Виктория повышает голос: «Илья, выходи, мне нужен ответ!»'
END='Катя заканчивает разговор; в трубке щёлкает отбой.'
BEFORE='Илья сидит в кабинете. Виктория ждёт за дверью и пока не стучит.'
AFTER='За дверью всё ещё ждёт Виктория. После её стука и требования ответа в кабинете повисла тишина.'


def response(current, text, narrative=None):
    comm=current['communication'];camera=current['camera']
    source_rows=comm.get('call_sources',[])
    actor=camera['controlled_actor_id'];npc=next((a for a in comm['participants'] if a!=actor),'qa_vera')
    physical=KNOCK if text==OFFER else DEMAND if text=='Я скоро освобожусь.' else ''
    ending=text=='Тогда до встречи.'
    prose=('Катя отвечает: «'+ASSENT+'».' if text==OFFER else END if ending else 'Катя говорит: «Я тебя слышу».')
    if text=='До свидания.':prose='Катя говорит: «До свидания, ещё созвонимся».'
    if text=='Может, встретимся?':prose='Катя отвечает: «Я пока не знаю, подумаю».'
    if text=='Что предлагаешь?':prose='Катя предлагает: «Давай встретимся через час».'
    if text=='Перенесём на два часа?':prose='Катя отвечает: «Да, перенесём на два часа».'
    if text=='Отменяем встречу.':prose='Катя отвечает: «Хорошо, встреча отменена».'
    if physical:prose+='\n\n'+physical
    if narrative is None:return prose
    result=dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids'],elapsed_minutes=2),choices=[])
    if physical:
        result['events']=[dict(id='outside',text='Стук в дверь.' if text==OFFER else 'Виктория требует ответа.',evidence=physical,
            participants=[actor,'qa_marina'],witnesses=[actor],medium='observation',interaction_channel='physical')]
        result['physical_projections']=[dict(event_id='outside',text=physical)]
        result['choices']=[dict(action='Подойти к двери и ответить Виктории',speech='',interaction_channel='physical'),dict(action='Выйти из кабинета',speech='',interaction_channel='physical')]
        result['final_scene'].update(situation=physical,situation_evidence=physical)
    if ending:result['call_lifecycle_changes']=[dict(call_id=comm['active_call'],actor_id=npc,assertion='completed_end',evidence=END)]
    # Deliberately defer agreement until a later turn: current player input is
    # no longer the proposal. Sources and exact original time must survive.
    if ending:
        proposal=next(r for r in source_rows if r['role']=='player' and r['content']==OFFER)
        reply=next(r for r in source_rows if r['role']=='narrative' and ASSENT in r['content'])
        result['scheduled_event_changes']=[dict(id='office-meeting',description='Встреча с Катей',character_ids=[actor,npc],
            assertion='agreed',temporal={'minute_offset':60},evidence=ASSENT,player_assertion='explicit_choice',player_evidence=OFFER,player_source_id=proposal['id'],call_time_source_id=proposal['id'],
            call_evidence=[dict(source_id=proposal['id'],actor_id=actor,quote=OFFER,assertion='proposal'),dict(source_id=reply['id'],actor_id=npc,quote=ASSENT,assertion='assent')])]
    if text=='Да, согласен.':
        proposal=next(r for r in source_rows if r['role']=='narrative' and 'Давай встретимся через час' in r['content'])
        reply=next(r for r in source_rows if r['role']=='player' and r['content']==text)
        result['scheduled_event_changes']=[dict(id='office-meeting',description='Встреча с Катей',character_ids=[actor,npc],
            assertion='agreed',temporal={'minute_offset':60},evidence=text,player_assertion='explicit_choice',player_evidence=text,player_source_id=reply['id'],call_time_source_id=proposal['id'],
            call_evidence=[dict(source_id=proposal['id'],actor_id=npc,quote='Давай встретимся через час',assertion='proposal'),dict(source_id=reply['id'],actor_id=actor,quote=text,assertion='assent')])]
    if text=='Перенесём на два часа?':
        proposal=next(r for r in source_rows if r['role']=='player' and r['content']==text)
        reply=next(r for r in source_rows if r['role']=='narrative' and 'Да, перенесём на два часа' in r['content'])
        result['scheduled_event_changes']=[dict(id='office-meeting',assertion='rescheduled',temporal={'minute_offset':120},
            evidence='Да, перенесём на два часа',player_assertion='explicit_choice',player_evidence=text,player_source_id=proposal['id'],call_time_source_id=proposal['id'],
            call_evidence=[dict(source_id=proposal['id'],actor_id=actor,quote=text,assertion='proposal'),dict(source_id=reply['id'],actor_id=npc,quote='Да, перенесём на два часа',assertion='assent')])]
    if text=='Отменяем встречу.':
        source=next(r for r in source_rows if r['role']=='player' and r['content']==text)
        result['scheduled_event_changes']=[dict(id='office-meeting',assertion='cancelled',evidence=text,
            player_assertion='explicit_choice',player_evidence=text,player_source_id=source['id'],
            call_evidence=[dict(source_id=source['id'],actor_id=actor,quote=text,assertion='cancellation')])]
    return result
