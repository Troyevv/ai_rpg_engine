"""Seeded optional-record damage may not leak Python type errors or need repair."""
from copy import deepcopy
import random
import pytest
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.raw import extraction_schema
from backend.services.relation_dimensions import RELATION_DIMENSIONS
from test_runtime_v3_domain import initial,payload,QUOTE


@pytest.mark.parametrize('seed',range(100))
def test_optional_mutations(seed):
    rng=random.Random(seed);p=payload()
    p['events'][0].update(from_location='stale',scene_id='obsolete')
    for key in ('minute','order','location_id'):
        p['events'][0][key]=rng.choice([None,[],{},'wrong',True,5])
    p['knowledge_gained'].append(dict(actor_id=rng.choice([[],{},None,42]),fact_id='f',source_event_id=['e'],evidence=QUOTE))
    p['character_changes']=[dict(id='a',situation='У двери',emotion=rng.choice([None,[],'злится']),evidence=QUOTE)]
    p['relationship_changes']=[dict(source_id='a',target_id='b',dimensions={'trust':10,'surprise':rng.choice([[],{},None,True,50])},context='Контекст',evidence=QUOTE)]
    for key in ('events','knowledge_gained','character_changes','relationship_changes'):
        p[key].append(rng.choice([None,[],3,'bad']))
        rng.shuffle(p[key])
    result=StateResolver(initial(),QUOTE,'Я подхожу к окну.').resolve(p)
    assert result.state['knowledge']['a:f']['status']=='known'
    assert result.state['characters']['a']['situation']=='У двери'
    assert result.state['relationships']['a:b']['dimensions']=={'trust':10}


def test_dimensions_schema_single_registry():
    dimensions=extraction_schema()['properties']['relationship_changes']['items']['properties']['dimensions']
    assert set(dimensions['properties'])==set(RELATION_DIMENSIONS)
    assert dimensions['additionalProperties'] is False
    assert dimensions['required']==[]
