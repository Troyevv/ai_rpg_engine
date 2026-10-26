"""The original user journal is immutable. SYNTHETIC_TAIL is offline test output."""
from copy import deepcopy
from pathlib import Path
from threading import Event
from unittest.mock import patch
import hashlib
import json
import pytest
from hypothesis import given, strategies as st
from backend.services.draft_response import join_fragments, prefix_complete, response, TransportError
from backend.services.draft_initial import prompt_schema
from test_draft_response_v4 import JournalRepo, CONFIG, MESSAGES, part, run
from test_initial_draft_v4 import api, rich, REMOTE, SHORT, wait_job

FIXTURE=Path(__file__).parent/'fixtures/initial_world/generation_response_overlap.json'
# Explicit offline continuation; this is NOT the user's missing provider response.
SYNTHETIC_TAIL='since":null,"actor_id":"char_liza","kind":"profession","title":"Адвокат"}}}}'


def journal():return json.loads(FIXTURE.read_bytes())


def test_real_journal_boundary_and_idempotent_resume():
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest()=='a72bbdb4f2861bea0a58e2935b131031aea60cc9801256209e82912845f2bfdd'
    j=journal();before=deepcopy(j);parts=j['responses']['world']['parts'];manifest={}
    text=join_fragments(parts,manifest,schema=prompt_schema())
    assert len(text)==76395 and not prefix_complete(text)
    assert manifest['boundaries'][1]['removed_prefix']==51
    assert manifest['boundaries'][1]['rejected'][0]['overlap']==1
    assert 'вложенность' in manifest['boundaries'][1]['rejected'][0]['reason']
    assert text==parts[0]['text']+parts[1]['text'][51:]
    assert parts==before['responses']['world']['parts']
    assert join_fragments(parts,deepcopy(manifest),schema=prompt_schema())==text
    calls=[]
    def suffix(messages,limit):
        calls.append(messages);assert messages[-2]['content']==text
        yield SYNTHETIC_TAIL
    repo=JournalRepo()
    result=response(repo,'j',j,'world',MESSAGES,CONFIG,262144,suffix,Event())
    assert len(calls)==1 and result==text+SYNTHETIC_TAIL
    assert j['responses']['world']['parts'][:2]==parts[:2]
    assert j['actual_tokens']==before['actual_tokens'] and j['actual_cost']==before['actual_cost']
    assert j['responses']['world']['parts'][2]['offset']==36237+40209
    assert j['responses']['world']['assembly']['boundaries'][2]['assembled_offset']==76395
    assert response(repo,'j',deepcopy(j),'world',MESSAGES,CONFIG,262144,lambda *_:pytest.fail('replay'),Event())==result
    damaged=deepcopy(j);damaged['responses']['world']['assembly']['sha256']='bad'
    with pytest.raises(TransportError,match='манифеста'):response(repo,'j',damaged,'world',MESSAGES,CONFIG,262144,suffix,Event())


@given(st.text(alphabet=st.characters(blacklist_categories=('Cs',)),max_size=80),st.integers(min_value=1,max_value=1000))
def test_literal_splits_preserve_unicode_escapes_repetition(value,cut):
    text=json.dumps({'same':value+value,'array':[value,value]},ensure_ascii=True)
    cut=1+cut%(len(text)-1)
    assert join_fragments([part(text[:cut],0),part(text[cut:],cut)])==text


def test_length_complete_and_multifragment_syntax_repair():
    assert len(run([('{"a":1}','length')])[3])==1
    raw,_,_,calls=run([('{"a":','length'),('1 "b":2}','stop')])
    assert raw=='{"a":1 "b":2}' and len(calls)==2
    from backend.services.draft_repair import request,apply
    _,paths=request(raw,[{'path':'/','message':'syntax'}]);assert paths is None
    assert json.loads(apply(raw,'{"a":1,"b":2}',paths))=={'a':1,'b':2}


def test_actual_ambiguity_never_guessed():
    # Two distinct allowed removals, neither is a literal continuation.
    left='{"a":[{';right='{"a":[{"x":1},{"x":1},{"x":1}]}'
    with pytest.raises(TransportError,match='Неоднозначная'):
        join_fragments([part(left,0),part(right,len(left))])
    a='{"x":"abc\\';b='\\\\"}'
    # A single escape boundary still obeys normal grammar, regardless of overlap.
    assert join_fragments([part(a,0),part(b,len(a))])==a+b
    with pytest.raises(TransportError):join_fragments([part('{"a":1}',0),part('{"a":1}',7)])
    with pytest.raises(TransportError,match='Повтор JSON-ключа'):join_fragments([part('{"a":1,',0),part('"a":2}',7)])


