"""Expand compact Extraction/10 operations into the existing phase and profile domains."""
from backend.runtime_v3.models import identity, fatal


def wire_schema(props):
    ids = dict(type='array', items=dict(type='string', minLength=1), minItems=1, maxItems=16, uniqueItems=True)
    for name in ('residence_changes', 'role_changes', 'social_relation_changes'):
        item = props[name]['items']
        item['required'] = []
        if name == 'social_relation_changes':
            item['properties']['kind']['enum'] = [*item['properties']['kind']['enum'], 'divorce']
        else:
            replaces = item['properties']['replaces']
            item['properties']['replaces'] = {'oneOf':[replaces, {'const':'current'}]}
        if name == 'residence_changes':
            item['properties']['actor_ids'] = ids
    experience = props['development_evidence']['items']['properties']
    experience['theme'] = dict(type='string', minLength=1, maxLength=100)
    experience['develops'] = dict(type='object', additionalProperties=False, required=['field','text'],
        properties=dict(field=dict(enum=['habits','traits','communication','preferences','strengths','weaknesses',
                                         'fears','temperament','value']), text=dict(type='string',minLength=1,maxLength=300)))


def phase_changes(records, state, turn_id, namespace):
    for name, collection in [('residence_changes','residences'), ('role_changes','roles'),
                             ('social_relation_changes','objective_relations')]:
        phases = []
        for i, source in enumerate(records[name]):
            def reject(message):
                fatal(message, 'life_phase_ambiguous', section=name, index=i)
            actors = source.get('actor_ids')
            if actors and ('actor_id' in source or 'id' in source and len(actors)>1):
                reject('Для общего переезда укажи участников без ID отдельной фазы.')
            for actor in actors or [source.get('actor_id')]:
                row = dict(source)
                row.pop('actor_ids', None)
                if actor is not None:
                    row['actor_id'] = actor
                if name == 'social_relation_changes' and row.get('kind') == 'divorce':
                    pair = {row.get('source_id'),row.get('target_id')}
                    matches = [r['id'] for r in state[collection].values() if r['kind']=='spouse' and
                               r['status']=='active' and {r['source_id'],r['target_id']}==pair]
                    if len(matches)!=1 or row.get('id',matches[0])!=matches[0]:
                        reject('Не найден действующий брак указанной пары.')
                    row.update(id=matches[0], kind='spouse', status='closed', outcome='divorced')
                if row.get('replaces') == 'current':
                    prior = [r['id'] for r in state[collection].values() if r['actor_id']==actor and
                             r['status']=='active' and (collection=='residences' or r['kind']==row.get('kind'))]
                    if len(prior)>1:
                        reject('При нескольких действующих фазах укажи точные ID для замены.')
                    row['replaces'] = prior
                if 'id' not in row:
                    if row.get('status')=='closed':
                        reject('Для закрытия укажи действующую фазу.')
                    row['id'] = identity('phase', namespace, turn_id, collection, actor,
                        row.get('source_id'),row.get('target_id'),row.get('kind'),row.get('location_id'),
                        row.get('title'),row.get('organization_id'))
                phases.append(row)
        records[name] = phases


def consolidate_experience(records, state, turn_id, namespace):
    for row in records['development_evidence']:
        change = row.pop('develops', None)
        theme = row.get('theme')
        if not (change and theme):
            continue
        cid = row['actor_id']
        actor = state['characters'].get(cid, {})
        profile = actor.get('personality') or {}
        recent = {entry['source_turn']:entry['id'] for entry in profile.get('evidence', {}).values()
                  if entry.get('theme')==theme and entry['source_turn'] != turn_id}
        if len(recent)<2:
            continue
        reference = row.setdefault('id', identity('experience', namespace, turn_id, cid, row['meaning']))
        field = change['field']
        item_id = identity('profile', cid, theme, field)
        values = field == 'value'
        old = (actor.get('values', {}) if values else profile.get('items', {})).get(item_id)
        if old and old.get('text') == change['text']:
            continue
        op = dict(item_id=item_id, text=change['text'], operation='refine' if old else 'establish')
        common = dict(actor_id=cid, rationale=row['meaning'], evidence_ids=[*list(recent.values())[-7:],reference])
        if values:
            records['value_deltas'].append(dict(common, **op, basis='sustained_behavior'))
        else:
            records['personality_deltas'].append(dict(common, developmental_fit='established_capability',
                                                       operations=[dict(op,field=field)]))
