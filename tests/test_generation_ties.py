import json
from copy import deepcopy
from itertools import combinations
from unittest.mock import patch

import pytest
from backend.services import generation_ties as ties
from backend.services.initial_world_stages import TiesPart
from backend.services.generation_contracts import request_schema
from llm import OutputLimitReached
from test_api import api
from test_world_blueprint import creative_provider, submit
from test_world_generation import wait


def registry(n):
    return [dict(id=f'actor_{i:03d}',name=str(i),kind='character') for i in range(n)]


@pytest.mark.parametrize('size',[2,7,30,100])
def test_large_cast_pairs_are_bounded_complete_disjoint_and_order_independent(size):
    people=registry(size); groups=ties.batches(people)
    pairs=[tuple(p) for b in groups for p in b['pairs']]
    assert len(pairs)==len(set(pairs))==size*(size-1)//2
    assert set(pairs)==set(combinations(sorted(r['id'] for r in people),2))
    assert all(1<=len(b['pairs'])<=6 for b in groups)
    assert ties.batches(list(reversed(people)))==groups
    for group in groups:
        context=ties.context(dict(registry=people,people=people,places={'unneeded':'large'},constraints=['explicit']),group)
        assert 'places' not in context and context['constraints']==['explicit']
        assert {r['id'] for r in context['people']}=={cid for pair in group['pairs'] for cid in pair}


def test_directed_adoption_and_feelings_are_not_inverted_or_propagated():
    people=registry(7); group=ties.batches(people)[0];a,b=group['pairs'][0]
    raw={'objective_relations':{'adoption':dict(id='adoption',kind='adoptive_parent',source_id=b,target_id=a,context='В детстве, возраст неизвестен')},
         'relationships':{'forward':dict(source_id=a,target_id=b,dimensions={'trust':20}),
                          'reverse':dict(source_id=b,target_id=a,dimensions={'trust':70})}}
    before=deepcopy(raw);value=ties.validate(raw,people,group)
    adopted=next(iter(value['objective_relations'].values()))
    assert (adopted['source_id'],adopted['target_id'])==(b,a)
    assert adopted['since'] is None and adopted['context']==raw['objective_relations']['adoption']['context']
    assert value['relationships'][a+':'+b]['dimensions']=={'trust':20}
    assert value['relationships'][b+':'+a]['dimensions']=={'trust':70}
    assert 'knowledge' not in value and raw==before
    assert ties.validate(value,people,group)==value
    assert ties.combine([value],people)==value
    with pytest.raises(ValueError,match='duplicate'):ties.combine([value,value],people)
    with pytest.raises(ValueError,match='outside'):ties.validate(raw,people,ties.batches(people)[-1])
    schema=request_schema('ties',TiesPart.model_json_schema(),dict(registry=people,assigned_pairs=group['pairs']))
    assert len(schema['$defs']['Relationship']['anyOf'])==2*len(group['pairs'])
    assert schema['properties']['relationships']['maxProperties']==2*len(group['pairs'])


@pytest.mark.parametrize('legacy',[False,True])
def test_output_limit_recovery_keeps_upstream_and_completed_tie_checkpoints(api,legacy):
    from test_initial_world_rich_brief import interpreted,provider,BRIEF
    from backend.repositories.preparation import Repository
    client,app=api;repo=app.state.repository;calls=[]
    base=creative_provider(calls,interpreted(),provider(calls))
    original_batches=ties.batches;broken=True;requests=[]
    def stream(**kw):
        stage=kw['messages'][0]['content'].split('\nStage: ')[1].split('\n')[0]
        data=json.loads(kw['messages'][-1]['content'])
        if stage=='ties':
            pairset=data.get('assigned_pairs');requests.append(pairset)
            if broken and (legacy or len(requests)==2):
                kw['on_usage'](dict(prompt_tokens=4000,completion_tokens=kw['max_tokens'],prompt_cache_hit_tokens=0))
                kw['on_finish']('length')
                yield '{"objective_relations":'
                raise OutputLimitReached('secret provider payload must never escape')
        yield from base(**kw)
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        with patch.object(ties,'batches',side_effect=lambda r:[] if legacy and broken else original_batches(r)):
            wid,jid=submit(client,BRIEF);done=wait(client,jid)
            assert done['status']=='failed',done
            failed=next(u for u in done['generation']['units'] if u['status']=='failed')
            assert failed['attempts']==1 # no automatic replay of truncated output
            assert 'OutputLimitReached' in done['error'] and 'secret provider' not in done['error']
            log=repo.request_log(job_id=jid)[0]
            assert (log['status'],log['finish_reason'],log['input_tokens'],log['output_tokens'])==('length','length',4000,log['max_tokens'])
            diagnostic=repo.inspect_generation_checkpoint(jid,failed['unit_id'],True)['diagnostic']
            assert diagnostic['partial_json_bytes']==len('{"objective_relations":')
            assert diagnostic['expected_json_bytes'] is None
            saved={u['unit_id']:repo.inspect_generation_checkpoint(jid,u['unit_id'],True)['artifact_version']
                   for u in done['generation']['units'] if u['status']=='completed'}
            assert 'places' in saved and 'core_0' in saved
            if not legacy:assert 'life_ties_0000' in saved
            # Read checkpoints through a fresh repository, as after backend restart.
            assert Repository(repo.path).inspect_generation_checkpoint(jid,'places',True)['artifact_version']==saved['places']
            broken=False
            resumed=client.post(f'/api/jobs/{jid}/generation/resume',json=dict(revision=done['generation']['revision'],api_key='fixture'))
            assert resumed.status_code==200,resumed.text
            done=wait(client,jid);assert done['status']=='saved',done
    assert all(repo.inspect_generation_checkpoint(jid,k,True)['artifact_version']==v for k,v in saved.items())
    if not legacy:assert requests.count(requests[0])==1
    draft=repo.draft(wid,True);saved_world=repo.confirm_draft(wid,draft['revision'],draft['version_id'])['save']
    state=Repository(repo.path).get_snapshot(saved_world)['world_state']
    assert len(state['characters'])==7 and len(state['organizations'])==6
    assert any(r['kind']=='adoptive_parent' for r in state['objective_relations'].values())
    assert state['knowledge']


