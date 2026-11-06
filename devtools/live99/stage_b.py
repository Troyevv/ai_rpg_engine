"""Stage B authorization and scenario plan; executes through the existing runner."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from .budget import Budget, action_ledger
from .evidence import now, snapshot, write
from .recovery import digest, qa_only, rows
from .retest import backup


TEXTS = {
    'social': [
        'Тимур, позвони Олегу сам, если хочешь; я пока останусь с Верой.',
        'Вера, я согласен провести этот вечер с тобой. Что ты предлагаешь?',
        'Я предлагаю встретиться дома сегодня в семь вечера. Тебе подходит это время?',
        'Я готов выслушать возражения и не настаиваю на своём плане.',
        'Спрашиваю, что изменилось после нашего решения и кому теперь нужна помощь.',
        'Предлагаю вместе разобрать фотографии, не передавая оригинал карты.',
        'Я отказываюсь обсуждать чужие личные письма. Предлагаю вернуться к общему делу.',
        'Я благодарю собеседника за конкретную помощь и спрашиваю, чем могу ответить.',
        'Я замолкаю и даю собеседникам возможность самим продолжить разговор.',
        'Я уточняю, какую договорённость мы действительно приняли и что осталось предложением.',
    ],
    'family': [
        'Вера, как ты себя чувствуешь? Я готов выслушать, если хочешь рассказать.',
        'Я предлагаю вместе обратиться к врачу для осмотра. Жду ответа Веры.',
        'Спрашиваю Веру, какую помощь она хочет получить от меня сегодня.',
        'Я предлагаю обсудить семейные планы, не принимая решение за Веру.',
        'Я остаюсь рядом и спрашиваю, как сейчас себя чувствуют Вера и ребёнок.',
        'Мне нравится имя Мира, но это пока предложение. Спрашиваю мнение Веры.',
        'Я предлагаю обсудить имя позже, когда все будут готовы. Сейчас помогу с водой.',
        'Спрашиваю, что мы можем рассказать Асе, не раскрывая чужие личные подробности.',
        'Прошу рассказать, что изменилось в повседневных заботах семьи.',
        'Я уточняю, какие семейные обещания ещё нужно выполнить.',
    ],
    'crisis': [
        'Кирилл, кому уже сообщили о смерти Павла? Я спрашиваю только о подтверждённых разговорах.',
        'Я предлагаю сохранить семейные вещи Павла до разговора с близкими.',
        'Я спрашиваю, кому сейчас нужна практическая помощь и кто может её оказать.',
        'Я предлагаю договориться о встрече с Ниной, но жду её согласия.',
        'Я слушаю воспоминания о Павле и не прошу никого говорить против желания.',
        'Я уточняю, какие обязательства пришлось перенести после потери.',
        'Я спрашиваю собеседника о самочувствии и предлагаю помощь врача, если она нужна.',
        'Я предлагаю сообщить близким только то, что мы точно знаем.',
        'Я не принимаю решения о чужих вещах без владельца. Предлагаю выяснить, кому они принадлежат.',
        'Я спрашиваю, что удалось сделать и какие вопросы ещё остаются открытыми.',
    ],
    'knowledge': [
        'Вера, какие старые карты есть в библиотеке? Я спрашиваю только о библиотеке.',
        'Предлагаю посмотреть открытый каталог вместе. Жду твоего ответа.',
        'Тимур, где сейчас работает Олег и от кого ты это узнал?',
        'Это твои наблюдения или слух? Прошу уточнить источник, не сообщая чужих секретов.',
        'Я не хочу обсуждать личное письмо Олега. Спрашиваю только о публичной работе мастерской.',
        'Вера, можешь ли ты завтра показать мне открытый каталог? Это предложение, я жду согласия.',
        'Я согласен зайти завтра в библиотеку к десяти, если Вере это подходит.',
        'Что из сказанного мы видели лично, а что ещё нужно проверить?',
        'Я прошу не передавать мой вопрос третьим лицам без моего согласия.',
        'Я уточняю, появились ли новые сведения, которые опровергают прежнее мнение.',
    ],
    'campaign': [
        'Вера, что действительно изменилось в семье и мастерской за прошедшие годы?',
        'Я предлагаю проверить ближайшие договорённости по календарю.',
        'Я спрашиваю, какие прежние цели уже достигнуты и какие перестали быть актуальны.',
        'Прошу рассказать о конкретных изменениях у тех, кого давно не видел.',
        'Я интересуюсь, от кого собеседник узнал эти новости; сам их пока не подтверждаю.',
        'Я предлагаю обсудить новое дело, не обещая участия до выяснения условий.',
        'Я возвращаюсь к текущей договорённости и спрашиваю, что мешает её выполнить.',
        'Я готов выслушать самостоятельные планы собеседника, не решая за него.',
        'Я спрашиваю, какие последствия нашего прошлого решения ещё заметны.',
        'Я уточняю, что изменилось со времени последней встречи, а что осталось прежним.',
    ],
    'phone': [
        'Вера, когда тебе удобно созвониться?',
        'Я спрашиваю Веру о доступном времени для встречи, без новых обещаний.',
        'Я уточняю, какие сообщения уже прочитаны и требуют ответа.',
        'Вера, удобно ли тебе обсудить библиотеку завтра утром?',
        'Я хочу согласовать время встречи, а не считать её уже состоявшейся.',
        'Я спрашиваю собеседника, есть ли важные новости от мастерской.',
        'Вера, спасибо за ответ. Если планы изменятся, пожалуйста, сообщи.',
        'Я прошу уточнить, какие договорённости остаются в силе.',
        'Я предлагаю завершить разговор и вернуться к нему после уточнения времени.',
        'Я проверяю последствия последнего разговора и спрашиваю о нерешённых вопросах.',
    ],
}


def operations():
    plans = {case: [dict(kind='turn', action=text) for text in texts] for case, texts in TEXTS.items()}
    # A complete original turn -> regeneration -> select sibling -> rollback -> new branch.
    plans['campaign'][1:1] = [dict(kind=k) for k in ('regenerate', 'variant', 'rollback')]
    plans['campaign'].insert(5, dict(kind='lta', amount=2, model_budget=4))
    plans['family'].insert(4, dict(kind='lta', amount=1, unit='weeks', model_budget=4))
    plans['phone'][0] = dict(kind='phone-retry')  # Explicitly authorized one-time retest.
    for i in (3, 6):
        plans['phone'][i]['kind'] = 'phone'
    plans['crisis'].insert(6, dict(kind='switch', action='qa_kirill'))
    for case, plan in plans.items():
        plan.extend(dict(kind='observed-choice') for _ in range(15-len(plan)))
        for op in plan:
            op['context_length'] = 65536 if case == 'family' else 40960 if case == 'knowledge' else 32768
    return plans


def prepare(parent, directory, sha, master):
    qa_only(sha, sha)
    ledger = (parent / 'budget.sqlite').resolve()
    if not ledger.is_file():
        raise ValueError('Missing historical ledger')
    baseline = rows(parent)
    if any(not r[3] for r in baseline):
        raise ValueError('Unknown paid outcome')
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    backup(parent / 'game.sqlite', directory / 'game.sqlite')
    backup(ledger, directory / 'budget-before.sqlite')
    original = json.loads((parent / 'manifest.json').read_text())
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    repo = Repository(directory / 'game.sqlite')
    for seed in original['seeds'].values():
        if snapshot(parent / 'game.sqlite', seed['save']) != snapshot(directory / 'game.sqlite', seed['save']):
            raise ValueError('Incompatible checkpoint copy')
        if repo.get_snapshot(seed['save']) != snapshot(parent / 'game.sqlite', seed['save'])['snapshot']:
            raise ValueError('Runtime migration changed the checkpoint')
    seeds = dict(original['seeds'])
    # Keep the old family save intact; use the existing near-due #78 fixture for live birth coverage.
    seeds['family'] = load_fixture(repo, 'pregnancy')
    (directory / 'budget.sqlite').symlink_to(ledger)
    baseline_actions = action_ledger(parent)
    authorization = Budget(ledger).authorize_stage_b(directory)
    with closing(sqlite3.connect(directory / 'game.sqlite')) as db:
        jobs = db.execute('SELECT rowid,id,status,kind FROM game_jobs WHERE save_id=? ORDER BY rowid DESC LIMIT 1',
                          (seeds['phone']['save'],)).fetchone()
        if not jobs or jobs[2:] != ('error', 'communication'):
            raise ValueError('Expected original held Phone job for the explicit retest')
        request_ids = [r[0] for r in db.execute('SELECT id FROM llm_requests')]
    plan = operations()
    plan['phone'][0].update(job_id=jobs[1], job_cursor=jobs[0]-1)
    write(directory / 'plan.json', plan)
    evidence = {str(p.relative_to(parent)): digest(p) for p in parent.rglob('*') if p.is_file()
                and p.name not in ('budget.sqlite', 'run.lock') and not p.name.startswith('budget.sqlite-')}
    write(directory / 'manifest.json', dict(version=3, stage='B', sha=sha, master_sha=master, created=now(),
        seeds=seeds, original_seeds=original['seeds'], parent=str(parent), ledger=str(ledger),
        parent_evidence=evidence, baseline_reservations=baseline, baseline_actions=baseline_actions,
        baseline_request_ids=request_ids, authorization=list(authorization), action_limit=baseline_actions+100,
        plan_hash=digest(directory / 'plan.json'), additional_usd='2.00',
        reason='Explicit Stage B authorization after reviewed Stage A/retest; no claim that Stage A completed'))


def validate(directory, manifest):
    ledger = (directory / 'budget.sqlite').resolve()
    if str(ledger) != manifest['ledger']:
        raise ValueError('Historical ledger link changed')
    with closing(sqlite3.connect(ledger)) as db:
        auth = Budget(ledger, directory).stage_b_baseline(db)
        if list(auth) != manifest['authorization'] or auth[2]+100 != manifest['action_limit']:
            raise ValueError('Stage B allowance or action baseline changed')
    if rows(directory)[:len(manifest['baseline_reservations'])] != manifest['baseline_reservations']:
        raise ValueError('Historical spending changed')
    if action_ledger(directory) < manifest['baseline_actions']:
        raise ValueError('Historical action count lost')
    if digest(directory / 'plan.json') != manifest['plan_hash']:
        raise ValueError('Reviewed plan changed')
    for name, checksum in manifest['parent_evidence'].items():
        if digest(Path(manifest['parent']) / name) != checksum:
            raise ValueError('Historical evidence changed: '+name)
