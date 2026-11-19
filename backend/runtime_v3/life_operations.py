"""Expand compact Extraction/10 operations into the existing phase and profile domains."""
from backend.runtime_v3.models import identity, fatal


def wire_schema(props, version):
    ids = dict(type='array', items=dict(type='string', minLength=1), minItems=1, maxItems=16, uniqueItems=True)
    for name in ('residence_changes', 'role_changes', 'social_relation_changes'):
        item = props[name]['items']
        item['required'] = []
        if version >= 11:
            item['properties']['perceived_by'] = dict(type='array', items=dict(type='string'), maxItems=64)
        if name == 'social_relation_changes':
            item['properties']['kind']['enum'] = [*item['properties']['kind']['enum'], 'divorce']
        else:
            replaces = item['properties']['replaces']
            item['properties']['replaces'] = {'oneOf':[replaces, {'const':'current'}]}
        if name == 'residence_changes':
            item['properties']['actor_ids'] = ids
    experience = props['development_evidence']['items']['properties']
    if version >= 11:
        experience['actor_id']['description'] = 'Владелец собственного опыта или поведения; наблюдатели перечислены в perceived_by.'
    experience['theme'] = dict(type='string', minLength=1, maxLength=100)
    experience['develops'] = dict(type='object', additionalProperties=False, required=['field','text'],
        properties=dict(field=dict(enum=['habits','traits','communication','preferences','strengths','weaknesses',
                                         'fears','temperament','value']), text=dict(type='string',minLength=1,maxLength=300)))


def phase_changes(records, state, turn_id, namespace, version=10):
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
                    if version >= 11 and row.get('status') == 'closed' and prior == [row.get('id')]:
                        row.pop('replaces')  # Closing the sole current phase already names it.
                    else:
                        row['replaces'] = prior
                if 'id' not in row:
                    if row.get('status')=='closed':
                        reject('Для закрытия укажи действующую фазу.')
                    row['id'] = identity('phase', namespace, turn_id, collection, actor,
                        row.get('source_id'),row.get('target_id'),row.get('kind'),row.get('location_id'),
                        row.get('title'),row.get('organization_id'))
                phases.append(row)
        records[name] = phases


def bind_phase_observers(records, state, turn_id, namespace, order, warnings):
    """Use the same private fact for the phase transition and its actual recipients."""
    actors = set(state['characters']) | {row['id'] for row in records['promotions']}
    for section, collection in (('role_changes', 'roles'), ('residence_changes', 'residences'),
                                ('social_relation_changes', 'objective_relations')):
        for index, row in enumerate(records[section]):
            observers = row.pop('perceived_by', [])
            recipients = list(dict.fromkeys(cid for cid in observers if cid in actors))
            if set(observers) - actors:
                warnings.append(dict(section=section, index=index, code='invalid_phase_recipient',
                                     action='omit_invalid_recipients'))
            previous = state[collection].get(row['id'], {})
            phase = {**previous, **row}
            closed = phase.get('status') == 'closed'
            link = 'closure_fact_id' if closed else 'fact_id'
            fid = phase.get(link)
            # An already established unlinked opening is historical; never change its identity.
            if previous and not closed and not fid:
                continue
            affected = ([phase.get('source_id'), phase.get('target_id')] if collection == 'objective_relations'
                        else [phase.get('actor_id')])
            if any(cid not in actors for cid in affected):
                continue  # The phase owner diagnoses an invalid identity.
            label = phase.get('title') or phase.get('kind')
            if collection == 'residences':
                location = phase.get('location_id')
                label = state['locations'].get(location, {}).get('name') or location
            names = ', '.join(state['characters'].get(cid, {}).get('display_name') or cid for cid in affected)
            text = f"{names} — {label} ({'завершено' if closed else 'установлено'})."
            if not fid:
                fid = row[link] = identity('phase-fact', namespace, turn_id, collection, row['id'], link)
                records['facts'].append(dict(id=fid, text=text, character_ids=affected, visibility='secret'))
            if recipients:
                records['information_events'].append(dict(
                    id=identity('phase-notice', namespace, turn_id, collection, row['id'], link),
                    text=text, source_actor_id=None, medium='discovery', order=order+1,
                    claims=[dict(fact_id=fid, perceived_by=recipients, assertion='observation', status='known')]))


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
