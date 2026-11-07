"""Post-#220..#226 plans on the existing Stage C runner, with preserved evidence."""
from contextlib import closing
from decimal import Decimal
from pathlib import Path
import sqlite3
import subprocess

from .budget import Budget, INPUT, OUTPUT, LIMIT_NUSD, action_ledger
from .evidence import now, snapshot, write
from .recovery import digest, qa_only, read, rows
from .retest import backup
from .stage_c import MAX_ACTIONS, turn

FIXES = ('1b2e3e42b030edb964ed1b53da4f8eda05a595a7',
         'a06caf7e839be317f77572091e50c98922794d60',
         '8d281b0b3fac22e7d90c68377eb6d02a69246266',
         '68a584d24140cc4e6bf13c6823747eb4b90f7ccd',
         '25c834b094a9047471406d7166111c8b6b755f75')


def plans(parent, *, campaign=False):
    def old(case, index):
        return read(parent / case / f'{index:03d}' / 'result.json')['action']
    def abandon(case, index, draft):
        jobs = read(parent / case / f'{index:03d}' / 'diagnostics.json.gz')
        if len(jobs) != 1 or jobs[0]['status'] != 'error':
            raise ValueError('Expected one preserved rejected job')
        return dict(kind='abandon', action=draft, job_id=jobs[0]['id'])
    def rollback(case, index, seed_ref=None):
        return dict(kind='rollback', restore_snapshot_path=str(parent / case / f'{index:03d}' / 'before.json.gz'),
                    **({'seed_ref': seed_ref} if seed_ref else {}))
    consent = 'Я согласен прийти завтра в библиотеку в 15:00. Спрашиваю Веру, подходит ли ей именно это время.'
    help_text = 'Я согласен сейчас сортировать фотографии по датам, оставляя оригинал карты на месте. Прошу Веру показать первую пачку.'
    retest = {
        'social': [abandon('social', 5, help_text), turn(help_text)],
        'knowledge': [abandon('knowledge', 0, consent), turn(consent)],
        'phone': [abandon('phone', 6, old('phone', 6)), turn(old('phone', 6)),
                  turn('Я не удерживаю Тимура и продолжаю разбирать фотографии. Не предлагаю ему место назначения.')],
        'campaign': [rollback('campaign', 1), rollback('campaign', 0), turn(old('campaign', 0)),
                     turn('Я уточняю у Тимура время его звонка Олегу, не принимая обязательств за себя.')],
        'crisis': [rollback('crisis', 10, 'incapacity'),
                   dict(turn(old('crisis', 10)), seed_ref='incapacity')],
        'family': [abandon('family', 1, old('family', 1)), turn(old('family', 1)),
                   turn('Я остаюсь рядом и наблюдаю, что происходит с Верой, не вмешиваясь в её действия.'),
                   turn('Я продолжаю держать Веру за руку, если она этого хочет, и наблюдаю за изменениями.'),
                   dict(kind='lta', amount=2, unit='weeks', model_budget=4, seed_ref='family_remote'),
                   dict(kind='switch', action='qa_nina', seed_ref='family_remote'),
                   dict(turn('Я, Нина, разбираю свои бумаги в библиотеке и ни с кем не связываюсь.'), seed_ref='family_remote'),
                   dict(turn('Я продолжаю заниматься своими бумагами и отмечаю только то, что сама вижу.'), seed_ref='family_remote')],
    }
    continuations = {
        'social': [turn(t) for t in [
            'Я показываю Вере первую отсортированную пачку и спрашиваю, верно ли понял порядок.',
            'Я предлагаю Тимуру самому выбрать занятие, не назначая ему работу.',
            'Я отказываюсь отдавать оригинал карты и объясняю, что пока не готов с ним расстаться.',
            'Я спрашиваю Веру, что ей не понравилось в нашем разговоре, и выслушиваю ответ.',
            'Я благодарю за прямой ответ. Продолжаю свою работу и оставляю другим возможность действовать.',
            'Я спрашиваю Веру, что из нашей совместной работы уже получилось и что стоит изменить.',
            'Я предлагаю сделать перерыв и спрашиваю, хочет ли кто-нибудь продолжить разговор.']],
        'knowledge': [turn(t) for t in [
            'Я говорю Вере: кажется, копия карты лежит в открытом каталоге библиотеки. Это моё предположение, я не проверял.',
            'Я спрашиваю Тимура, видел ли он копию сам или слышал о ней от кого-то.',
            'Я уточняю Вере: я ошибся, копия всё ещё у меня. Прошу не полагаться на моё прежнее предположение.',
            'Я прошу Веру сообщить исправление Тимуру, если она уже успела передать прежнее сообщение.',
            'Я спрашиваю Тимура, что ему теперь известно о копии карты и откуда.',
            'Я не раскрываю содержание личного письма Олега и спрашиваю только о публичной работе библиотеки.',
            'Я предлагаю уточнить расписание библиотеки непосредственно у сотрудников, не выдумывая ответ за них.']],
        'crisis': [dict(turn(t), seed_ref='incapacity') for t in [
            'Я, Нина, спрашиваю присутствующих в библиотеке, какие сведения о Кирилле у них подтверждены.',
            'Я предлагаю сообщить врачу только известные факты и не объявляю Кирилла выздоровевшим.',
            'Я спрашиваю Олега о доступной ему помощи, не требуя движений повреждённой рукой.',
            'Я выслушиваю ответ и предлагаю каждому самому выбрать посильное действие.']]
            + [turn('Я, Вера, спрашиваю Кирилла, какие дела Павла после его смерти ещё нужно завершить.'),
               turn('Я предлагаю сохранить фотографии Павла и спрашиваю мнение семьи.'),
               dict(kind='lta', amount=2, unit='weeks', model_budget=6),
               turn('Я спрашиваю, что фактически изменилось в жизни семьи за прошедшие две недели.')],
        'family': [turn('Я спрашиваю Веру о самочувствии и о том, какой помощи она хочет сейчас.'),
                   turn('Я предлагаю имя Мира для ребёнка и жду ответа Веры, не считая согласие полученным.'),
                   turn('Я спрашиваю, как лучше помочь семье сегодня, и выслушиваю ответ.'),
                   dict(kind='lta', amount=1, unit='years', model_budget=6),
                   turn('Я интересуюсь занятиями ребёнка и изменениями в семье за прошедший год.'),
                   dict(kind='lta', amount=5, unit='years', model_budget=6),
                   turn('Я спрашиваю ребёнка о его собственных интересах и не выбираю за него будущую профессию.')],
        'campaign': [dict(kind='regenerate'), dict(kind='variant', lineage_index=3),
                     dict(kind='rollback', lineage_index=3),
                     turn('Я предлагаю обсудить дальнейшую работу мастерской, не обещая участия заранее.'),
                     dict(kind='background'), dict(kind='lta', amount=1, unit='years', model_budget=6),
                     turn('Я спрашиваю, что стало с договорённостями, делами мастерской и звонком Олегу.'),
                     dict(kind='background'), dict(kind='lta', amount=5, unit='years', model_budget=6),
                     turn('Я спрашиваю о реальных изменениях в городе и о невыполненных обязательствах.')],
        'phone': [dict(kind='phone', action='Вера, какие у тебя новости? Я пока не обещаю встречу.'),
                  dict(kind='phone-group', action='Кто хочет рассказать о своих планах и новостях мастерской?'),
                  dict(kind='phone-call'), dict(kind='call-speech', action='Вера, расскажи о своих планах. Я слушаю.'),
                  dict(kind='call-end'), turn('Я занимаюсь своими фотографиями и даю другим возможность связаться со мной.'),
                  dict(kind='phone-group', action='Какие из обсуждённых дел уже сделаны? Не буду додумывать ответы за других.')],
    }
    if campaign:
        # Exercise an existing true/outdated employment fact through an actual
        # actor-owned message, rather than repeating the old hypothetical map chat.
        continuations['knowledge'] = [
            turn('Я спрашиваю Веру, что ей достоверно известно о работе Олега и откуда она это знает.'),
            dict(kind='switch', action='qa_oleg'),
            dict(kind='phone', action='Вера, сообщаю о себе: теперь я работаю в Академии двух берегов. Сведения о моей прежней работе в Мастерской карт устарели.'),
            dict(kind='switch', action='qa_kirill'),
            turn('Вера, ты узнала что-нибудь новое о работе Олега? Я спрашиваю, не предполагая ответа заранее.'),
            turn('Тимур, что тебе теперь известно о работе Олега и из чьих слов?'),
            turn('Я предлагаю уточнить публичные сведения у самого Олега. Содержание его личного письма я не спрашиваю.')]
        # Same #78 near-due fixture, not the historically contradictory born child.
        retest['family'] = [dict(kind='lta', amount=2, unit='weeks', model_budget=4),
            turn(old('family', 1)),
            turn('Я остаюсь рядом и наблюдаю, что происходит с Верой, не вмешиваясь в её действия.'),
            turn('Я продолжаю держать Веру за руку, если она этого хочет, и наблюдаю за изменениями.'),
            dict(kind='switch', action='qa_nina', seed_ref='family_remote'),
            dict(kind='lta', amount=2, unit='weeks', model_budget=4, seed_ref='family_remote'),
            dict(turn('Я, Нина, разбираю свои бумаги в библиотеке и ни с кем не связываюсь.'), seed_ref='family_remote'),
            dict(turn('Я продолжаю заниматься своими бумагами и отмечаю только то, что сама вижу.'), seed_ref='family_remote')]
        # Background intentionally releases control. Explicitly select the actor
        # before either subsequent first-person input; never infer player agency.
        operations = []
        for op in continuations['campaign']:
            if operations and operations[-1]['kind'] == 'lta' and op['kind'] == 'turn':
                operations.append(dict(kind='switch', action='qa_kirill'))
            operations.append(op)
        continuations['campaign'] = operations
    counts = {case: len(ops) for case, ops in retest.items()}
    for case, ops in retest.items():
        for op in ops: op['phase'] = 'retest'
        ops.extend(dict(op, phase='continue') for op in continuations[case])
        for op in ops: op['context_length'] = 65536 if case == 'family' else 40960
    if sum(map(len, retest.values())) > MAX_ACTIONS: raise ValueError('Plan exceeds bounded action allowance')
    return retest, counts


