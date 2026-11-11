"""Fail closed *before* dispatch, including repair, continuation and concurrent calls."""
import inspect
import sqlite3
import json
import os
from pathlib import Path
from functools import wraps

MODEL = 'deepseek-flash'
# Reserve the entire provider context window, even if our prompt estimator is wrong.
CONTEXT = 1_048_576
LIMIT_TOKENS = 3_000_000
LIMIT_CALLS = 320
# Integer nano-USD per token: maximum (peak, cold input), verified 2026-11-06.
INPUT, OUTPUT = 300, 1200
LIMIT_NUSD = 2_000_000_000


def action_ledger(directory):
    """Import old intents once; reservations survive missing files and restarts."""
    path = directory / 'budget.sqlite'
    if not path.is_file():
        raise ValueError('Missing original budget ledger')
    with sqlite3.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='qa_actions'").fetchone()
        if not exists:
            db.execute('CREATE TABLE qa_actions(path TEXT PRIMARY KEY, intent TEXT NOT NULL)')
            for intent in sorted(directory.rglob('intent.json')):
                # Includes archived unsubmitted attempts and retry attempts.
                db.execute('INSERT INTO qa_actions VALUES(?,?)',
                           (str(intent.parent.relative_to(directory)), intent.read_text()))
        return db.execute('SELECT count(*) FROM qa_actions').fetchone()[0]


def reserve_action(directory, folder, meta, limit):
    action_ledger(directory)
    with sqlite3.connect(directory / 'budget.sqlite') as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT count(*) FROM qa_actions').fetchone()[0] >= limit:
            raise RuntimeError('QA cumulative action budget exhausted')
        copied_retest = db.execute("SELECT 1 FROM sqlite_master WHERE name='postfix_authorization'").fetchone()
        db.execute('INSERT INTO qa_actions VALUES(?,?)',
                   (str(folder.resolve()) if copied_retest or (directory / 'budget.sqlite').is_symlink()
                    else str(folder.relative_to(directory)), json.dumps(meta, ensure_ascii=False)))


