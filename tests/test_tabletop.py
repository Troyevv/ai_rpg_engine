"""Tabletop contract, deterministic mechanics, storage/API boundaries and full slice."""
import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from backend.api.app import create_app
from backend.tabletop.models import Command, NewGame, GameState, Ruleset, CharacterSheet, PendingRoll
from backend.tabletop.dice import DiceEngine
from backend.tabletop.rules import RulesEngine
from backend.tabletop.runtime import TabletopRuntime, new_game
from backend.tabletop.ai import GameAI
from backend.tabletop.dm import DMAgent, DMContextBuilder
from backend.tabletop.projection import public_state
from backend.tabletop.repository import TabletopRepository


class Fixed:
    def __init__(self, *values):
        self.values = iter(values)
    def randint(self, lo, hi):
        n = next(self.values)
        assert lo <= n <= hi
        return n


def runtime(*values):
    return TabletopRuntime(DiceEngine(Fixed(*values)))


def state():
    return new_game(NewGame(companion=False))


@pytest.mark.parametrize('sides',[4,6,8,10,12,20,100])
def test_dice_sizes(sides):
    r = DiceEngine(Fixed(1,sides)).roll(f'2d{sides}+3', purpose='test', actor='hero')
    assert r.total == sides+4 and r.raw == [1,sides] and r.modifier == 3


@pytest.mark.parametrize('expression',['0d6','99d20','1d3','d0','-1d20','1d20;eval','2d20+9999'])
def test_bad_dice(expression):
    with pytest.raises(ValueError):
        DiceEngine().roll(expression)


def test_advantage_critical_and_modifiers():
    assert DiceEngine(Fixed(1,20)).roll('d20',advantage=1).total == 20
    assert DiceEngine(Fixed(1,20)).roll('d20',advantage=-1).total == 1
    assert DiceEngine(Fixed(3,4)).roll('d8+3',critical=True).total == 10
    assert DiceEngine(Fixed(3)).roll('d8+3',critical=True,critical_rule='max_dice').total == 14
    r=RulesEngine();a=state().actor('hero')
    assert r.modifier(9)==-1
    assert r.check_modifier(a,'strength','athletics',Ruleset())==5
    assert r.save_modifier(a,'constitution')==4
    assert r.attack_modifier(a,'sword')==5
    with pytest.raises(ValueError):r.check_modifier(a,'strength','perception',Ruleset())


def test_ability_save_and_secret_revelation():
    s=state();r=runtime(12)
    after,events=r.execute(s,Command(type='check',target='chest',skill='perception'))
    assert s.session_state.pending is None  # copy-on-write
    assert after.session_state.pending.dc==12
    public=json.dumps(public_state(after),ensure_ascii=False)
    assert '"secret":' not in public and '"cache":' not in public and '"dc":' not in public
    with pytest.raises(ValueError):r.execute(after,Command(type='look'))
    done,events=r.resolve_roll(after,after.session_state.pending.id)
    assert done.player_knowledge['cache'] and events[-1]['kind']=='discovery'
    with pytest.raises(ValueError):r.resolve_roll(done,after.session_state.pending.id)
    a,e=runtime().execute(state(),Command(type='save',ability='constitution',dc=14))
    assert a.session_state.pending.modifier==4
    a,e=runtime(10).resolve_roll(a,a.session_state.pending.id)
    assert e[-1]['success'] is True


def test_check_natural_twenty_not_automatic_success():
    s,e=runtime().execute(state(),Command(type='check',ability='intelligence',dc=25))
    s,e=runtime(20).resolve_roll(s,s.session_state.pending.id)
    assert not e[-1]['success']


def combat_state():
    r=runtime(20,1)
    s,e=r.execute(state(),Command(type='start_encounter'))
    s,e=r.resolve_roll(s,s.session_state.pending.id)
    return s


def test_full_domain_slice_and_action_economy():
    s=state();r=runtime(15,20,1,12,2,1)
    s,e=r.execute(s,Command(type='check',target='chest',skill='perception'))
    s,e=r.resolve_roll(s,s.session_state.pending.id)
    s,e=r.execute(s,Command(type='start_encounter'))
    s,e=r.resolve_roll(s,s.session_state.pending.id)
    assert s.encounter.order==['hero','goblin']
    s,e=r.execute(s,Command(type='attack',target='goblin'))
    assert not s.encounter.action
    s,e=r.resolve_roll(s,s.session_state.pending.id)
    assert s.session_state.pending.purpose=='damage'
    s,e=r.resolve_roll(s,s.session_state.pending.id)
    assert s.npcs['goblin'].hp==9
    with pytest.raises(ValueError):r.execute(s,Command(type='attack',target='goblin'))
    s,e=r.execute(s,Command(type='end_turn'))
    assert s.encounter.round==2 and s.encounter.action
    assert any(x.get('roll',{}).get('actor')=='goblin' for x in e)


