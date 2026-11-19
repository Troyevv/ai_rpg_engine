"""Offline provider replies for the Stage C Knowledge rejection (#222)."""

QUESTION = 'Вера, во сколько завтра встретимся в библиотеке?'
CONSENT = 'Я согласен прийти завтра в библиотеку в 15:00. Спрашиваю Веру, подходит ли ей именно это время.'


def meeting_reply(action, camera=None):
    agreed = action == CONSENT
    text = ('Вера кивает: «Да, завтра в библиотеке в три».' if agreed else
            'Вера предлагает Кириллу встретиться завтра в библиотеке в 15:00 и ждёт ответа.')
    if camera is None:
        return text
    actors = ['qa_kirill', 'qa_vera']
    plan = dict(id='sched_vera_meeting', description='Встреча в библиотеке', character_ids=actors,
                assertion='agreed', decision_actor_id='qa_vera', source_event_id='offer',
                temporal=dict(day_offset=1, time='15:00'), evidence=text)
    if agreed:
        plan.update(player_assertion='explicit_choice', player_evidence=action)
    return dict(player_agency=dict(status='preserved', actions=[], narrative_audit=[]), final_scene=dict(location_id=camera['location_id'],
                                 present_character_ids=camera['present_character_ids'], elapsed_minutes=1),
                events=[dict(id='offer', text=text, participants=actors, witnesses=actors, evidence=text)],
                scheduled_event_changes=[plan])
