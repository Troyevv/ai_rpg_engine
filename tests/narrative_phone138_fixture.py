"""Semantic LLM fixture only; never writes state or calls Runtime itself."""
from copy import deepcopy
from call_continuity_fixture import response as call_response

TEXT='Ты завтра свободен?'
MESSAGE_ACTION='Посмотреть на дождь.'
CALL_ACTION='Поставить чашку на стол.'
PROSE='За окном шумит дождь. Телефон завибрировал: Катя написала «Ты завтра свободен?».'


def response(current, task, extraction=False):
    text=task['player_input'];camera=current['camera'];comm=current['communication']
    if comm.get('focus')=='call':
        return call_response(current,text,'complete' if extraction else None)
    prose='Илья сидит в кабинете. За окном шумит дождь.'
    rows=[]
    if text==MESSAGE_ACTION:
        prose=PROSE
        rows=[dict(sender_id='qa_vera',recipient_ids=['qa_kirill'],channel='TEXT_MESSAGE',content=TEXT)]
    elif text==CALL_ACTION:
        prose='На экране телефона появляется входящий звонок от Кати.'
        rows=[dict(sender_id='qa_vera',recipient_ids=['qa_kirill'],channel='VOICE_CALL')]
    if not extraction:return prose
    return dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids'],elapsed_minutes=1),
        remote_events=rows,choices=[dict(action='Посмотреть в окно',speech='')])
