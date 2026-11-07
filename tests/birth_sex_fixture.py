"""#231 saved-response equivalents. No live API and no semantic parser oracle."""
from copy import deepcopy
import json
from unittest.mock import patch

import engine
from backend.repositories.preparation import Repository
from devtools.narrative_test_world import load_fixture

CONFIG = dict(model='test', context_length=65536, max_tokens=2000, update_tokens=4096)
REACTION = 'Я остаюсь рядом и наблюдаю, что происходит с Верой, не вмешиваясь в её действия.'
WORDS = {'male': 'Мальчик', 'female': 'Девочка'}


def due_save(path, checkpoint='pregnancy'):
    repo = Repository(path)
    sid = load_fixture(repo, checkpoint)['save']
    advance = repo.begin_job(sid, '', 'long_term', dict(CONFIG, long_term_advance=dict(
        amount=2, unit='weeks', max_llm_calls=0)))
    engine.run_job(repo.path, advance, engine.Worker())
    assert repo.get_job(advance)['status'] == 'saved'
    return repo, sid


def payload(state, *, sexes=None, event_sexes=None, recipients=None, basis='announcement'):
    p, = state['pregnancies'].values()
    if sexes is None: sexes = [child['sex'] for child in p['children']]
    if event_sexes is None: event_sexes = sexes
    if recipients is None: recipients = ['qa_vera', 'qa_kirill']
    narrative = 'Вера родила. Тимур осмотрел детей. ' + ' '.join(
        f'О ребёнке {i+1} врач сказал: «{WORDS[sex]}».' for i, sex in enumerate(sexes) if sex)
    if basis == 'observation':
        names = {'qa_vera':'Вера', 'qa_kirill':'Кирилл', 'qa_timur':'Тимур'}
        observers = ' и '.join(names.get(actor, actor) for actor in recipients)
        narrative = 'Вера родила. ' + ' '.join(
            f'{observers} рассмотрели ребёнка {i+1}: {WORDS[sex]}.'
            for i, sex in enumerate(sexes) if sex)
    event_text = 'Вера родила. ' + ' '.join(
        f'Ребёнок {i+1}: {WORDS[sex]}.' for i, sex in enumerate(event_sexes) if sex)
    observations = [dict(child_id=child['id'], narrative_sex=sex, event_sex=event_sex,
        basis=basis if sex else 'not_disclosed', perceived_by=recipients if sex else [],
        evidence=narrative if sex else '',
        source_actor_id='qa_timur' if sex and basis=='announcement' else None,
        source_assertion='direct_observation' if sex and basis=='announcement' else None)
        for child, sex, event_sex in zip(p['children'], sexes, event_sexes, strict=True)]
    camera = state['camera']
    raw = dict(final_scene=dict(location_id=camera['location_id'],
        present_character_ids=camera['present_character_ids'], elapsed_minutes=2),
        events=[dict(id='delivery', text=event_text, evidence=narrative, medium='observation',
            participants=['qa_vera','qa_timur'], witnesses=['qa_vera','qa_kirill','qa_timur'],
            minute=p['due_minute'])],
        births=[dict(pregnancy_id=p['id'], source_event_id='delivery', assertion='birth_completed',
            location_id=camera['location_id'], evidence=narrative, sex_observations=observations)])
    return narrative, raw


def execute(repo, sid, narrative, responses, *, kind='turn', retry=None):
    if isinstance(responses, dict): responses = [responses]
    pending = [deepcopy(row) for row in responses]
    calls = []
    if retry: repo.retry_job(retry, CONFIG)
    jid = retry or repo.begin_job(sid, REACTION if kind=='turn' else '', kind, CONFIG)
    def stream(**kwargs):
        calls.append(kwargs)
        if kwargs.get('response_format'):
            yield json.dumps(pending.pop(0) if len(pending)>1 else pending[0], ensure_ascii=False)
        else:
            yield narrative
    with patch('engine.find_loaded_model', return_value={'config': {}}), patch('engine.chat_stream', side_effect=stream):
        engine.run_job(repo.path, jid, engine.Worker())
    return repo.get_job(jid), calls
