"""Deterministic provider response to a player's ordinary turn at delivery."""
REACTION = 'Я остаюсь рядом с Верой и держу её за руку.'
DELIVERY = 'Вера родила. Врач передал ей ребёнка.'


def delivery_claim(process, camera):
    return dict(events=[dict(id='delivery', text=DELIVERY, evidence=DELIVERY, participants=['qa_vera'],
                             witnesses=['qa_vera', 'qa_kirill'], medium='observation', minute=process['due_minute'])],
                births=[dict(pregnancy_id=process['id'], source_event_id='delivery', assertion='birth_completed',
                             location_id=camera['location_id'], evidence=DELIVERY)])
