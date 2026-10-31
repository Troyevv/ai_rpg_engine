"""Literal Unicode fixtures verify lossless transport, not model style quotas."""
import json
from group152_provider import response as group_response
from test_communication_cycle import decision

MESSAGE = 'Привет! Are you there?.. 👋🏽'
REPLY = 'Да 🙂 / okay... 👩🏽‍💻 ❤️ — e\u0301\n\n' + 'Русский + English; без шаблона!.. ' * 90
DRY = 'Понял. Обсудим позже.'


def response(messages, structured=False):
    system = messages[0]['content']
    if system.startswith('Group communication reaction/'):
        data = json.loads(messages[1]['content'])
        return json.dumps(dict(messages=[dict(actor_id=actor, content=text,
            basis_ids=[data['source_message']['id']], read_previous=i>0)
            for i,(actor,text) in enumerate(zip(data['groups'][0]['actor_ids'], [REPLY,DRY, 'Sounds good… 👍']))]),ensure_ascii=False)
    if system.startswith('Select at most ONE'):
        data = json.loads(messages[1]['content'])
        if not data.get('groups'):
            result = json.loads(decision(messages))
            if result.get('action') and result['action']['action'] == 'send':
                result['action']['content'] = REPLY
            return json.dumps(result, ensure_ascii=False)
        result = json.loads(group_response(messages, structured))
        if result.get('group_series'):
            result['group_series']['messages'][0]['content'] = REPLY
        return json.dumps(result, ensure_ascii=False)
    return group_response(messages, structured)
