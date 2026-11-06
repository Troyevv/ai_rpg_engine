"""Check the QA oracle against persisted production turn numbering."""
from copy import deepcopy

import pytest

from backend.repositories.preparation import Repository
from devtools.live99.evidence import oracle, snapshot
from devtools.narrative_test_world import load_fixture
from test_narrative_test_world import ordinary_job


def test_oracle_accepts_zero_based_start_then_turn_and_regeneration(tmp_path):
    repo = Repository(tmp_path / 'qa.sqlite')
    sid = load_fixture(repo)['save']
    for kind, sequence in [('start', 0), ('turn', 1), ('regenerate', 1)]:
        before = snapshot(repo.path, sid)
        ordinary_job(repo, sid, kind)
        after = snapshot(repo.path, sid)
        projection = dict(repo.get_save(sid), turns=repo.list_turns(sid))
        assert after['last_turn']['sequence'] == sequence
        oracle(before, after, projection, kind)

        wrong = deepcopy(after)
        wrong['last_turn']['sequence'] += 1
        with pytest.raises(ValueError, match='Wrong sequence'):
            oracle(before, wrong, projection, kind)

        empty = deepcopy(after)
        empty['last_turn']['assistant_text'] = '  '
        with pytest.raises(ValueError, match='empty committed scene'):
            oracle(before, empty, projection, kind)