def test_attack_natural_one_and_twenty_and_hp():
    s=combat_state();s,e=runtime().execute(s,Command(type='attack',target='goblin'))
    missed,e=runtime(1).resolve_roll(s,s.session_state.pending.id)
    assert missed.session_state.pending is None and e[-1]['kind']=='miss'
    hit,e=runtime(20).resolve_roll(s,s.session_state.pending.id)
    assert hit.session_state.pending.critical
    done,e=runtime(8,8).resolve_roll(hit,hit.session_state.pending.id)
    assert done.npcs['goblin'].hp==0 and done.active_encounter is None
    assert len(e[0]['roll']['raw'])==2


def test_death_saves_heal_and_conditions():
    r=RulesEngine();a=CharacterSheet(id='hero',name='Hero')
    assert r.damage(a,12)==12 and 'unconscious' in a.conditions
    r.death_save(a,DiceEngine(Fixed(1)).roll('d20'))
    assert a.death_failures==2
    r.death_save(a,DiceEngine(Fixed(20)).roll('d20'))
    assert a.hp==1 and not a.conditions and a.death_failures==0
    r.damage(a,100)
    assert 'dead' in a.conditions
    with pytest.raises(ValueError):r.heal(a,20)


def test_ai_movement_flee_attack_and_dodge():
    s=combat_state();ai=GameAI()
    assert ai.decide(s,'goblin').type=='attack'
    s.npcs['goblin'].position=50
    assert ai.decide(s,'goblin').type=='move'
    s.npcs['goblin'].position=5;s.npcs['goblin'].hp=1
    assert ai.decide(s,'goblin').distance<0
    s.npcs['goblin'].hp=14;s.npcs['goblin'].attacks={}
    assert ai.decide(s,'goblin').type=='dodge'


def test_movement_rest_and_dodge():
    s=combat_state()
    with pytest.raises(ValueError):runtime().execute(s,Command(type='move',distance=35))
    s,e=runtime().execute(s,Command(type='dodge'))
    assert 'dodge' in s.actor('hero').conditions and not s.encounter.action
    with pytest.raises(ValueError):runtime().execute(s,Command(type='rest'))
    s=state();s.characters['hero'].hp=1
    s,e=runtime().execute(s,Command(type='rest'))
    assert s.characters['hero'].hp==8 and s.game_time==3600
    with pytest.raises(ValueError):runtime().execute(s,Command(type='rest'))


@pytest.mark.parametrize('payload',[
    {'type':'attack','hp':999}, {'type':'ApplyDamageRequest','amount':999},
    {'type':'check','dc':1}, {'type':'look','state':{'characters':{}}},
    {'type':'check','actor':'goblin'}, {'type':'check','ability':'luck'},
])
def test_llm_cannot_mutate_state_directly(payload):
    with pytest.raises(ValueError):Command.model_validate(payload)


def test_context_fog_including_companion_internals():
    s=new_game(NewGame());s.characters['theron'].knowledge=['NEVER-SHOW'];s.npcs['goblin'].knowledge=['NEVER-SHOW']
    for value in (public_state(s),DMContextBuilder.build(s)):
        text=json.dumps(value)
        assert 'NEVER-SHOW' not in text and 'cache' not in text and 'dm_state' not in text
        assert 'armor_class' not in json.dumps(value.get('npcs',value.get('visible_npcs')))


def test_unsupported_rules_and_state_references():
    with pytest.raises(ValueError):Ruleset(capabilities=['magic'])
    with pytest.raises(ValueError):GameState.model_validate({**state().model_dump(),'party':['missing']})
    s=state();s.ruleset.capabilities=[]
    with pytest.raises(ValueError):runtime().execute(s,Command(type='check'))


@pytest.fixture
def api(tmp_path):
    app=create_app(tmp_path/'tabletop.sqlite3')
    with TestClient(app) as client:
        yield client,app


def create(client):
    response=client.post('/api/tabletop/games',json={'name':'Test','companion':False})
    assert response.status_code==200,response.text
    return response.json()


def send(client,g,kind='actions',**payload):
    return client.post(f"/api/tabletop/games/{g['id']}/{kind}",json={'revision':g['revision'],'request_id':f"request-{g['revision']}-{kind}",**payload})