def prepare(parent, directory, sha, master, *, campaign=False):
    from .run import ROOT
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    qa_only(sha, sha)
    for fix in FIXES: subprocess.run(['git', 'merge-base', '--is-ancestor', fix, master], cwd=ROOT, check=True)
    if campaign:
        for fix in ('8411ed1c5d1bfeb0c8d6639ed2024d330b34541d',
                    'c1598de18f35e0b8e01a430c458211cfa86982b5',
                    '2bd13c67e03b4d861d59861987e8f836413e57a7',
                    '40bc3da23b44a025954a6b050fe71a08a2ce4a2d'):
            subprocess.run(['git', 'merge-base', '--is-ancestor', fix, master], cwd=ROOT, check=True)
    old = read(parent / 'manifest.json')
    if old.get('stage') != 'C' or old.get('followup'): raise ValueError('Choose original Stage C parent')
    baseline = rows(parent)
    if any(not row[3] for row in baseline): raise ValueError('Unknown paid outcome')
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    ledger = (parent / 'budget.sqlite').resolve()
    backup(parent / 'game.sqlite', directory / 'game.sqlite')
    backup(ledger, directory / 'budget-before.sqlite')
    repo = Repository(directory / 'game.sqlite')
    for seed in [*old['seeds'].values(), *old['extra_seeds'].values()]:
        sid = seed['save']; original = snapshot(parent / 'game.sqlite', sid)
        if snapshot(directory / 'game.sqlite', sid) != original or repo.get_snapshot(sid) != original['snapshot']:
            raise ValueError('Checkpoint migration changed canonical data')
    seeds = dict(old['seeds'])
    if campaign:
        seeds['family'] = load_fixture(repo, 'pregnancy')
    extra = dict(old['extra_seeds'], family_remote=load_fixture(repo, 'pregnancy'))
    plan, counts = plans(parent, campaign=campaign)
    (directory / 'budget.sqlite').symlink_to(ledger)
    actions = action_ledger(parent)
    related = {}
    if campaign:
        with closing(sqlite3.connect(ledger)) as db:
            allowance_parent = Path(db.execute('SELECT directory FROM stage_c_followup_authorization WHERE id=1').fetchone()[0])
        reference = read(allowance_parent / 'manifest.json')
        if not reference.get('followup') or Path(reference['ledger']).resolve() != ledger:
            raise ValueError('Missing historical followup manifest / ledger')
        related = {str(p): digest(p) for p in allowance_parent.rglob('*') if p.is_file()
                   and p.name not in ('budget.sqlite', 'run.lock') and not p.name.startswith('budget.sqlite-')}
        auth = Budget(ledger).link_stage_c_followup(directory, allowance_parent)
    else:
        auth = Budget(ledger).authorize_stage_c_followup(directory, parent)
    if actions + sum(map(len, plan.values())) > auth[2] + MAX_ACTIONS:
        raise ValueError('Plan exceeds remaining historical action allowance')
    with closing(sqlite3.connect(ledger)) as db:
        spent = db.execute('SELECT coalesce(sum(input),0)*?+coalesce(sum(output),0)*? '
                           'FROM reservations WHERE id>?', (INPUT, OUTPUT, auth[1])).fetchone()[0]
    remaining = str(Decimal(LIMIT_NUSD-spent) / Decimal(1_000_000_000))
    write(directory / 'plan.json', plan)
    with closing(sqlite3.connect(directory / 'game.sqlite')) as db:
        request_ids = [r[0] for r in db.execute('SELECT id FROM llm_requests')]
    evidence = {str(p.relative_to(parent)): digest(p) for p in parent.rglob('*') if p.is_file()
                and p.name not in ('budget.sqlite', 'run.lock') and not p.name.startswith('budget.sqlite-')}
    write(directory / 'manifest.json', dict(version=5, stage='C', followup=True, sha=sha, master_sha=master,
        created=now(), seeds=seeds, extra_seeds=extra, parent=str(parent), ledger=str(ledger),
        parent_evidence=evidence, baseline_reservations=baseline, baseline_actions=actions,
        baseline_request_ids=request_ids, authorization=list(auth), action_limit=auth[2]+MAX_ACTIONS,
        plan_hash=digest(directory / 'plan.json'), additional_usd=remaining if campaign else '2.00', retest_counts=counts,
        related_evidence=related, campaign_retest=campaign,
        reason=('Post-#231..#233 live retest using the remaining #230 allowance; no budget/action reset'
                if campaign else 'Explicit post-#220..#226 targeted live retest and Stage C continuation; preserve A/B/C spending')))
