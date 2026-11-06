"""Authoring through production draft confirmation; shared by API and browser tests."""
import json
from secret_handoff181_fixture import candidate as base, SONYA, MAXIM, OWN

WORLD = 'Под городом скрыта древняя обсерватория.'
BIO = 'В родильном доме Илью перепутали с другим ребёнком.'
KNOWN = 'Известный переводчик публикуется под чужим именем.'

PRIVATE = 'Это бытовая приватная записка, не сюжетная тайна.'


def candidate(semantic=False):
    state = base(own=True)
    world = state['world']
    for fid, cid in [('own181','ilya'), ('fact_sonya_love','sonya'), ('fact_maxim_sale','maxim')]:
        world['facts'][fid]['secret_keeper_ids'] = [cid]
        # Explicit authored own secret is enough at this boundary; no manual holder.
        del world['knowledge'][cid+':'+fid]
    world['facts']['world183'] = dict(id='world183',text=WORLD+' '+('За старой стеной сохранились карты звёздного неба и записи наблюдений. '*55)+'Конец длинной тайны 183.',secret=True,story_secret=True,
        secret_subject_ids=[],secret_existence='hidden',character_ids=[],evidence=[])
    world['knowledge']['ilya:fact_maxim_sale']['status']='suspected'
    world['facts']['private183'] = dict(id='private183',text=PRIVATE,secret=True,story_secret=False,
        secret_subject_ids=[],secret_existence='hidden',character_ids=['sonya'],evidence=[])
    if semantic:
        world['facts']['circumstance183'] = dict(id='circumstance183',text=BIO,secret=True,story_secret=True,
            secret_subject_ids=[],secret_biography_ids=['ilya'],secret_existence='hidden',character_ids=[],evidence=[])
        world['facts']['known183'] = dict(id='known183',text=KNOWN,secret=True,story_secret=True,
            secret_subject_ids=[],secret_keeper_ids=['maxim'],secret_existence='hidden',character_ids=[],evidence=[])
        world['knowledge']['ilya:known183'] = dict(actor_id='ilya',fact_id='known183',status='known')
    return state


def stage(repo, wid, semantic=False):
    state = candidate(semantic)
    with repo.connect() as db:
        repo._record_document(db, 'world_draft', wid, json.dumps(dict(state=state,candidate=True,
            generated=True,source='',review=dict(status='not_started')),ensure_ascii=False), True, 'generation_candidate')
    return state


def start(client, repo, semantic=False):
    wid = client.post('/api/workspaces',json={'name':'Сосновка 183'}).json()['id']
    stage(repo, wid, semantic)
    path=f'/api/workspaces/{wid}/draft'
    draft=client.get(path+'?author=true').json()
    response=client.post(path+'/confirm',json=dict(revision=draft['revision'],version_id=draft['version_id'],accept_warnings=True))
    assert response.status_code==200,response.text
    return response.json()
