"""Audited QA-only checkout adoption and fail-closed saved-stage recovery."""
from contextlib import closing
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess

from .budget import CONTEXT, INPUT, OUTPUT, LIMIT_NUSD, LIMIT_TOKENS, LIMIT_CALLS, MODEL, action_ledger
from .evidence import snapshot, now, write

ROOT = Path(__file__).resolve().parents[2]
FAMILY_CONTEXT = 65536  # Next UI preset above 32768, well below Flash's verified 1M.


def read(path):
    return json.loads(gzip.decompress(path.read_bytes()) if path.suffix == '.gz' else path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def qa_only(old, new):
    paths = subprocess.check_output(['git', 'diff', '--name-only', old, new], cwd=ROOT, text=True).splitlines()
    if any(not (p.startswith('devtools/live99/') or p.startswith('tests/test_live99_')
                or p.startswith('docs/manual_qa/narrative_v4/live99')) for p in paths):
        raise ValueError('Product changed; a QA-only adoption cannot authorize this checkout')
    if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=normal'], cwd=ROOT, text=True).strip():
        raise ValueError('Commit the reviewed QA changes before adoption/run')


def rows(directory):
    path = directory / 'budget.sqlite'
    if not path.is_file():
        raise ValueError('Missing original budget ledger')
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        return [list(r) for r in db.execute('SELECT id,input,output,settled FROM reservations ORDER BY id')]


def adopt(directory, manifest, sha):
    qa_only(manifest['sha'], sha)
    target = directory / 'adoptions' / (sha + '.json')
    if target.exists():
        validate_revision(directory, manifest, sha)
        return
    # Previous adoption receipts are also immutable evidence in the next receipt.
    evidence = {str(p.relative_to(directory)): digest(p) for p in directory.rglob('*')
                if p.is_file() and (p.name in ('manifest.json', 'intent.json', 'result.json',
                    'before.json.gz', 'after.json.gz', 'diagnostics.json.gz', 'verified.json')
                    or p.parent.name == 'adoptions')}
    count = action_ledger(directory)
    target.parent.mkdir(exist_ok=True)
    write(target, dict(source_sha=manifest['sha'], qa_sha=sha, at=now(), evidence=evidence,
                       reservations=rows(directory), actions=count))


def validate_revision(directory, manifest, sha):
    qa_only(manifest['sha'], sha)
    if manifest['sha'] == sha:
        return
    receipt = read(directory / 'adoptions' / (sha + '.json'))
    if receipt['source_sha'] != manifest['sha'] or receipt['qa_sha'] != sha:
        raise ValueError('Adoption identity mismatch')
    for relative, checksum in receipt['evidence'].items():
        if digest(directory / relative) != checksum:
            raise ValueError('Original evidence changed: ' + relative)
    current = {r[0]: r for r in rows(directory)}
    for original in receipt['reservations']:
        actual = current.get(original[0])
        if actual is None or (original[3] and actual != original) or (
                not original[3] and (actual[1] > original[1] or actual[2] > original[2])):
            raise ValueError('Original spending reservation lost or changed')
    if action_ledger(directory) < receipt['actions']:
        raise ValueError('Original action reservations lost')


def effective(folder):
    retries = sorted((folder / 'retries').glob('[0-9]*'))
    return retries[-1] if retries else folder


def completed(folder):
    candidate = effective(folder)
    result = candidate / 'result.json'
    if result.exists() and read(result)['status'] == 'recorded':
        return True
    verified = candidate / 'verified.json'
    if verified.exists():
        review = read(verified)
        return review['status'] == 'recorded' and all(
            digest(candidate / name) == checksum for name, checksum in review['evidence'].items())
    return False


def retry_candidate(directory, manifest, case, index, allow_pending=None):
    """Only finish a completed narrative whose Extraction was never dispatched."""
    if case != 'family':
        raise ValueError('Only the reviewed family context recovery is supported')
    folder = directory / case / f'{index:03d}'
    latest = effective(folder)
    if completed(folder) or (latest != folder and latest != allow_pending):
        raise ValueError('Already completed or a retry exists; review without another dispatch')
    intent = read(folder / 'intent.json')
    if intent['save'] != manifest['seeds'][case]['save'] or intent['kind'] not in ('turn', 'start'):
        raise ValueError('Retry identity or operation mismatch')
    before = read(folder / 'before.json.gz')
    if snapshot(directory / 'game.sqlite', intent['save']) != before:
        raise ValueError('Save changed; refusing retry')
    with closing(sqlite3.connect(directory / 'game.sqlite')) as db:
        db.row_factory = sqlite3.Row
        jobs = [dict(r) for r in db.execute('SELECT * FROM game_jobs WHERE save_id=? AND rowid>?',
                                           (intent['save'], intent['job_cursor']))]
        if len(jobs) != 1:
            raise ValueError('Expected exactly one original job')
        job = jobs[0]
        requests = [dict(r) for r in db.execute('SELECT * FROM llm_requests WHERE job_id=?', (job['id'],))]
    if job['status'] != 'error' or not job['narrative_complete'] or not job['narrative'].strip():
        raise ValueError('No completed narrative to recover')
    if job['revision'] != before['revision'] or job['user_text'] != intent['action']:
        raise ValueError('Job lineage changed')
    if not job['error'].startswith('Контекст v3 не помещается'):
        raise ValueError('Not a reviewed context overflow; hold the product failure')
    if not requests or any(r['stage'] != 'narrative' or r['status'] != 'complete' for r in requests):
        raise ValueError('A failed, unknown or already paid Extraction cannot be automatically retried')
    return folder, intent, job, [r['id'] for r in requests]


def probe_context(directory, job, context_length=FAMILY_CONTEXT):
    """Use the production builder and the recorded Narrative policies, no LLM."""
    from backend.repositories.preparation import Repository
    from backend.runtime_v3.repository import (read_history, restore_biographical_secrets,
                                                continuity_reader, relationship_reader)
    from backend.runtime_v3.milestones import reader as milestone_reader
    from backend.runtime_v3.personality import history_reader
    from backend.runtime_v3.pacing import recorded_policy
    from backend.runtime_v3.initiative import recorded_plan
    from backend.runtime_v3.continuity import recorded
    from backend.runtime_v3.protagonist import initialize
    from context_builder import build_context, estimate
    config = json.loads(job['config_json'])
    if config['provider'] != 'deepseek' or config['model'] != MODEL or not 32768 < context_length <= CONTEXT:
        raise ValueError('Unverified model or context size')
    repo = Repository(directory / 'game.sqlite')
    before = json.loads(job['memory_before_json'] or job['before_json'])
    with repo.connect() as db:
        restore_biographical_secrets(db, before)
        history, _ = read_history(db, before.get('history_head'))
    initialize(before)
    turns = repo.list_turns(job['save_id'])
    before['_resolver_turn_id'] = turns[-1]['sequence'] + 2 if turns else 1
    for name, reader in [('_milestone_query', milestone_reader), ('_development_query', history_reader),
                         ('_relationship_query', relationship_reader), ('_continuity_query', continuity_reader)]:
        history[name] = reader(repo, before.get('history_head'))
    recorded_messages = json.loads(job['context_json'])
    messages = build_context(before, turns, job['user_text'], job['kind'], context_length,
        config['update_tokens'], extraction_text=job['narrative'],
        pacing_decision=recorded_policy(recorded_messages, before['world_state']),
        initiative_decision=recorded_plan(recorded_messages), continuity_decision=recorded(recorded_messages),
        recent_turns=config.get('recent_turns', 6), prompts=config.get('_prompts'), world_history=history)
    reservations = rows(directory)
    count, inp, out = len(reservations), sum(r[1] for r in reservations), sum(r[2] for r in reservations)
    reserve_out = config['update_tokens']
    ceiling = (inp + CONTEXT) * INPUT + (out + reserve_out) * OUTPUT
    if count >= LIMIT_CALLS or inp + CONTEXT + out + reserve_out > LIMIT_TOKENS or ceiling > LIMIT_NUSD:
        raise ValueError('Insufficient remaining budget for Extraction')
    return dict(model=MODEL, context_length=context_length, input_estimate=estimate(messages),
                output_cap=reserve_out, hard_input_limit=context_length-reserve_out-256,
                conservative_usd_after_one_reservation=ceiling/1e9)
