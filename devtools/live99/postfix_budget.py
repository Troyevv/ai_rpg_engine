"""Approved #245 subrun on a COPY of #239's settled ledger. No budget renewal.

Reuse Budget's stream audit and settlement. Reserve both the inherited allowance
and the new 36-call/$0.60 sublimit atomically, including all provider stages.
"""
import json
import sqlite3
from pathlib import Path

from .budget import Budget, CONTEXT, INPUT, OUTPUT, LIMIT_CALLS, LIMIT_NUSD


def authorize_copy(directory, *, historical_baseline, historical_rows):
    """Called only after explicit approval; never modify the source ledger."""
    directory = Path(directory).resolve()
    path = directory / 'budget.sqlite'
    if path.is_symlink() or not path.is_file():
        raise ValueError('A physical ledger copy is required')
    with sqlite3.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        rows = db.execute('SELECT * FROM reservations ORDER BY id').fetchall()
        if rows != [tuple(r) for r in historical_rows] or any(not r[3] for r in rows):
            raise ValueError('Historical reservations changed or unknown outcome')
        inherited = db.execute('SELECT baseline_id FROM stage_c_followup_authorization WHERE id=1').fetchone()
        if inherited != (historical_baseline,):
            raise ValueError('Historical authorization baseline mismatch')
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='postfix_authorization'").fetchone():
            raise ValueError('Retest already authorized; never reset on resume')
        db.execute('CREATE TABLE postfix_authorization (id INTEGER PRIMARY KEY CHECK(id=1), '
                   'directory TEXT NOT NULL, baseline_id INTEGER NOT NULL, historical_baseline INTEGER NOT NULL, '
                   'max_calls INTEGER NOT NULL, max_nusd INTEGER NOT NULL, historical_rows TEXT NOT NULL)')
        db.execute('INSERT INTO postfix_authorization VALUES(1,?,?,?,?,?,?)',
                   (str(directory), rows[-1][0] if rows else 0, historical_baseline,
                    36, 600_000_000, json.dumps(rows)))


class PostfixBudget(Budget):
    def __init__(self, directory):
        directory = Path(directory).resolve()
        path = directory / 'budget.sqlite'
        if path.is_symlink() or not path.is_file():
            raise ValueError('A physical ledger copy is required')
        # Preserve historical authorization/link tables; no path rebinding.
        super().__init__(path, stage_c=directory, stage_c_followup=True)

    def reserve(self, max_tokens):
        if type(max_tokens) is not int or not 0 < max_tokens <= 32000:
            raise ValueError('Missing or excessive output cap')
        with sqlite3.connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            auth = db.execute('SELECT directory,baseline_id,historical_baseline,max_calls,max_nusd,historical_rows '
                              'FROM postfix_authorization WHERE id=1').fetchone()
            if not auth or auth[0] != self.run_directory or auth[3:5] != (36, 600_000_000):
                raise ValueError('Missing or changed explicit retest authorization')
            prefix = db.execute('SELECT * FROM reservations WHERE id<=? ORDER BY id', (auth[1],)).fetchall()
            if prefix != [tuple(r) for r in json.loads(auth[5])]:
                raise ValueError('Historical ledger prefix changed')
            inherited = db.execute('SELECT baseline_id FROM stage_c_followup_authorization WHERE id=1').fetchone()
            if inherited != (auth[2],):
                raise ValueError('Historical authorization changed')
            if db.execute('SELECT count(*) FROM reservations WHERE settled=0').fetchone()[0]:
                raise RuntimeError('Unknown paid outcome; stop before another dispatch')
            for baseline, calls, ceiling in ((auth[2], LIMIT_CALLS, LIMIT_NUSD),
                                             (auth[1], auth[3], auth[4])):
                count, inp, out = db.execute('SELECT count(*),coalesce(sum(input),0),coalesce(sum(output),0) '
                                            'FROM reservations WHERE id>?', (baseline,)).fetchone()
                if (count >= calls or (inp + CONTEXT) * INPUT + (out + max_tokens) * OUTPUT > ceiling
                        or baseline == auth[2] and inp + out + CONTEXT + max_tokens > LIMIT_NUSD // INPUT):
                    raise RuntimeError('QA request, token or USD budget exhausted')
            return db.execute('INSERT INTO reservations(input,output) VALUES(?,?)',
                              (CONTEXT, max_tokens)).lastrowid
