"""Controlled provider responses for #122. Test scenarios, not production NLP."""
def extract(data):
    result = dict(final_scene=data['final_scene'])
    rows = data['accepted_messages']
    proposals = [e for e in rows if 'через два часа' in e['content']]
    if proposals:
        proposal = proposals[-1]
        replies = [e for e in rows if e['sender_id'] != proposal['sender_id'] and e['ordinal'] > proposal['ordinal'] and e['content'].startswith('Да')]
        if replies:
            reply = replies[0]
            result['scheduled_event_changes'] = [dict(id='phone-meeting',description='Встреча по договорённости',
                character_ids=[proposal['sender_id'], reply['sender_id']],assertion='agreed',temporal=dict(minute_offset=120),
                evidence=reply['content'],remote_source_ids=[proposal['id'],reply['id']],remote_time_source_id=proposal['id'],
                player_assertion='explicit_choice',player_evidence=proposal['content'],interrupts=True)]
    authored = [e for e in rows if e['sender_id']==data['controlled_actor_id'] and e['content'].startswith('Я планирую')]
    if authored:
        e=authored[-1]
        result['character_changes']=[dict(id=e['sender_id'],evidence=e['content'],intentions_updates=[dict(
            text=e['content'],status='active',evidence=e['content'],source_event_id=e['id'],
            player_assertion='explicit_choice',player_evidence=e['content'])])]
    return result