def test_world_a_is_not_adopted_by_job_b(api):
    client,app=api;wid=client.post('/api/workspaces',json={'name':'A then B'}).json()['id'];url=f'/api/workspaces/{wid}/draft'
    client.post(url+'/import',json={'revision':0,'format':'json','text':json.dumps(rich())})
    d=client.get(url+'?author=true').json()
    # B fails preflight before publishing a candidate. A remains independently available.
    with patch('backend.services.preparation.chat_stream',side_effect=AssertionError('no call')):
        jid=client.post(url+'/generate',json={'revision':d['revision'],'text':SHORT+' detail'*12000,'config':REMOTE,'api_key':'test'}).json()['id']
        assert wait_job(client,jid)['status']=='error'
    repo=app.state.repository
    cfg=repo.resume_draft_response(jid,revision=d['revision'],config_changes={'context_length':262144})
    j=json.loads(repo.preparation_job(jid)['response_journal'])
    assert 'candidate_text' not in j
    assert client.get(url+'?author=true').json()['state']['campaign']==d['state']['campaign']
    assert cfg['context_length']==262144


def test_real_saved_response_to_editor_game_and_reload(api):
    client,app=api;repo=app.state.repository
    wid=client.post('/api/workspaces',json={'name':'Real fragment recovery'}).json()['id'];url=f'/api/workspaces/{wid}/draft'
    # Seed an existing stopped job without paying/replaying its two original requests.
    with patch('backend.services.preparation.chat_stream',side_effect=RuntimeError('offline')):
        jid=client.post(url+'/generate',json={'revision':0,'text':SHORT,'config':dict(REMOTE,context_length=262144),'api_key':'test'}).json()['id']
        wait_job(client,jid)
    j=journal();j.pop('requests');j.pop('recovery');j['recovery_epoch']=0
    repo.save_response_journal(jid,j);calls=[]
    def suffix(**kw):
        calls.append(kw)
        if len(calls)==4:
            from llm import ProviderHTTPError
            raise ProviderHTTPError('Controlled outage before alternate audit',502)
        yield SYNTHETIC_TAIL if len(calls)==1 else '{"issues":"invalid report"}'
    with patch('backend.services.preparation.chat_stream',side_effect=suffix):
        assert client.post(url+'/resume',json={'revision':0,'api_key':'test'}).status_code==200
        assert wait_job(client,jid)['status']=='error' # report failure retains the automatically coalesced world
    assert len(calls)==4 and calls[0]['messages'][-2]['content'].endswith('"status": "active",\n        "')
    d=client.get(url+'?author=true').json();original=deepcopy(d['candidate'])
    assert not any(e['category']=='duplicate' for e in d['validation']['diagnostics'])
    sibling=d['candidate']['world']['objective_relations']['obj_katya_timur']
    assert sibling['status']=='active'
    assert sibling['context']=='Кровные сестра и брат\nКровные брат и сестра'
    assert 'obj_timur_katya' not in d['candidate']['world']['objective_relations']
    reviewed=[];corrections=[]
    # Synthetic provider patches fix only contradictory biography clauses.
    for index,card in enumerate(d['candidate']['characters']):
        if card['id'] not in ('char_timur','char_marina','char_sergey'):continue
        bio=card['fields']['Биография']
        bio=bio.replace('Родился после усыновления Ильи','Родился за шесть лет до усыновления Ильи')
        bio=bio.replace('Они усыновили Илью, а позже родились Тимур и Катя.', 'Тимур уже родился, когда они усыновили Илью; позже родилась Катя.')
        bio=bio.replace('После нескольких лет брака они не могли иметь детей; Марина тяжело переживала.', 'После рождения Тимура они несколько лет не могли завести второго ребёнка; Марина тяжело переживала.')
        bio=bio.replace('Женился на Марине, но у них не было детей.', 'Женился на Марине; после рождения Тимура они несколько лет не могли завести второго ребёнка.')
        corrections.append(dict(path=f'/characters/{index}/fields/Биография',value=bio))
    def reviewer(**kw):
        from backend.services.draft_completeness import MARKER
        reviewed.append(kw)
        if kw['messages'][0]['content'].startswith(MARKER):
            yield json.dumps({'issues':[{'path':'/characters/2/fields/Биография','severity':'blocker','patch_paths':[p['path'] for p in corrections],'message':'Тимуру 26, Илье 20, но Тимур родился после усыновления младенца Ильи.'}] if len(reviewed)==1 else []},ensure_ascii=False)
        else:yield json.dumps({'patches':corrections},ensure_ascii=False)
    with patch('backend.services.preparation.chat_stream',side_effect=reviewer):
        assert client.post(url+'/resume',json={'revision':d['revision'],'api_key':'test'}).status_code==200
        final=wait_job(client,jid);assert final['status']=='saved',final
    assert len(reviewed)==3 # report, targeted biography patch, re-review; no world request
    d=client.get(url+'?author=true').json();assert d['state']
    for cid,actor in original['world']['characters'].items():
        for field in ('goals','intentions','obligations'):assert d['state']['world']['characters'][cid].get(field)==actor.get(field)
    assert d['state']['world']['knowledge']==original['world']['knowledge']
    started=client.post(url+'/confirm',json={'revision':d['revision'],'version_id':d['version_id']});assert started.status_code==200,started.text
    from test_runtime_v3_engine import run as play,raw_for
    from test_engine import CONFIG as PLAY_CONFIG
    from backend.repositories.preparation import Repository
    sid=started.json()['save']
    for kind in ('start','turn','turn'):
        snap=repo.get_snapshot(sid);turn=repo.begin_job(sid,'Осматриваюсь.' if kind=='turn' else '',kind,dict(PLAY_CONFIG,provider='deepseek',model='deepseek-flash',context_length=262144))
        play(repo,turn,raw_for(snap));assert repo.get_job(turn)['status']=='saved',repo.get_job(turn)['error']
        repo=Repository(repo.path)
        from backend.runtime_v3.models import ObjectiveRelation
        assert repo.get_snapshot(sid)['world_state']['objective_relations']['obj_katya_timur']==ObjectiveRelation.model_validate(sibling).model_dump()


