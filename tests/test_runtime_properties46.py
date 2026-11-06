"""Bounded relational properties and long-world budgets for #46."""
import json
from tempfile import TemporaryDirectory
from pathlib import Path
from time import perf_counter

from hypothesis import given, settings, strategies as st

from backend.repositories.preparation import Repository
from backend.runtime_v3.context import build_context
from backend.runtime_v3.kinship import genealogy
from backend.runtime_v3.long_term import run as advance
from backend.runtime_v3.migration import migrate_v2
from backend.runtime_v3.remote import projection as phone
from backend.runtime_v3.player_calendar import player_calendar
from backend.runtime_v3.scope import RelevanceResolver
from backend.runtime_v3.repository import initialize, append_history, read_history, migrate_snapshot
from backend.runtime_v3.milestones import query
from context_builder import estimate
from devtools.narrative_test_world import build_fixture, load_fixture
from test_narrative_test_world import CONFIG
from test_npc_review import promoted
from test_runtime_v3_engine import raw_for, run as run_job
from test_life_social import run, state, tie


@given(st.lists(st.sampled_from(['b', 'c', 'd']), min_size=2, max_size=8))
@settings(max_examples=10, deadline=None)
def test_remarriage_lineages_archive_the_prior_family(partners):
    from sqlite3 import connect
    with connect(':memory:') as db:
        initialize(db)
        head = None
        current = state()
        phases = []
        for i, partner in enumerate(partners):
            # Fork a quiet sibling before the canonical divorce/remarriage.
            sibling = append_history(db, head, {})
            earlier = query(db, sibling)
            rid = f'marriage-{i}'
            delta = [tie(rid, b=partner)]
            if phases:
                delta.insert(0, dict(id=phases[-1], status='closed', outcome='divorced'))
            transition = run(current, 'social_relation_changes', delta)
            head = append_history(db, head, transition.history)
            current = json.loads(json.dumps(transition.state))
            phases.append(rid)
            assert {k for k,r in current['objective_relations'].items() if r['status']=='active'} == {rid}
            assert all(current['objective_relations'][k]['outcome']=='divorced' for k in phases[:-1])
            assert query(db, sibling) == earlier
            records = query(db, head)
            assert len({r['id'] for r in records}) == len(records)


@given(st.lists(st.booleans(), min_size=2, max_size=6))
@settings(max_examples=5, deadline=None)
def test_legacy_roundtrips_reuse_the_migration_head(reopens):
    legacy = build_fixture('family')
    raw = json.dumps(legacy, ensure_ascii=False)
    with TemporaryDirectory() as directory:
        repo = Repository(Path(directory) / 'legacy.sqlite')
        with repo.connect() as db:
            first, _ = migrate_snapshot(db, json.loads(raw))
        for reopen in reopens:
            if reopen:
                repo = Repository(repo.path)
            with repo.connect() as db:
                migrated, _ = migrate_snapshot(db, json.loads(raw))
                assert migrated == first
                assert db.execute('SELECT count(*) FROM world_history_v3').fetchone()[0] == 1
            assert migrate_v2(json.loads(json.dumps(migrated))).snapshot['world_state'] == first['world_state']
        assert json.dumps(legacy, ensure_ascii=False) == raw


@given(st.integers(min_value=3, max_value=5), st.sampled_from(['Конверт', 'Разговор на кухне']))
@settings(max_examples=4, deadline=None)
def test_large_world_selection_fits_actual_context(scale, prompt):
    from long_world_fixture import long_world
    snapshot, turns, history = long_world(scale)
    scope = RelevanceResolver().resolve(snapshot, prompt, world_history=history)
    messages = build_context(snapshot, turns, prompt, 'turn', 32768, 2000, world_history=history)
    assert len(scope.knowledge_ids) <= 48 and len(scope.fact_ids) <= 24
    assert estimate(messages) <= 32768 - 2000
    assert 'UNRELATED_WAREHOUSE_54' not in str(messages)


def test_dense_family_history_projections_and_lta(tmp_path):
    from devtools.narrative_test_world import _phone
    repo = Repository(tmp_path / 'dense.sqlite')
    legacy = _phone(build_fixture('ui-family-dense'))
    with repo.connect() as db:
        snapshot, _ = migrate_snapshot(db, legacy)
        head = snapshot['history_head']
        for i in range(96):
            head = append_history(db, head, {'state_changes':[dict(kind='life_changes', entity='qa_roman',
                minute=i, before={'life_status':'alive'}, after={'life_status':'dead'}, evidence='Архивная запись')]})
        history, warnings = read_history(db, head)
        assert not warnings
        milestones = query(db, head, actor_ids=['qa_roman'], limit=8)
    snapshot['history_head'] = head
    world = snapshot['world_state']
    started = perf_counter()
    messages = build_context(snapshot, [], 'Наблюдаю за семьёй.', 'turn', 32768, 2000, world_history=history)
    family = genealogy(snapshot, 'qa_timur', depth=3, limit=24)
    calendar = player_calendar(world, '2026-10-01', '2026-10-31')
    directory = phone(snapshot)['recipients']
    after, _, report = advance(snapshot, dict(amount=15, unit='years', max_llm_calls=0))
    assert len(world['characters']) > 100 and len(directory) == len(world['characters'])-1
    assert len(history['state_changes']) == 64 and len(milestones) == 8
    assert family['truncated'] and len(family['nodes']) == 24
    assert len(calendar['scheduled']['items']) <= calendar['scheduled']['limit']
    assert estimate(messages) <= 32768-2000 and report['llm_calls'] == 0
    assert after['world_state']['meta']['world_time'] > world['meta']['world_time']
    print('R18', dict(characters=len(world['characters']), history_window=len(history['state_changes']),
          context_estimate=estimate(messages), family_nodes=len(family['nodes']), recipients=len(directory),
          milestones=len(milestones), lta_calls=report['llm_calls'], seconds=round(perf_counter()-started,3)))


@given(st.lists(st.sampled_from(['restore_npc', 'restore_quiet', 'reopen', 'repeat_worker']),
                min_size=2, max_size=7))
@settings(max_examples=5, deadline=None)
def test_variant_replay_preserves_selected_npc_and_knowledge(operations):
    with TemporaryDirectory() as directory:
        repo = Repository(Path(directory) / 'variants.sqlite')
        sid = load_fixture(repo, 'base')['save']
        before = repo.get_snapshot(sid)
        variants = {}
        for kind, name, raw in [('start', 'restore_npc', promoted(before)),
                                ('regenerate', 'restore_quiet', raw_for(before))]:
            jid = repo.begin_job(sid, 'Я доверяю Ладе.' if kind == 'start' else '', kind, CONFIG)
            run_job(repo, jid, raw)
            assert repo.get_job(jid)['status'] == 'saved', repo.get_job(jid)['error']
            turn, = repo.list_turns(sid)
            variants[name] = (turn['active_variant_id'], repo.get_snapshot(sid))
        selected = 'restore_quiet'
        for operation in operations:
            if operation == 'reopen':
                repo = Repository(repo.path)
            elif operation == 'repeat_worker':
                assert run_job(repo, jid, raw) == []
            else:
                selected = operation
                repo.select_variant(sid, turn['id'], variants[selected][0], repo.get_save(sid)['revision'])
            current = repo.get_snapshot(sid)
            assert current == variants[selected][1]
            assert ('new_npc' in current['world_state']['characters']) == (selected == 'restore_npc')
            assert ('qa_kirill:workshop' in current['world_state']['knowledge']) == (selected == 'restore_npc')
        repo.rollback_last(sid)
        assert repo.get_snapshot(sid) == before
