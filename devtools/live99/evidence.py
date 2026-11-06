import gzip
import hashlib
import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from backend.runtime_v3.models import assert_world_state_v3_invariants


def now():
    return datetime.now(timezone.utc).isoformat()


def write(path, value):
    raw = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode()
    tmp = path.with_suffix('.part')
    with tmp.open('wb') as out:
        out.write(gzip.compress(raw) if path.suffix == '.gz' else raw)
        out.flush()
        os.fsync(out.fileno())
    tmp.replace(path)


def snapshot(path, sid):
    # Keep raw evidence even if the production validator rejects this save.
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN')
        rev, raw = db.execute('SELECT revision,state_json FROM saves WHERE id=?', (sid,)).fetchone()
        snap = json.loads(raw)
        turn = db.execute('SELECT id,sequence,kind,user_text,assistant_text,active_variant_id,changes_json '
                          'FROM turns WHERE save_id=? ORDER BY sequence DESC LIMIT 1', (sid,)).fetchone()
        history = db.execute('SELECT id,parent_id,payload_json FROM world_history_v3 WHERE id=?',
                             (snap.get('history_head'),)).fetchone()
        # Timing can legitimately finalize after commit. Hash the immutable variant
        # content without that presentation metadata.
        variants = db.execute("SELECT id,json_remove(payload,'$.timing_json') FROM response_variants WHERE save_id=?",
                              (sid,))
        siblings = {key: hashlib.sha256(payload.encode()).hexdigest() for key, payload in variants}
        return dict(revision=rev, snapshot=snap, last_turn=dict(turn) if turn else None,
                    history=dict(history) if history else None, variants=siblings)


def diagnostics(path, sid, cursor):
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        jobs = [dict(row) for row in db.execute('''SELECT id,status,error,kind,narrative,
            repair_diagnostics_json,warnings_json FROM game_jobs WHERE save_id=? AND rowid>?''', (sid, cursor))]
        for job in jobs:
            job['requests'] = [dict(r) for r in db.execute('''SELECT id,stage,provider,model,status,
                input_tokens,output_tokens,cached_input_tokens,cost_usd,finish_reason,response_text,
                diagnostics_json FROM llm_requests WHERE job_id=? ORDER BY rowid''', (job['id'],))]
        return jobs


def oracle(before, after, projection, kind):
    old, new = before['snapshot'], after['snapshot']
    assert_world_state_v3_invariants(new['world_state'])
    if projection['revision'] != after['revision']:
        raise ValueError('Projection revision differs from the persisted save')
    if projection['state']['controlled_actor_id'] != new['world_state']['camera']['controlled_actor_id']:
        raise ValueError('UI projection has a different controlled actor')
    if new.get('history_head') and after['history'] is None:
        raise ValueError('Missing current History node')
    if any(after['variants'].get(k) != v for k, v in before['variants'].items()):
        raise ValueError('A prior variant disappeared or changed')
    if kind == 'reload':
        if before != after:
            raise ValueError('Reload changed persistent state')
        return
    if after['revision'] <= before['revision']:
        raise ValueError('No committed revision')
    if kind not in ('regenerate', 'variant', 'rollback'):
        if new['world_state']['meta']['world_time'] < old['world_state']['meta']['world_time']:
            raise ValueError('World time went backwards')
    if kind in ('start', 'turn', 'regenerate'):
        last = after['last_turn']
        if not last or not any(t['id'] == last['id'] and t['active_variant_id'] == last['active_variant_id']
                               for t in projection['turns']):
            raise ValueError('Projected turn or active variant differs from canonical turn')
        previous = before['last_turn']
        expected = (previous['sequence'] if previous else 0) + (kind != 'regenerate')
        if last['sequence'] != expected or not last['assistant_text'].strip():
            raise ValueError('Wrong sequence or empty committed scene')


def delta(before, after):
    """Canonical IDs that changed, with the exact values in the two snapshots."""
    old, new = (x['snapshot']['world_state'] for x in (before, after))
    result = {}
    for section in old.keys() | new.keys():
        a, b = old.get(section), new.get(section)
        if a != b:
            result[section] = sorted(k for k in a.keys() | b.keys() if a.get(k) != b.get(k)) \
                if isinstance(a, dict) and isinstance(b, dict) else True
    return result


def scenario_checks(case, before, after, projection):
    state = after['snapshot']['world_state']
    ui = projection['state']
    if ui['world_clock']['minute'] != state['meta']['world_time']:
        raise ValueError('Player calendar disagrees with the canonical clock')
    if case == 'crisis' and state['characters']['qa_pavel']['life_status'] != 'dead':
        raise ValueError('Deceased QA character lost canonical death state')
    if case == 'family':
        for pregnancy in before['snapshot']['world_state']['pregnancies'].values():
            if pregnancy['status'] != 'born':
                continue
            for slot in pregnancy['children']:
                cid = slot['id']
                character = state['characters'][cid]
                if character['birth_date'] != before['snapshot']['world_state']['characters'][cid]['birth_date']:
                    raise ValueError('Recorded birthday changed')
                parents = {row['source_id'] for row in state['objective_relations'].values()
                           if row['kind'] == 'parent' and row['target_id'] == cid}
                if parents != set(pregnancy['parent_ids']):
                    raise ValueError('Birth no longer has its original parent links')
    if case == 'knowledge' and after['history']:
        from backend.runtime_v3.history import audit_world_history
        history = json.loads(after['history']['payload_json'])
        if audit_world_history(history):
            raise ValueError('History provenance requires review')
