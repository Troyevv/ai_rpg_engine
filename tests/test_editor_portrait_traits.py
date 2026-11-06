import json
from copy import deepcopy
import pytest
from test_draft_editor_paths import recorded
from backend.services.draft_changes import apply_proposal
from backend.services.draft_editor import messages
from backend.services.draft_portraits import consume_authored_traits, default_descriptor


def test_new_npc_portrait_contract_and_materialization():
    f=recorded();s=f['base']['state'];p=json.loads(f['reply'])
    card=p['changes'][1]['value']
    card['fields']['Внешность']='Тёмно-русые волосы до подбородка, серо-голубые глаза. Дома носит трикотаж.'
    actor=next(c['value'] for c in p['changes'] if c['path']=='/world/characters/olya')
    actor.update(biological_sex='male', developmental_stage='adult', birth_date=None)
    card['portrait_traits']={'facial_hair':'mustache','hair':'bob','hair_color':'dark_blond','eyes':'grey_blue','clothing':'jumper'}
    before=deepcopy(s)
    out,_=apply_proposal(s,json.dumps(p),editing=True)
    assert s==before
    descriptor=out['world']['characters']['olya']['procedural_portrait']
    assert (descriptor['version'],descriptor['body_frame'],descriptor['facial_hair']) == (2,'male','mustache')
    assert (descriptor['hair'],descriptor['hair_color'],descriptor['eyes'],descriptor['clothing'])==(2,3,7,6)
    assert 'portrait_traits' not in next(c for c in out['characters'] if c['id']=='olya')
    schema=json.loads(messages(f['base'],'Создай сестру')[1]['content'])['world_schema']
    assert 'portrait_traits' in schema['properties']['characters']['items']['properties']
    # Repeated hints cannot overwrite a saved/manual descriptor.
    saved=deepcopy(descriptor);saved['hair']=7
    out['world']['characters']['olya']['procedural_portrait']=saved
    next(c for c in out['characters'] if c['id']=='olya')['portrait_traits']={'hair':'long'}
    consume_authored_traits(out)
    assert out['world']['characters']['olya']['procedural_portrait']==saved


def test_partial_and_absent_traits_stable():
    first=default_descriptor('anna','adult')
    assert first==default_descriptor('anna','adult')
    partial=default_descriptor('anna','adult',hints={'eyes':'grey_blue'})
    assert partial==dict(first,eyes=7)


def test_unknown_traits_rejected():
    f=recorded();p=json.loads(f['reply']);p['changes'][1]['value']['portrait_traits']={'eyes':'ultraviolet'}
    with pytest.raises(ValueError,match='portrait_traits'):apply_proposal(f['base']['state'],json.dumps(p),editing=True)

from test_api import api
import test_draft_editor_paths as pipeline


def test_anna_traits_through_real_editor_job_and_start(api,monkeypatch):
    f=recorded();p=json.loads(f['reply'])
    card=p['changes'][1]['value'];card['name']='Анна Соколова'
    card['fields']['Внешность']='Тёмно-русые волосы до подбородка. Серо-голубые глаза. Родинка над правой бровью. Дома носит трикотаж, на работе медицинскую форму. На запястье маленькие часы.'
    card['fields']['Возраст']='24 года'
    card['portrait_traits']={'hair':'bob','hair_color':'dark_blond','eyes':'grey_blue','clothing':'jumper'}
    actor=next(c['value'] for c in p['changes'] if c['path']=='/world/characters/olya')
    actor['birth_date']='2002-04-11'
    f['reply']=json.dumps(p,ensure_ascii=False)
    monkeypatch.setattr(pipeline,'recorded',lambda:f)
    pipeline.test_olya_job_preview_apply_start_and_restore(api)


@pytest.mark.parametrize(('text','style'), [
    ('Гладко выбрит','clean_shaven'), ('Щетина','stubble'), ('Усы','mustache'),
    ('Короткая борода','short_beard'), ('Полная борода','full_beard'),
])
def test_facial_hair_requires_public_unambiguous_typed_source(text,style):
    actor = {'biological_sex':'male', 'appearance':{'items':{}}}
    baseline = default_descriptor('ilya','adult',actor)
    item = {'kind':'facial_hair','text':text,'revision':1}
    actor['appearance']['items']['beard'] = item
    assert default_descriptor('ilya','adult',actor) == {**baseline,'facial_hair':style}
    conflicting = 'stubble' if style=='mustache' else 'mustache'
    with pytest.raises(ValueError,match='facial_hair'):
        default_descriptor('ilya','adult',actor,{'facial_hair':conflicting})
    for key,value in [('fact_id','private'),('source_event_id','event'),('revision',2),('condition_id','private')]:
        actor['appearance']['items']['beard'] = {**item,key:value}
        assert default_descriptor('ilya','adult',actor,{'facial_hair':style}) == baseline
    actor['appearance']['items'].update(beard=item,other={**item,'text':conflicting})
    assert default_descriptor('ilya','adult',actor) == baseline


def test_seeded_choices_cover_all_styles_without_reading_prose():
    from backend.services.portrait_traits import FACIAL_HAIR
    actor = {'biological_sex':'male','appearance':{'legacy_text':'Полная борода'}}
    options = [default_descriptor(str(n),'adult',actor) for n in range(64)]
    assert {p['facial_hair'] for p in options} == set(FACIAL_HAIR)
    assert all(p['body_frame']=='male' and p['version']==2 for p in options)
    assert options == [default_descriptor(str(n),'adult',dict(actor,biography='Усы')) for n in range(64)]
