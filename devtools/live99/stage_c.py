"""Reviewed Stage B retest and bounded Stage C on the existing browser runner."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from .budget import Budget, action_ledger
from .evidence import now, snapshot, write
from .recovery import digest, qa_only, rows, read, completed
from .retest import backup

MAX_ACTIONS = 120  # Includes retest, deterministic operations and failed attempts.
FIXES = {
    '211': '0c2f9fb042e6677d2b3ef03771556d5daa858344',
    '206': '9df13da7a02d08610af571bd0b044a07011814a8',
    '209': '2af969f9d62d96e663f5519c30b7fff301561e4e',
    '207': '4c44be6', '208': '57ba21e', '212': '063ae07',
}


def turn(text):
    return dict(kind='turn', action=text)


def continuation():
    return {
        'social': [
            turn('Я не согласен передавать оригинал карты. Предлагаю сделать копию и спрашиваю мнение Веры.'),
            turn('Я выслушиваю возражения, не меняя своего отказа передавать оригинал.'),
            turn('Я предлагаю Тимуру самому выбрать, с кем он хочет обсудить копирование карты.'),
            turn('Я готов помочь разобрать фотографии сейчас. Спрашиваю, какую часть работы взять.'),
            turn('Я выполняю предложенную мне сортировку фотографий и показываю результат Вере.'),
            turn('Я спрашиваю Веру, что в нашем разговоре было для неё неприятно и что стоит изменить.'),
            turn('Я благодарю за честный ответ и даю собеседникам возможность самим продолжить разговор.'),
        ],
        'family': [
            turn('Я спрашиваю Веру о её самочувствии после родов и какую помощь она хочет получить.'),
            turn('Я предлагаю имя Мира, но не считаю его согласованным. Жду ответа Веры.'),
            turn('Я предлагаю помочь с ребёнком и спрашиваю, что нужно сделать сейчас.'),
            dict(kind='lta', amount=1, unit='years', model_budget=4),
            turn('Я спрашиваю Веру, чему ребёнок научился за прошедшее время и что изменилось в семье.'),
            dict(kind='lta', amount=5, unit='years', model_budget=4),
            turn('Я интересуюсь самостоятельными занятиями ребёнка и не выбираю за него будущую профессию.'),
            turn('Я прошу рассказать о важном событии семьи и о том, кто был его свидетелем.'),
        ],
        'crisis': [
            turn('Я спрашиваю Веру, какие дела Павла после его смерти остались незавершёнными.'),
            turn('Я предлагаю связаться с Ниной и выяснить, нужна ли ей помощь с семейными вещами.'),
            dict(kind='switch', action='qa_vera'),
            turn('Я, Вера, спрашиваю Кирилла о практических последствиях смерти Павла для семьи.'),
            dict(kind='lta', amount=2, unit='weeks', model_budget=4),
            turn('Я уточняю, какие обязательства после утраты удалось выполнить, а какие пришлось отменить.'),
            dict(turn('Я прошу Тимура вызвать врача к Кириллу и сообщить только подтверждённые сведения.'), seed_ref='incapacity'),
            dict(turn('Я спрашиваю Олега о его руке и предлагаю поручить физическую помощь тому, кто может её оказать.'), seed_ref='incapacity'),
            dict(kind='switch', action='qa_nina', seed_ref='incapacity'),
            dict(turn('Я, Нина, спрашиваю Веру о состоянии Кирилла и предлагаю практическую помощь.'), seed_ref='incapacity'),
        ],
        'knowledge': [
            turn('Я согласен прийти завтра в библиотеку в 15:00. Спрашиваю Веру, подходит ли ей именно это время.'),
            turn('Я сообщаю Вере: вчера я оставил копию карты в открытом каталоге библиотеки. Прошу проверить её наличие.'),
            turn('Я спрашиваю, видел ли Тимур эту копию сам или знает о ней только с моих слов.'),
            turn('Я уточняю: я ошибся, копия осталась у меня. Прошу Веру больше не полагаться на прежнее сообщение.'),
            turn('Я прошу Веру сообщить исправление Тимуру, если она успела передать ему прежние сведения.'),
            turn('Я не раскрываю содержание личного письма Олега и прошу не обсуждать неизвестные нам подробности.'),
            turn('Я спрашиваю Тимура, что он теперь считает известным о копии карты и откуда это узнал.'),
        ],
        'campaign': [
            turn('Я спрашиваю Тимура, состоялся ли его звонок Олегу и что из договорённости осталось выполнить.'),
            dict(kind='regenerate'), dict(kind='variant'), dict(kind='rollback'),
            turn('Я предлагаю обсудить дальнейшую работу мастерской, не обещая своего участия заранее.'),
            dict(kind='background'),
            dict(kind='lta', amount=5, unit='years', model_budget=6),
            dict(kind='background'),
            dict(kind='lta', amount=10, unit='years', model_budget=6),
            dict(kind='background'),
        ],
        'phone': [
            dict(kind='phone', action='Вера, давай созвонимся сейчас, если тебе удобно.'),
            dict(kind='phone-call'),
            dict(kind='call-speech', action='Вера, расскажи, какие планы у тебя на завтра. Я пока ничего не обещаю.'),
            dict(kind='call-end'),
            dict(kind='phone-group', action='Всем привет. Кто хочет сам рассказать новости мастерской?'),
            turn('Я остаюсь на месте, занимаюсь своими фотографиями и даю другим возможность связаться со мной.'),
            dict(kind='phone-group', action='Я предлагаю обсудить новости здесь, но не принимаю обязательств о встрече.'),
            dict(kind='phone', action='Спасибо за разговор. Если планы изменятся, сообщи мне, пожалуйста.'),
        ],
    }


def prepare(parent, directory, sha, master):
    import subprocess
    from .run import ROOT
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    qa_only(sha, sha)
    for fix in FIXES.values():
        subprocess.run(['git', 'merge-base', '--is-ancestor', fix, master], cwd=ROOT, check=True)
    old = read(parent / 'manifest.json')
    if old.get('stage') != 'B':
        raise ValueError('Choose the preserved Stage B parent')
    ledger = (parent / 'budget.sqlite').resolve()
    baseline = rows(parent)
    if any(not r[3] for r in baseline):
        raise ValueError('Unknown paid outcome')
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    backup(parent / 'game.sqlite', directory / 'game.sqlite')
    backup(ledger, directory / 'budget-before.sqlite')
    repo = Repository(directory / 'game.sqlite')
    for seed in old['seeds'].values():
        original = snapshot(parent / 'game.sqlite', seed['save'])
        if snapshot(directory / 'game.sqlite', seed['save']) != original or repo.get_snapshot(seed['save']) != original['snapshot']:
            raise ValueError('Checkpoint migration changed canonical data; inspect the isolated copy')
    seeds = dict(old['seeds'])
    extra_seeds = {}
    extension = parent / 'crisis-extension.json'
    if extension.exists():
        extra_seeds['incapacity'] = read(extension)['seed']
        sid = extra_seeds['incapacity']['save']
        if repo.get_snapshot(sid) != snapshot(parent / 'game.sqlite', sid)['snapshot']:
            raise ValueError('Incapacity checkpoint is incompatible')
    else:
        raise ValueError('Preserved Stage B incapacity checkpoint is required')
    # The old Family save is already beyond due. Keep it intact and reproduce
    # the boundary from the same deterministic near-due #78 checkpoint.
    seeds['family'] = load_fixture(repo, 'pregnancy')
    plans = {case: [] for case in seeds}
    failures = {'social': '005', 'knowledge': '005', 'campaign': '014', 'phone': '000'}
    with closing(sqlite3.connect(directory / 'game.sqlite')) as db:
        db.row_factory = sqlite3.Row
        request_ids = [r[0] for r in db.execute('SELECT id FROM llm_requests')]
        for case, index in failures.items():
            result = read(parent / case / index / 'result.json')
            jobs = list(db.execute('SELECT * FROM game_jobs WHERE save_id=? AND rowid>?',
                                  (seeds[case]['save'], result['job_cursor'])))
            if len(jobs) != 1 or jobs[0]['status'] != 'error':
                raise ValueError('Retest does not identify one original failed job: '+case)
            job = dict(jobs[0])
            op = dict(kind='phone-retry' if case == 'phone' else 'retry', action=result['action'],
                      job_id=job['id'], job_cursor=result['job_cursor'], old_case=f'{case}/{index}')
            if case != 'phone':
                if not job['narrative_complete']:
                    raise ValueError('Cannot reuse incomplete Narrative')
                op.update(reuse_narrative=job['narrative'], original_request_ids=[r[0] for r in
                          db.execute('SELECT id FROM llm_requests WHERE job_id=?', (job['id'],))])
            plans[case].append(op)
    plans['social'].append(turn('Вера, что ты решила насчёт совместного разбора фотографий? Я спрашиваю о твоём решении.'))
    plans['family'] = [dict(kind='lta', amount=2, unit='weeks', model_budget=4),
                       turn('Я остаюсь рядом с Верой и держу её за руку, пока она рожает. Жду указаний врача.')]
    plans['campaign'].append(dict(kind='lta', amount=1, unit='years', model_budget=4))
    plans['crisis'] = [turn('Я спрашиваю, что изменилось в жизни семьи после смерти Павла.')]
    counts = {case: len(ops) for case, ops in plans.items()}
    for case, ops in continuation().items():
        for op in plans[case]:
            op['phase'] = 'retest'
        for op in ops:
            plans[case].append(dict(op, phase='continue', lineage_index=counts[case]))
        for op in plans[case]:
            op['context_length'] = 65536 if case == 'family' else 40960
    if sum(map(len, plans.values())) > MAX_ACTIONS:
        raise ValueError('Plan exceeds action budget')
    (directory / 'budget.sqlite').symlink_to(ledger)
    actions = action_ledger(parent)
    authorization = Budget(ledger).authorize_stage_c(directory)
    write(directory / 'plan.json', plans)
    evidence = {str(p.relative_to(parent)): digest(p) for p in parent.rglob('*') if p.is_file()
                and p.name not in ('budget.sqlite', 'run.lock') and not p.name.startswith('budget.sqlite-')}
    write(directory / 'manifest.json', dict(version=4, stage='C', sha=sha, master_sha=master, created=now(),
        seeds=seeds, extra_seeds=extra_seeds, original_seeds=old['seeds'], parent=str(parent), ledger=str(ledger),
        parent_evidence=evidence, baseline_reservations=baseline, baseline_actions=actions,
        baseline_request_ids=request_ids, authorization=list(authorization), action_limit=actions+MAX_ACTIONS,
        plan_hash=digest(directory / 'plan.json'), additional_usd='2.00', retest_counts=counts,
        reason='Explicit Stage B Retest -> Stage C authorization; one shared additional $2, no automatic paid retry'))


def validate(directory, manifest):
    from .stage_b import validate as validate_history
    validate_history(directory, manifest)
    for receipt in (directory / 'retest-reviews').glob('*.json'):
        review = read(receipt)
        if review['case'] not in manifest['seeds'] or review['status'] != 'passed':
            raise ValueError('Invalid retest review')
        for name, checksum in review['evidence'].items():
            if digest(directory / name) != checksum:
                raise ValueError('Reviewed retest evidence changed')


def review(directory, manifest, case):
    """An explicit QA review records evidence, never rewrites a failure as success."""
    validate(directory, manifest)
    if case not in manifest['seeds']:
        raise ValueError('Choose a retested group')
    target = directory / 'retest-reviews' / f'{case}.json'
    if target.exists():
        raise ValueError('Retest already reviewed')
    folders = [directory / case / f'{i:03d}' for i in range(manifest['retest_counts'][case])]
    if not all(completed(p) for p in folders):
        raise ValueError('Held or missing retest; do not enter associated Stage C scenarios')
    audit = read(directory / 'semantic-reviews' / f'{case}.json')
    if audit.get('status') != 'passed' or audit.get('case') != case or not audit.get('checks') or not all(audit['checks'].values()):
        raise ValueError('A semantic state/History/Knowledge/agency review is required')
    evidence = {str(p.relative_to(directory)): digest(p) for folder in folders for p in folder.iterdir() if p.is_file()}
    evidence[str((directory / 'semantic-reviews' / f'{case}.json').relative_to(directory))] = digest(directory / 'semantic-reviews' / f'{case}.json')
    target.parent.mkdir(exist_ok=True)
    write(target, dict(case=case, status='passed', reviewed=now(), evidence=evidence))
