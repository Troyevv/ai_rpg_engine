"""Lossless card-label adaptation at the initial-generation boundary."""
from copy import deepcopy
from backend.services.world import CARD_FIELDS
from backend.services.initial_world_v2 import _check
from backend.runtime_v3.personality import CARD_FIELDS as PERSONALITY_FIELDS
from backend.runtime_v3.models import PersonalityItem, PersonalityProfile, Fact, identity

LABELS = {label.casefold():label for label in (*CARD_FIELDS, *PERSONALITY_FIELDS.values())}
LABELS.update({'манера_речи':'Стиль общения','манера речи':'Стиль общения',
               'страхи':'Страхи и уязвимости','слабые стороны':'Слабости'})
PRIVATE_LABELS = {'секрет','секреты','тайна','тайны','secret','secrets'}


def normalize_cards(payload):
    result=deepcopy(payload)
    if not isinstance(result,dict) or not isinstance(result.get('cards'),dict):return result
    for cid,card in result['cards'].items():
        if not isinstance(card,dict) or not isinstance(card.get('fields'),dict):continue
        fields={}
        for key,text in card['fields'].items():
            target=LABELS.get(key.casefold(),key)
            if target in fields and isinstance(text,str) and isinstance(fields[target],str):
                fields[target]+='\n'+text
            else:fields[target]=text
        card['fields']=fields
        actors=result.get('characters')
        actor=actors.get(cid) if isinstance(actors,dict) else None
        if isinstance(actor,dict) and actor.get('personality') is None:
            # Same explicit-label mapping as Runtime initialization, with strict
            # validation before checkpoint commit; never truncate oversized prose.
            items={field:_check(PersonalityItem,dict(field=field,text=fields[label]),'characters/'+cid+'/personality/'+field).model_dump()
                   for field,label in PERSONALITY_FIELDS.items() if isinstance(fields.get(label),str) and fields[label].strip()}
            if items:actor['personality']=PersonalityProfile(items=items).model_dump()
    return result


def private_card_facts(cards):
    """An explicit secret label is not public card text or evidence of a holder."""
    facts={}
    for cid,card in cards.items():
        for label,text in list(card['fields'].items()):
            if label.casefold() in PRIVATE_LABELS and text.strip():
                fid=identity('initial_card_secret',cid,label)
                facts[fid]=_check(Fact,dict(id=fid,text=text,visibility='secret',character_ids=[cid]),'facts/'+fid).model_dump()
                del card['fields'][label]
    return facts