def test_optional_motivation_defaults_are_recoverable_without_literary_loss():
    from backend.services.draft_initial import inspect_candidate
    from test_draft_motivations import motivated
    raw,cid=motivated();minimal=deepcopy(raw)
    for field in ('goals','intentions','obligations'):
        # Only remove defaults of the second, metadata-free entry.
        item=minimal['world']['characters'][cid][field][1]
        for key in ('dependencies','review_required','reviewed_signature'):item.pop(key,None)
    full,_=inspect_candidate(raw);compact,_=inspect_candidate(minimal)
    assert full==compact


def test_retry_only_bad_fragment_preserves_accounting_and_blocks_concurrent_resume(api):
    client,app=api;repo=app.state.repository
    wid=client.post('/api/workspaces',json={'name':'boundary'}).json()['id'];url=f'/api/workspaces/{wid}/draft'
    with patch('backend.services.preparation.chat_stream',side_effect=RuntimeError('offline')):
        jid=client.post(url+'/generate',json={'revision':0,'text':SHORT,'config':REMOTE,'api_key':'test'}).json()['id'];wait_job(client,jid)
    left='{"a":[{';right='{"a":[{"x":1},{"x":1},{"x":1}]}'
    j={'responses':{'world':{'parts':[part(left,0),part(right,len(left))],'complete':False,'assembly_error':'ambiguous'}},'actual_tokens':123,'actual_cost':'0.012','reserved_tokens':22,'recovery_epoch':0}
    repo.save_response_journal(jid,j)
    repo.resume_draft_response(jid,revision=0,retry_last_fragment=True)
    after=json.loads(repo.preparation_job(jid)['response_journal'])
    assert after['responses']['world']['parts']==[part(left,0)]
    assert after['fragment_recoveries'][0]['part']==part(right,len(left))
    for key in ('actual_tokens','actual_cost','reserved_tokens'):assert after[key]==j[key]
    with pytest.raises(ValueError):repo.resume_draft_response(jid,revision=0,retry_last_fragment=True)
    with pytest.raises(ValueError,match='Устаревший'):repo.save_response_journal(jid,j)


def test_stop_with_incomplete_prefix_continues_instead_of_inventing_brackets():
    result,_,j,calls=run([('{"a":','stop'),('1}','stop')])
    assert result=='{"a":1}' and len(calls)==2
    assert j['responses']['world']['document_state']=='complete'