def test_paused_pair_edit_preserves_other_batches_and_reaches_canonical_world(api):
    from test_initial_world_rich_brief import interpreted,provider,BRIEF
    from test_generation_edits import checkpoint_body
    client,app=api;repo=app.state.repository;calls=[]
    base=creative_provider(calls,interpreted(),provider(calls));commit=repo.commit_generation_unit
    def pause(jid,token,unit,payload):
        result=commit(jid,token,unit,payload)
        if unit=='opening':repo.generation_control(jid,'pause')
        return result
    with patch('backend.services.preparation.chat_stream',side_effect=base),patch.object(repo,'commit_generation_unit',side_effect=pause):
        wid,jid=submit(client,BRIEF);assert wait(client,jid)['status']=='paused'
    checkpoints={u['unit_id']:repo.inspect_generation_checkpoint(jid,u['unit_id'],True)
                 for u in repo.generation_status(jid)['units'] if u['unit_id'].startswith('life_ties_')}
    unit,cp=next((unit,cp) for unit,cp in checkpoints.items() if cp['artifact']['objective_relations'])
    assert set(cp['editor_schema']['properties'])=={'objective_relations','relationships'}
    rid=next(iter(cp['artifact']['objective_relations']))
    edited='Автор уточнил обстоятельства знакомства.'
    response=client.patch(f'/api/workspaces/{wid}/draft',json=checkpoint_body(repo,jid,unit,'/objective_relations/'+rid+'/context',edited))
    assert response.status_code==200,response.text
    assert repo.inspect_generation_checkpoint(jid,'life_ties',True)['status']=='stale'
    with patch('backend.services.preparation.chat_stream',side_effect=base):
        response=client.post(f'/api/jobs/{jid}/generation/resume',json=dict(revision=repo.generation_status(jid)['revision'],api_key='fixture'))
        assert response.status_code==200,response.text
        done=wait(client,jid);assert done['status']=='saved',done
    for other,old in checkpoints.items():
        if other!=unit:assert repo.inspect_generation_checkpoint(jid,other,True)['artifact_version']==old['artifact_version']
    assert repo.generation_resources(jid,['life'])['life']['objective_relations'][rid]['context']==edited


def test_thirty_character_sparse_graph_assembles_and_roundtrips_canonically():
    from backend.runtime_v3.models import Character
    from backend.services.initial_world_v2 import normalize
    from test_draft_world import fixture
    people=registry(30);parts=[]
    for group in ties.batches(people):
        raw=dict(objective_relations={},relationships={})
        for a,b in group['pairs']:
            if int(b[-3:])-int(a[-3:])!=1:continue
            key=a+'_'+b
            raw['objective_relations'][key]=dict(id=key,kind='friend',source_id=a,target_id=b)
            raw['relationships'][a+':'+b]=dict(source_id=a,target_id=b,dimensions={'trust':40})
            raw['relationships'][b+':'+a]=dict(source_id=b,target_id=a,dimensions={'trust':-10})
        parts.append(ties.validate(raw,people,group))
    result=ties.combine(parts,people)
    assert len(result['objective_relations'])==29 and len(result['relationships'])==58
    snapshot=normalize(fixture()).snapshot
    knowledge=deepcopy(snapshot['world_state']['knowledge'])
    for row in people:
        snapshot['world_state']['characters'][row['id']]=Character(id=row['id'],display_name=row['name']).model_dump()
        snapshot['character_cards'].append(dict(id=row['id'],name=row['name'],fields={},aliases=[]))
    for field,records in result.items():snapshot['world_state'][field].update(records)
    accepted=normalize(snapshot).snapshot
    assert accepted['world_state']['knowledge']==knowledge
    assert normalize(json.loads(json.dumps(accepted))).snapshot==accepted
