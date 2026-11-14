"""Offline #254 replay on immutable original SQLite checkpoints; no provider IO.

python -m devtools.live99.replay_acceptance254 ARCHIVE_ROOT OUTPUT_DIRECTORY
Original replies and explicitly authored birth control are reported separately.
The paired path mirrors #252: real resolver + atomic Repository.commit_job,
not a claim to have run new Extraction or a full background-enabled HTTP turn.
"""
import argparse
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sqlite3
import gzip
from unittest.mock import patch

from backend.repositories.preparation import Repository
from backend.runtime_v3.player_actions import resolver_options
from backend.runtime_v3.raw import RawTurnResult
from backend.runtime_v3.repository import read_history, relationship_reader
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.milestones import reader as milestone_reader
from backend.runtime_v3.personality import history_reader
from backend.services.npc_review import publish_cards
from backend.services.world_delta_errors import StructuralDeltaError


def replay(root, output, name, *, birth_control=False):
    case = json.loads((root/'cases'/name/'case.json').read_text())
    source = root/'cases'/name/'checkpoint.sqlite'
    with source.open('rb') as f: digest = hashlib.file_digest(f, 'sha256').hexdigest()
    dest = output/(name+('-authored' if birth_control else '')+'.sqlite')
    with sqlite3.connect(f'file:{source.resolve()}?mode=ro', uri=True) as src, sqlite3.connect(dest) as dst:
        src.backup(dst)
    repo = Repository(dest); sid = case['save_id']; before = repo.get_snapshot(sid)
    with repo.connect() as db: old_history = read_history(db,before['history_head'])[0]
    config = dict(model='test',context_length=131072,max_tokens=2400,update_tokens=8192)
    jid = repo.begin_job(sid,case['player_input'],'turn',config)
    repo.job_progress(jid,'extracting',narrative=case['narrative'],complete=True)
    attempts = []; resolved = None
    paths = sorted((root/'comparison'/name/'v5').glob('attempt-*.json'))
    for path in (paths[:1] if birth_control else paths):
        payload = json.loads(json.loads(path.read_text())['response'])
        if birth_control:
            payload['births'][0]['sex_observations'][0]['source_assertion'] = 'direct_observation'
        raw = RawTurnResult.parse(payload); selection = case['selection']['5']
        resolver = StateResolver(before['world_state'],case['narrative'],case['player_input'],
            **resolver_options(before['world_state'],case['player_input'],contract_version=5),
            chronology_events=case['world_history'].get('events',[]),
            pacing_decision=selection.get('pacing'),initiative_decision=selection.get('initiative'),
            continuity_decision=selection.get('continuity'),
            relationship_query=relationship_reader(repo,before.get('history_head')),
            milestone_query=milestone_reader(repo,before.get('history_head')),
            development_query=history_reader(repo,before.get('history_head')),
            actor_names={c['id']:c['name'] for c in before['character_cards']})
        try:
            resolved = resolver.resolve(raw)
            attempts.append(dict(source=str(path.relative_to(root)),status='accepted',warnings=resolved.warnings))
            break
        except StructuralDeltaError as exc:
            attempts.append(dict(source=str(path.relative_to(root)),status='rejected',diagnostics=exc.diagnostics('offline')))
            if not exc.repairable: break
    if resolved:
        after = deepcopy(before); after['world_state'] = resolved.state; publish_cards(after,resolved)
        repo.job_progress(jid,'validating')
        repo.commit_job(jid,after,resolved.choices,dict(raw_turn_result=asdict(raw),state_patch=asdict(resolved.patch)),history_batch=resolved.history)
        assert Repository(dest).get_snapshot(sid)['world_state'] == resolved.state
        with repo.connect() as db:
            new_history = read_history(db,repo.get_snapshot(sid)['history_head'])[0]
            assert all(new_history[k][:len(rows)] == rows for k,rows in old_history.items())
        outcomes = dict(movements=resolved.history['movements'],
            knowledge_acquisitions=resolved.history['knowledge_acquisitions'],
            pregnancy_status={k:v['status'] for k,v in resolved.state['pregnancies'].items()},
            new_character_ids=sorted(set(resolved.state['characters'])-set(before['world_state']['characters'])))
        repo.rollback_last(sid)
        assert repo.get_snapshot(sid)['world_state'] == before['world_state']
    else:
        repo.job_progress(jid,'error',error='Offline original reply rejected')
        assert Repository(dest).get_snapshot(sid) == before
        outcomes = {}
    with repo.connect() as db: assert db.execute('pragma integrity_check').fetchone()[0] == 'ok'
    with source.open('rb') as f: assert hashlib.file_digest(f,'sha256').hexdigest() == digest
    return dict(case=name,authored_control=birth_control,attempts=attempts,outcomes=outcomes,
                reload='PASS',atomicity='PASS',source_sha256=digest,paid_calls=0)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    names=json.loads((args.archive/'manifest.json').read_text())['cases']
    results=[]
    for name in names:
        row=replay(args.archive,args.output,name);results.append(row)
        print(name,row['attempts'][-1]['status'],flush=True)
    results.append(replay(args.archive,args.output,'family_birth',birth_control=True))
    for mode in ('original', 'causes_only_counterfactual', 'authored_hypothetical'):
        results.append(replay_lta(args.archive,args.output,mode))
    (args.output/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))


