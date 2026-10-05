"""Canonical motivation transitions. Legacy lists are read only at migration boundaries."""
from copy import deepcopy
from backend.runtime_v3.models import Motivation, identity
from backend.services.player_agency import supported_player_field, normalized

FIELDS = ('goals', 'intentions', 'obligations')


def active_texts(records):
    return [r if isinstance(r, str) else r['text'] for r in records
            if isinstance(r, str) or r['status'] == 'active']


def replace_active(records, texts, actor, field, sequence):
    result = deepcopy(records)
    for entry in result:
        if entry['status'] == 'active' and entry['text'] not in texts:
            entry.update(status='cancelled', source_sequence=sequence)
    existing = {r['text'] for r in result if r['status'] == 'active'}
    for text in texts:
        if text not in existing:
            result.append(Motivation(id=identity(field, actor, sequence, text, len(result)), text=text,
                                     source_sequence=sequence).model_dump())
            existing.add(text)
    return result


def apply_changes(resolver, item, cid, index):
    actor = resolver.state['characters'][cid]
    controlled = cid == resolver.state['camera']['controlled_actor_id']
    for field in FIELDS:
        for change in item.get(field + '_updates', []) if isinstance(item.get(field + '_updates', []), list) else []:
            if not isinstance(change, dict) or not resolver.supported(change):
                resolver.warn('character_changes', index, 'нет evidence lifecycle', field, cid); continue
            old = next((r for r in actor[field] if r['id'] == change.get('id')), None)
            status = change.get('status', 'active')
            if old:
                if old['status'] != 'active' or status not in ('completed','cancelled','failed','superseded','expired'): continue
                # Semantics belong to existing Extraction; source must be current.
                # Completing an established motivation does not create a player desire.
                old.update(status=status, evidence=change['evidence'], source_sequence=resolver.turn_id-1)
            else:
                if change.get('id'):
                    resolver.warn('character_changes', index, 'неизвестный motivation ID', field, cid); continue
                text = change.get('text')
                if not isinstance(text, str) or not text.strip() or status != 'active': continue
                if controlled and not supported_player_field(field, [text], [], resolver.player_input, [change['evidence']]):
                    resolver.warn('character_changes', index, 'новая мотивация не задана игроком', field, cid); continue
                values = dict(id=identity(field,cid,resolver.turn_id,text), text=text, evidence=change['evidence'], source_sequence=resolver.turn_id-1)
                if type(change.get('due_minute')) is int and change['due_minute'] >= 0: values['due_minute'] = change['due_minute']
                if not any(r['id']==values['id'] or r['status']=='active' and normalized(r['text'])==normalized(text) for r in actor[field]):
                    actor[field].append(Motivation(**values).model_dump())
