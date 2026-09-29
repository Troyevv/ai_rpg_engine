import json
from copy import deepcopy
from context_builder import build_context, estimate
from backend.runtime_v3.models import Fact, Knowledge
from test_runtime_v3_storage import snapshot_fixture


def test_long_known_history_is_ranked_without_mutating_current_state():
    snapshot=snapshot_fixture();state=snapshot['world_state']
    for i in range(150):
        fid=f'fact_{i}'
        state['facts'][fid]=Fact(id=fid,text=('Подвал: важная подсказка' if i==149 else 'Давно известная подробность '*60),character_ids=['a']).model_dump()
        state['knowledge']['a:'+fid]=Knowledge(actor_id='a',fact_id=fid).model_dump()
    before=deepcopy(snapshot)
    messages=build_context(snapshot,[],'Осмотреть подвал','turn',16000,2000)
    assert estimate(messages)<=16000-2000-256
    current=json.loads(next(m['content'] for m in messages if m['content'].startswith('Текущее состояние')).split('\n',1)[1])
    assert 'fact_149' in current['facts'] and len(current['facts'])<150
    assert all(k['fact_id'] in current['facts'] for k in current['knowledge'])
    assert snapshot==before


def test_old_campaign_sections_do_not_duplicate_absent_cards():
    snapshot=snapshot_fixture()
    snapshot['campaign']['sections']={'characters':'DO NOT DUPLICATE OLD CARDS','tone':'Драмеди'}
    messages=build_context(snapshot,[],'Осмотреть комнату','turn',32768,2000)
    assert 'DO NOT DUPLICATE OLD CARDS' not in str(messages)
    assert 'Драмеди' in str(messages)