class Budget:
    def __init__(self, path, stage_b=None, *, stage_c=None, stage_c_followup=False):
        if stage_b and stage_c:
            raise ValueError('Choose exactly one paid stage')
        self.path = path
        self.stage_b = str(stage_b.resolve()) if stage_b else None
        self.stage_c = str(stage_c.resolve()) if stage_c else None
        if stage_c_followup and not stage_c:
            raise ValueError('A followup requires its Stage C directory')
        self.stage_c_followup = stage_c_followup
        self.run_directory = self.stage_c or self.stage_b
        with sqlite3.connect(path) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS reservations
                (id INTEGER PRIMARY KEY, input INTEGER, output INTEGER, settled INTEGER DEFAULT 0)''')
            db.execute('CREATE TABLE IF NOT EXISTS spending_caps (name TEXT PRIMARY KEY, ceiling INTEGER NOT NULL)')

    def authorize_stage_b(self, directory):
        return self._authorize(directory, 'B')

    def authorize_stage_c(self, directory):
        return self._authorize(directory, 'C')

    def authorize_stage_c_followup(self, directory, parent):
        with sqlite3.connect(self.path) as db:
            original = db.execute('SELECT directory FROM stage_c_authorization WHERE id=1').fetchone()
        if original != (str(parent.resolve()),):
            raise ValueError('Followup must retain the original Stage C ledger')
        return self._authorize(directory, 'C_followup')

    def link_stage_c_followup(self, directory, parent):
        """Use the remaining authorization in an isolated retest, never renew it."""
        directory, parent = str(directory.resolve()), str(parent.resolve())
        with sqlite3.connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT directory,baseline_id,baseline_actions FROM stage_c_followup_authorization WHERE id=1').fetchone()
            if not row or row[0] != parent or directory == parent:
                raise ValueError('Choose the original authorized followup parent')
            if db.execute('SELECT count(*) FROM reservations WHERE settled=0').fetchone()[0]:
                raise ValueError('Unknown paid outcome; cannot link a retest')
            db.execute('CREATE TABLE IF NOT EXISTS stage_c_followup_link '
                       '(directory TEXT PRIMARY KEY, parent TEXT UNIQUE NOT NULL)')
            prior = db.execute('SELECT directory,parent FROM stage_c_followup_link').fetchall()
            if prior and prior != [(directory, parent)]:
                raise ValueError('Followup continuation already linked; allowance cannot renew')
            db.execute('INSERT OR IGNORE INTO stage_c_followup_link VALUES(?,?)', (directory, parent))
            return directory, row[1], row[2]

    def _authorize(self, directory, stage):
        """One explicit authorization per stage; retest shares its stage's allowance."""
        directory = str(directory.resolve())
        table = {'B': 'stage_b_authorization', 'C': 'stage_c_authorization',
                 'C_followup': 'stage_c_followup_authorization'}[stage]
        with sqlite3.connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute(f'''CREATE TABLE IF NOT EXISTS {table}
                (id INTEGER PRIMARY KEY CHECK(id=1), directory TEXT NOT NULL,
                 baseline_id INTEGER NOT NULL, baseline_actions INTEGER NOT NULL)''')
            prior = db.execute(f'SELECT directory,baseline_id,baseline_actions FROM {table}').fetchone()
            if prior:
                if prior[0] != directory:
                    raise ValueError(f'Stage {stage} already belongs to another run; allowance cannot renew')
                return prior
            if db.execute('SELECT count(*) FROM reservations WHERE settled=0').fetchone()[0]:
                raise ValueError(f'Unknown paid outcome; Stage {stage} cannot start')
            baseline = db.execute('SELECT coalesce(max(id),0) FROM reservations').fetchone()[0]
            actions = db.execute('SELECT count(*) FROM qa_actions').fetchone()[0]
            db.execute(f'INSERT INTO {table} VALUES(1,?,?,?)', (directory, baseline, actions))
            return directory, baseline, actions

    def stage_b_baseline(self, db):
        return self.phase_baseline(db)

    def phase_baseline(self, db):
        table = ('stage_c_followup_authorization' if self.stage_c_followup else
                 'stage_c_authorization' if self.stage_c else 'stage_b_authorization')
        row = db.execute(f'SELECT directory,baseline_id,baseline_actions FROM {table} WHERE id=1').fetchone()
        if row and row[0] != self.run_directory and self.stage_c_followup:
            exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='stage_c_followup_link'").fetchone()
            link = db.execute('SELECT parent FROM stage_c_followup_link WHERE directory=?',
                              (self.run_directory,)).fetchone() if exists else None
            if link == (row[0],):
                row = (self.run_directory, row[1], row[2])
        if not row or row[0] != self.run_directory:
            raise ValueError('Missing or mismatched paid stage authorization')
        return row

    def cap_additional(self, name, allowance):
        """Persist once in the shared ledger; restarting cannot renew an allowance."""
        if type(allowance) is not int or not 0 < allowance <= LIMIT_NUSD:
            raise ValueError('Invalid additional allowance')
        with sqlite3.connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            previous = db.execute('SELECT ceiling FROM spending_caps WHERE name=?', (name,)).fetchone()
            if previous:
                return previous[0]
            spent = db.execute('SELECT coalesce(sum(input),0)*?+coalesce(sum(output),0)*? '
                               'FROM reservations', (INPUT, OUTPUT)).fetchone()[0]
            ceiling = min(LIMIT_NUSD, spent + allowance)
            db.execute('INSERT INTO spending_caps VALUES(?,?)', (name, ceiling))
            return ceiling

    def reserve(self, max_tokens):
        if type(max_tokens) is not int or not 0 < max_tokens <= 32000:
            raise ValueError('Missing or excessive output cap')
        with sqlite3.connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            baseline = self.phase_baseline(db)[1] if self.run_directory else 0
            if self.run_directory and db.execute('SELECT count(*) FROM reservations WHERE settled=0').fetchone()[0]:
                raise RuntimeError('Unknown paid outcome; stop before another dispatch')
            count, inp, out = db.execute(
                'SELECT count(*), coalesce(sum(input),0), coalesce(sum(output),0) FROM reservations WHERE id>?',
                (baseline,)
            ).fetchone()
            inp += CONTEXT
            out += max_tokens
            cap = db.execute('SELECT min(ceiling) FROM spending_caps').fetchone()[0]
            ceiling = LIMIT_NUSD if self.run_directory else min(LIMIT_NUSD, cap if cap is not None else LIMIT_NUSD)
            # Each explicitly authorized stage bounds tokens at peak/cold prices.
            token_limit = LIMIT_NUSD // INPUT if self.run_directory else LIMIT_TOKENS
            if count >= LIMIT_CALLS or inp + out > token_limit or inp * INPUT + out * OUTPUT > ceiling:
                raise RuntimeError('QA request, token or USD budget exhausted')
            return db.execute('INSERT INTO reservations(input,output) VALUES(?,?)',
                              (CONTEXT, max_tokens)).lastrowid

    def settle(self, rid, usage):
        # No receipt (timeout / interrupted process) => retain full reservation across restarts.
        if not isinstance(usage, dict):
            return
        inp, out = usage.get('prompt_tokens'), usage.get('completion_tokens')
        if any(type(n) is not int or n < 0 for n in (inp, out)):
            return
        with sqlite3.connect(self.path) as db:
            db.execute('UPDATE reservations SET input=?,output=?,settled=1 WHERE id=? AND input>=? AND output>=?',
                       (inp, out, rid, inp, out))

    def wrap(self, stream):
        signature = inspect.signature(stream)

        @wraps(stream)
        def guarded(*args, **kwargs):
            params = signature.bind(*args, **kwargs)
            params.apply_defaults()
            p = params.arguments
            if p['provider'] != 'deepseek' or p['model'] != MODEL:
                raise ValueError('QA allows only the verified DeepSeek model')
            rid = self.reserve(p['max_tokens'])
            consumer = p['on_usage']

            usage_receipt = None

            def receipt(usage):
                nonlocal usage_receipt
                usage_receipt = usage
                if consumer:
                    consumer(usage)

            p['on_usage'] = receipt
            audit = None
            complete = False
            def record(value):
                if audit:
                    audit.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n')
                    audit.flush()
                    os.fsync(audit.fileno())
            try:
                if self.run_directory:
                    # Preserve paid chunks independently of the production tracker;
                    # never serialize credentials/callbacks.
                    folder = Path(self.run_directory) / 'provider-streams'
                    folder.mkdir(parents=True, exist_ok=True)
                    audit = (folder / f'{rid:06d}.jsonl').open('x', encoding='utf-8')
                    record(dict(event='request', reservation_id=rid, **{
                        k: p[k] for k in ('provider', 'model', 'messages', 'max_tokens',
                                         'temperature', 'thinking', 'response_format') if k in p}))
                for chunk in stream(**p):
                    record(dict(event='chunk', text=chunk))
                    yield chunk
                self.settle(rid, usage_receipt)
                complete = True
            finally:
                if audit:
                    try:
                        record(dict(event='end', complete=complete, usage=usage_receipt))
                    finally:
                        audit.close()

        return guarded
