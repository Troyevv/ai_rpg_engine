"""Read-only, content-free provenance for the selected Narrative menu."""
import json

from backend.runtime_v3 import narrative_frame
from backend.runtime_v3.suggestions import split_suggestions


def shape(rows):
    if not isinstance(rows, list):
        return None
    result = dict(rows=len(rows), spoken=0, null=0, empty=0, missing=0, invalid=0,
                  fields={}, other_fields=0)
    for row in rows:
        if not isinstance(row, dict):
            result['missing'] += 1
            continue
        for field in row:
            if field in ('text', 'action', 'speech', 'facts', 'interaction_channel'):
                result['fields'][field] = result['fields'].get(field, 0) + 1
            else:
                result['other_fields'] += 1
        if 'speech' not in row:
            result['missing'] += 1
        elif row['speech'] is None:
            result['null'] += 1
        elif isinstance(row['speech'], str):
            result['spoken' if row['speech'].strip() else 'empty'] += 1
        else:
            result['invalid'] += 1
    return result


def inspect_choices(db, save_id, turn_id, variant):
    # All stages refer to this active variant, including after rollback or regeneration.
    db.execute('BEGIN')
    turn = db.execute("""SELECT t.sequence,t.kind,t.choices_json,v.job_id,v.created_at,
        json_extract(v.payload,'$.choices_json') AS variant_choices,
        j.config_json,j.context_json,j.replaces_id
        FROM turns t JOIN response_variants v ON t.active_variant_id=v.id AND v.save_id=t.save_id
        LEFT JOIN game_jobs j ON j.id=v.job_id
        WHERE t.save_id=? AND t.id=? AND v.id=?""", (save_id, turn_id, variant)).fetchone()
    if not turn:
        return None
    config = json.loads(turn['config_json'] or '{}')
    recovery = config.get('_narrative_recovery') or {}
    job_id = recovery.get('source_job_id') or turn['job_id']
    stage = 'long_term_narrative' if turn['kind'] == 'long_term' else 'narrative'
    receipt = db.execute("""SELECT response_text,context_json,diagnostics_json FROM llm_requests
        WHERE job_id=? AND save_id=? AND stage=? AND status='complete' ORDER BY rowid DESC LIMIT 1""",
                         (job_id, save_id, stage)).fetchone()
    messages = json.loads((receipt['context_json'] if receipt else turn['context_json']) or '[]')
    frame = config.get('_authored_frame') or {}
    raw_rows = None
    wire_format = None
    contract = None
    generating_build = None
    if stage == 'narrative':
        contract = narrative_frame.contract_id(messages)
    if receipt:
        diagnostics = json.loads(receipt['diagnostics_json'] or '{}')
        generating_build = diagnostics.get('backend_build')
        raw = receipt['response_text']
        if raw and stage == 'narrative':
            decoded = narrative_frame.read(raw, complete=True)
            if decoded:
                raw_rows = decoded[1].get('actions')
                wire_format = 'scene/actions'
            else:
                _, trailer = split_suggestions(raw, complete=True, verbatim=True)
                raw_rows = trailer or None
                wire_format = 'action_suggestions' if trailer else 'prose'
        elif raw and stage == 'long_term_narrative':
            try:
                wire = json.loads(raw)
            except ValueError:
                wire = None
            if isinstance(wire, dict) and 'arrival' in wire:
                wire_format, raw_rows = 'arrival/actions', wire.get('actions')
                contract = (narrative_frame.SPEECH_CONTRACT_ID if any(
                    narrative_frame.EXPLICIT_FORMAT in m.get('content','') for m in messages)
                            else 'narrative-actions/1')
    stored = json.loads(turn['choices_json'])
    branch = json.loads(turn['variant_choices'] or 'null')
    return dict(turn=turn_id, sequence=turn['sequence'], variant=variant, kind=turn['kind'],
                created_at=turn['created_at'], regenerated=turn['replaces_id'] is not None,
                recovered=bool(recovery), contract=contract, generating_build=generating_build,
                wire_format=wire_format, raw=shape(raw_rows),
                checkpoint=shape(frame.get('actions') if frame else config.get('_narrative_suggestions') or None),
                published=(config.get('_published_scene') or {}).get('choices'),
                saved_variant=shape(branch), saved_turn=shape(stored),
                same_saved_choices=branch == stored if branch is not None else None)
