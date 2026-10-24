import pytest
from backend.services.world_creation_settings import CreationSettings, presentation_rule
from backend.services.initial_world_v2 import normalize
from test_initial_world_v2 import rich_draft
from test_api import api
from context_builder import build_context


@pytest.mark.parametrize('options',[
    {'primary_genre':'romance','secondary_genres':['romance']},
    {'secondary_genres':['drama','drama']},
    {'secondary_genres':['romance','drama','fantasy','horror']},
    {'primary_genre':'custom','custom_genre':' '},
    {'cast_preset':'custom','core_npcs':0},
    {'secondary_npcs':41}, {'npc_expressiveness':'stereotype'},
])
def test_creation_settings_reject_conflicts_and_invalid_limits(options):
    with pytest.raises(ValueError): CreationSettings.model_validate(options)


def test_cast_targets_preserve_explicit_npcs_and_do_not_invent_actors():
    entities=[dict(id=str(i),kind='character',tier='core') for i in range(5)]
    settings=CreationSettings(cast_preset='small',primary_genre='family_saga')
    assert settings.cast_targets(entities)==dict(core=5,secondary=5,user_entities_over_target=True)
    assert len(entities)==5
    assert settings.npc_expressiveness=='expressive'
    assert CreationSettings(cast_preset='custom',core_npcs=1,secondary_npcs=0).cast_targets([])['secondary']==0


def test_expressiveness_is_presentation_and_survives_normalization():
    draft=rich_draft()
    assert normalize(draft).snapshot['world_state']['meta']['npc_expressiveness']=='realistic'
    draft['world']['npc_expressiveness']='hyperbolized'
    snapshot=normalize(draft).snapshot
    assert normalize(snapshot).snapshot['world_state']==snapshot['world_state']
    context=build_context(snapshot,[],'Осмотреться','turn',32768,2000)
    assert 'NPC presentation:' in str(context)
    assert 'anime-like' in str(context)
    assert 'never changes established traits' in str(context)
    assert 'player decisions' in presentation_rule('expressive')


def test_policy_update_does_not_reset_expressiveness_when_older_client_omits_it(api):
    import json
    client,app=api
    wid=client.post('/api/workspaces',json={'name':'Presentation'}).json()['id']
    path=f'/api/workspaces/{wid}/draft'
    draft=rich_draft();draft['world']['npc_expressiveness']='hyperbolized'
    assert client.post(path+'/import',json={'revision':0,'format':'json','text':json.dumps(draft)}).status_code==200
    value=client.get(path+'?author=true').json()
    sid=client.post(path+'/confirm',json={'revision':value['revision'],'version_id':value['version_id']}).json()['save']
    policy=client.get(f'/api/saves/{sid}/narrative-policy').json()['current']
    assert policy.pop('npc_expressiveness')=='hyperbolized'
    policy['narrative_pacing']={'preset':'calm'}
    revision=client.get(f'/api/saves/{sid}').json()['revision']
    assert client.put(f'/api/saves/{sid}/narrative-policy',json={'revision':revision,**policy}).status_code==200
    assert app.state.repository.get_snapshot(sid)['world_state']['meta']['npc_expressiveness']=='hyperbolized'