def test_legacy_candidate_edit_lineage_is_retained(api):
    client,app=api;repo=app.state.repository
    wid=client.post('/api/workspaces',json={'name':'legacy edited candidate'}).json()['id'];url=f'/api/workspaces/{wid}/draft'
    calls=[]
    def fail_review(**kw):
        calls.append(kw);yield json.dumps(rich()) if len(calls)==1 else '{"wrong":true}'
    with patch('backend.services.preparation.chat_stream',side_effect=fail_review):
        jid=client.post(url+'/generate',json={'revision':0,'text':SHORT,'config':REMOTE,'api_key':'test'}).json()['id']
        assert wait_job(client,jid)['status']=='error'
    # Test-only recreation of pre-provenance document metadata; never a production migration.
    with repo.connect() as db:
        for row in db.execute("SELECT id,content FROM document_versions WHERE owner=? AND kind='world_draft'",(wid,)).fetchall():
            rec=json.loads(row['content']);rec.pop('origin_job',None)
            db.execute('UPDATE document_versions SET content=? WHERE id=?',(json.dumps(rec),row['id']))
    d=client.get(url+'?author=true').json()
    d=client.patch(url+'/candidate',json={'revision':d['revision'],'path':'/campaign/title','value':'Моя ручная правка'}).json()
    with patch('backend.services.preparation.chat_stream',return_value=iter(['{"issues":[]}'])) as provider:
        assert client.post(url+'/resume',json={'revision':d['revision'],'api_key':'test'}).status_code==200
        assert wait_job(client,jid)['status']=='saved'
        assert provider.call_count==1
    assert client.get(url+'?author=true').json()['state']['campaign']['title']=='Моя ручная правка'


def test_terminal_duplicate_keys_and_empty_report_reach_strict_validation():
    assert run([('{"issues":[],"issues":[1]}','stop')])[0]=='{"issues":[],"issues":[1]}'
    assert run([('','stop')])[0]==''
    from backend.services.draft_response import strict_loads
    with pytest.raises(ValueError,match='Повтор'):strict_loads(run([('{"a":1,','length'),('"a":2}','stop')])[0])


def test_public_integrity_error_does_not_offer_fragment_replacement():
    from backend.repositories.preparation import Repository
    j=journal();j['responses']['world']['assembly_error']='Нарушена целостность манифеста сборки.'
    public=Repository.public_job(dict(kind='draft_world',status='error',response_journal=json.dumps(j)))
    assert public['transport_blocked'] and not public['fragment_recovery']
    assert 'responses' not in public and 'response_journal' not in public


def test_identical_candidate_from_new_job_gets_new_lineage(api):
    client,app=api;repo=app.state.repository
    wid=client.post('/api/workspaces',json={'name':'identical failed worlds'}).json()['id'];url=f'/api/workspaces/{wid}/draft'
    value=rich();cid=value['protagonist_id'];value['protagonist_id']='missing'
    last_version=None
    for _ in range(2):
        d=client.get(url+'?author=true').json();count=[]
        def broken(**kw):
            count.append(kw);yield json.dumps(value) if len(count)==1 else '{"patches":[]}'
        with patch('backend.services.preparation.chat_stream',side_effect=broken):
            jid=client.post(url+'/generate',json={'revision':d['revision'],'text':SHORT,'config':REMOTE,'api_key':'test'}).json()['id']
            assert wait_job(client,jid)['status']=='error'
        d=client.get(url+'?author=true').json()
        if last_version:assert d['version_id']>last_version
        last_version=d['version_id']
        with repo.connect() as db:assert json.loads(repo._draft_head(db,wid)['content'])['origin_job']==jid
    d=client.patch(url+'/candidate',json={'revision':d['revision'],'path':'/protagonist_id','value':cid}).json()
    with patch('backend.services.preparation.chat_stream',return_value=iter(['{"issues":[]}'])) as provider:
        client.post(url+'/resume',json={'revision':d['revision'],'api_key':'test'})
        assert wait_job(client,jid)['status']=='saved'
        assert provider.call_count==1


def test_terminal_syntax_failure_is_not_a_published_world():
    from backend.repositories.preparation import Repository
    j={'responses':{'world':{'parts':[part('{"bad":}',0)],'complete':True,'document_state':'syntax_error'}}}
    public=Repository.public_job(dict(kind='draft_world',status='error',response_journal=json.dumps(j)))
    assert public['transport_incomplete'] and not public['fragment_recovery']
