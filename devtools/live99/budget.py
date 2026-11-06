"""Fail closed *before* dispatch, including repair, continuation and concurrent calls."""
import inspect
import sqlite3
import json
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
        db.execute('INSERT INTO qa_actions VALUES(?,?)',
                   (str(folder.relative_to(directory)), json.dumps(meta, ensure_ascii=False)))


class Budget:
    def __init__(self, path):
        self.path = path
        with sqlite3.connect(path) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS reservations
                (id INTEGER PRIMARY KEY, input INTEGER, output INTEGER, settled INTEGER DEFAULT 0)''')

    def reserve(self, max_tokens):
        if type(max_tokens) is not int or not 0 < max_tokens <= 32000:
            raise ValueError('Missing or excessive output cap')
        with sqlite3.connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            count, inp, out = db.execute(
                'SELECT count(*), coalesce(sum(input),0), coalesce(sum(output),0) FROM reservations'
            ).fetchone()
            inp += CONTEXT
            out += max_tokens
            if count >= LIMIT_CALLS or inp + out > LIMIT_TOKENS or inp * INPUT + out * OUTPUT > LIMIT_NUSD:
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
            yield from stream(**p)
            self.settle(rid, usage_receipt)

        return guarded
