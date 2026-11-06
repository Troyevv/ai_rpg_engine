"""Minimal authoring reproduction of Sosnovka's shared possession provenance."""
import json
from test_draft_world import fixture as base

SONYA = 'Соня несколько лет влюблена в Илью.'
MAXIM = 'Максим тайно готовит продажу семейного дома.'
OWN = 'Илья выпускает музыку под псевдонимом.'


def candidate(own=False):
    raw = base()
    ids = [c['id'] for c in raw['characters'][:3]]
    mapping = dict(zip(ids, ['ilya', 'sonya', 'maxim']))
    def rename(v):
        if isinstance(v, dict): return {mapping.get(k, k): rename(x) for k, x in v.items()}
        if isinstance(v, list): return [rename(x) for x in v]
        return mapping.get(v, v) if isinstance(v, str) else v
    s = rename(raw)
    s['draft_contract'] = 4
    for card, name in zip(s['characters'], ['Илья', 'Соня', 'Максим']): card['name'] = name
    w = s['world']
    w['facts'] = {}; w['knowledge'] = {}; w['events'] = {}; w['relationships'] = {}
    for scene in w['scenes'].values(): scene['event_ids'] = []
    for cid, row in w['characters'].items(): row['last_event_id'] = None
    definitions = [('fact_sonya_love', SONYA, ['sonya','ilya'], 'sonya', 'discoverable'),
                   ('fact_maxim_sale', MAXIM, ['maxim','sonya'], 'maxim', 'discoverable'),
                   ('protected181', 'PROTECTED_CONTENT_181', ['sonya'], 'sonya', 'hidden')]
    if own: definitions.append(('own181', OWN, ['ilya'], 'ilya', 'hidden'))
    for fid, text, subjects, holder, existence in definitions:
        w['facts'][fid] = dict(id=fid, text=text, secret=True, story_secret=True,
            secret_subject_ids=subjects, secret_existence=existence, character_ids=subjects, evidence=['AUTHOR_EVIDENCE_181'])
        for cid in ('ilya','sonya','maxim'):
            w['knowledge'][cid+':'+fid] = dict(actor_id=cid, fact_id=fid,
                status='known' if cid==holder else 'unknown', source_event_id=None)
    w['possessions'] = {iid:dict(id=iid, name=name, kind='предмет', owner_id=holder, holder_id=holder,
        location_id=None, status='available', fact_id=fid, source_event_id=None)
        for iid,name,holder,fid in [('notebook181','PRIVATE_NOTEBOOK_181','sonya','fact_sonya_love'),
            ('phone181','PRIVATE_PHONE_181','maxim','fact_maxim_sale'),
            ('docs181','PRIVATE_DOCS_181','maxim','fact_maxim_sale')]}
    return s


def stage(repo, wid, own=False):
    s = candidate(own)
    with repo.connect() as db:
        repo._record_document(db, 'world_draft', wid, json.dumps(dict(state=s,candidate=True,
            generated=True,source='',review=dict(status='not_started')),ensure_ascii=False), True, 'generation_candidate')
    return s


def payload(snap, reveal=True):
    s = snap['world_state']
    return dict(final_scene=dict(location_id=s['camera']['location_id'],
        present_character_ids=s['camera']['present_character_ids'],elapsed_minutes=1),
        events=[dict(id='confession181',text='Соня призналась Илье.',evidence='Соня призналась Илье.',
            participants=['ilya','sonya'],witnesses=['ilya'],fact_ids=['fact_sonya_love'],medium='conversation')] if reveal else [],
        knowledge_gained=[dict(actor_id='ilya',fact_id='fact_sonya_love',source_event_id='confession181',
            evidence='Соня призналась Илье.')] if reveal else [],
        choices=[dict(action=f'Осмотреть деталь {i}',speech='') for i in range(6)])