def replay_lta(root, output, mode):
    import engine
    folder = root/'play/turns/L1b'
    source = folder/'checkpoint.sqlite'; dest = output/('lta-'+mode+'.sqlite')
    with source.open('rb') as f: digest=hashlib.file_digest(f,'sha256').hexdigest()
    with sqlite3.connect(f'file:{source.resolve()}?mode=ro',uri=True) as src, sqlite3.connect(dest) as dst:
        src.backup(dst)
    repo=Repository(dest); sid=json.loads((folder/'intent.json').read_text())['save']
    target=json.loads(gzip.decompress((folder/'before.json.gz').read_bytes()))['snapshot']
    for _ in range(4):
        if repo.get_snapshot(sid) == target: break
        repo.rollback_last(sid)
    before=repo.get_snapshot(sid)
    assert before == target, 'Original LTA before snapshot was not restored exactly'
    rows=json.loads(gzip.decompress((folder/'requests.json.gz').read_bytes()))
    responses=[rows[0]['response_text']]+[r['response_text'] for r in rows[1:]]
    if mode != 'original':
        payload=json.loads(responses[2])
        payload['information_events'][0]['advance_candidate_ids']=['advance_62b4bd97a0ff73d86fdb']
        if mode == 'authored_hypothetical':
            # Explicit authored interpretation of the original conditional question,
            # NOT evidence that the model learned to avoid broad secret disclosure.
            payload['information_events']=[];payload['secret_disclosures']=[]
            payload['events'][0]['text']='Тамара спрашивает, будет ли Виктор отвечать на письмо; автор и семейные обстоятельства не сообщены.'
        responses=[responses[0],json.dumps(payload,ensure_ascii=False)]
    calls=[];answers=iter(responses)
    def stream(**kwargs):
        calls.append(kwargs)
        return iter([next(answers)])
    config=dict(model='test',context_length=131072,max_tokens=2400,update_tokens=8192,
        long_term_advance=dict(amount=2,unit='weeks',max_llm_calls=len(responses)))
    jid=repo.begin_job(sid,'','long_term',config)
    # Preserve the original selected group and Narrative request, independently
    # of local semantic-retrieval availability. Extraction is rebuilt normally.
    original_job=json.loads((folder/'job-record.json').read_text())
    with repo.connect() as db:
        db.execute('UPDATE game_jobs SET context_json=? WHERE id=?', (original_job['context_json'],jid))
    with patch('engine.find_loaded_model',return_value={'config':{}}),patch('engine.chat_stream',side_effect=stream):
        engine.run_job(repo.path,jid,engine.Worker())
    job=repo.get_job(jid);after=Repository(dest).get_snapshot(sid)
    assert job['status']=='saved',job['error']
    secret='char_tamara:fact_viktor_letter'
    gained=secret not in before['world_state']['knowledge'] and secret in after['world_state']['knowledge']
    if mode != 'causes_only_counterfactual': assert not gained
    with repo.connect() as db: assert db.execute('pragma integrity_check').fetchone()[0]=='ok'
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)['world_state']==before['world_state']
    with source.open('rb') as f: assert hashlib.file_digest(f,'sha256').hexdigest()==digest
    result=dict(case='lta',mode=mode,job_status=job['status'],full_secret_gained=gained,
        report=after['last_long_term_advance'],diagnostics=json.loads(job['repair_diagnostics_json'] or '[]'),
        reload='PASS',rollback='PASS',source_sha256=digest,paid_calls=0)
    print('lta',mode,'full_secret_gained',gained,flush=True)
    return result


if __name__ == '__main__': main()