def test_api_vertical_slice_restart_replay_and_roll_idempotency(api):
    c,app=api;g=create(c)
    dice=DiceEngine(Fixed(15,20,1,12,2,1))
    app.state.tabletop_runtime.dice=dice;app.state.tabletop_runtime.combat.dice=dice
    g=send(c,g,command={'type':'check','target':'chest','skill':'perception'}).json()
    assert g['state']['mode']=='AWAITING_ROLL'
    pending=g['state']['pending']['id']
    args={'revision':g['revision'],'request_id':'same-roll-id','pending_id':pending}
    path=f"/api/tabletop/games/{g['id']}/roll"
    first=c.post(path,json=args);second=c.post(path,json=args)
    assert first.status_code==second.status_code==200 and first.json()==second.json()
    g=first.json()
    for cmd in [{'type':'start_encounter'},{'type':'attack','target':'goblin'}]:
        g=send(c,g,command=cmd).json()
        while g['state']['pending']:
            g=send(c,g,'roll',pending_id=g['state']['pending']['id']).json()
    g=send(c,g,command={'type':'end_turn'}).json()
    assert g['state']['encounter']['round']==2
    repo=TabletopRepository(app.state.repository.path)
    assert repo.load(g['id'])[0]==g['revision']
    # Read-only snapshot replay never invokes RNG or LLM.
    assert c.get(f"/api/tabletop/games/{g['id']}/replay/{g['revision']}").json()['state']==g['state']
    before=g['revision'];g=send(c,g,'rollback').json()
    assert g['revision']==before+1 and g['state']['encounter']['round']==1


def test_pending_survives_restart_and_rejects_stale_roll(api):
    c,app=api;g=create(c);g=send(c,g,command={'type':'check'}).json()
    fresh=create_app(app.state.repository.path)
    with TestClient(fresh) as other:
        restored=other.get(f"/api/tabletop/games/{g['id']}").json()
        assert restored['state']['pending']==g['state']['pending']
        assert send(other,g,'roll',pending_id='wrong').status_code==409
        assert send(other,g,command={'type':'look'}).status_code==409


def test_history_damage_does_not_break_current_state(api):
    c,app=api;g=create(c);repo=app.state.tabletop_repository
    with repo.connect() as db:
        db.execute("UPDATE tabletop_history SET after_json='invalid',before_json='{}',events_json='bad' WHERE game_id=?",(g['id'],))
    current=c.get(f"/api/tabletop/games/{g['id']}")
    assert current.status_code==200 and current.json()['state']==g['state']
    assert send(c,g,'rollback').status_code==409
    assert c.get(f"/api/tabletop/games/{g['id']}/replay/1").status_code==409
    assert send(c,g,command={'type':'look'}).status_code==200


def test_atomic_cas_and_failed_history_insert(tmp_path):
    repo=TabletopRepository(tmp_path/'atomic.db');gid=repo.create(state());s=state()
    def commit(n):
        try:return repo.commit(gid,0,f'request-{n}',str(n),s,[],'')
        except ValueError:return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(commit,[1,2]))==1
    with repo.connect() as db:
        db.execute("CREATE TRIGGER fail_history BEFORE INSERT ON tabletop_history BEGIN SELECT RAISE(ABORT,'injected'); END")
    with pytest.raises(Exception):repo.commit(gid,1,'request-new','new',s,[],'')
    assert repo.load(gid)[0]==1


CONFIG={'provider':'deepseek','model':'deepseek-flash','max_tokens':512}


def test_dm_contract_usage_no_secret_and_fallback(api):
    c,app=api;g=create(c)
    calls=[]
    def stream(**kw):
        calls.append(kw)
        kw['on_usage']({'prompt_tokens':100,'completion_tokens':10,'prompt_cache_hit_tokens':20})
        yield json.dumps({'type':'check','ability':'strength','skill':'athletics','dc':14}) if kw.get('response_format') else 'Проверь силу: брось кубик.'
    with patch('llm.chat_stream',side_effect=stream):
        g=send(c,g,text='Пробую сдвинуть тяжёлый шкаф',config=CONFIG,api_key='secret-token').json()
    assert g['state']['pending']['ability']=='strength' and len(calls)==2
    assert len(g['usage'])==2 and g['usage'][0]['input_tokens']==100
    assert 'cache' not in json.dumps(calls,default=str,ensure_ascii=False).replace('prompt_cache_hit_tokens','') # no hidden secret key
    with patch('llm.chat_stream',side_effect=RuntimeError('secret-token')):
        response=send(c,g,'roll',pending_id=g['state']['pending']['id'],config=CONFIG,api_key='secret-token')
    assert response.status_code==200 and 'secret-token' not in response.text
    assert 'результат сохранён' in response.text
    with app.state.tabletop_repository.connect() as db:
        assert 'secret-token' not in '\n'.join(db.iterdump())


def test_bad_llm_command_never_mutates(api):
    c,app=api;g=create(c)
    with patch('llm.chat_stream',return_value=iter(['{"type":"look","hp":999}'])):
        response=send(c,g,text='Получи HP',config=CONFIG,api_key='secret')
    assert response.status_code==409
    after=c.get(f"/api/tabletop/games/{g['id']}").json()
    assert after['revision']==g['revision'] and after['state']==g['state']
    assert send(c,g,command={'type':'look','hp':999}).status_code==422
    assert send(c,g,'roll',pending_id='no',raw=20).status_code==422


def test_architecture_does_not_import_narrative_runtime():
    from pathlib import Path
    for path in (Path(__file__).parents[1]/'backend'/'tabletop').glob('*.py'):
        assert 'import engine' not in path.read_text() and 'runtime_v3' not in path.read_text()
