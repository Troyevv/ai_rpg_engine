"""Synthetic diagnostic replay using existing E5 import/API/job fixtures.
Usage: python issue134_replay.py BASE_CHECKOUT OUTPUT.json
The checkout owns Runtime; this script supplies only provider responses.
"""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
root = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(root), str(root/'tests')]
from fastapi.testclient import TestClient
from backend.api.app import create_app
from test_runtime_handoff import imported, submit, arrival, wait_job, snapshot_state
text = ('В замке поворачивается ключ, дверь приоткрывается на ладонь. '
        'Виктория стоит в проёме, в куртке поверх рабочего фартука, с сумкой на плече; '
        'за её спиной пустой коридор и наполовину погашенные лампы. '
        'Она смотрит на разбросанные бумаги на столе, потом на Илью — и не спешит уходить')
results=[]
for case in ('unsupported_inside', 'contextual_entry'):
    with TemporaryDirectory() as tmp:
        app=create_app(Path(tmp)/'replay.sqlite')
        with TestClient(app) as client:
            sid=imported(client);repo=app.state.repository
            before=repo.get_snapshot(sid);stored=snapshot_state(repo,sid)
            narrative=text if case=='unsupported_inside' else 'Виктория Соловьёва открыла дверь и вошла внутрь. Илья поднял голову.'
            raw=arrival(evidence=narrative)
            raw['movements'][0].update(actor_evidence='Виктория' if case=='unsupported_inside' else 'Виктория Соловьёва',
                destination_evidence='в проёме' if case=='unsupported_inside' else 'внутрь')
            if case=='contextual_entry':raw['movements'][0].update(destination_reference='camera_location',anchor_location_id='ilya_cabinet')
            def provider(**kw):yield json.dumps(raw,ensure_ascii=False) if kw.get('response_format') else narrative
            with patch('engine.chat_stream',side_effect=provider):
                jid=submit(client,sid);job=wait_job(client,jid)
            record=repo.get_job(jid)
            results.append(dict(case=case,source='SYNTHETIC provider payload; not original user job',
                before_camera=before['world_state']['camera'],actor_origin=before['world_state']['characters']['viktoria_solovyova']['location_id'],
                narrative=narrative,raw_extraction=raw,status=job['status'],error=job.get('error'),
                repairs=json.loads(record['repair_diagnostics_json']),canonical_unchanged=snapshot_state(repo,sid)==stored,
                committed_turns=len(repo.list_turns(sid))))
Path(sys.argv[2]).write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
