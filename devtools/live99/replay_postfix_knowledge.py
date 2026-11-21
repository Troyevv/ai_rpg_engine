"""Offline characterization of #245's saved-but-missing Knowledge.

Run: python -m devtools.live99.replay_postfix_knowledge
No provider, SQLite mutation, or product workaround. The one-field diagnostic
control is never written to a game save. It is not a proposed product fix.
"""
import hashlib
import json
from copy import deepcopy
from pathlib import Path

from backend.runtime_v3.resolver import StateResolver


def replay():
    root = Path(__file__).resolve().parents[2]
    evidence = json.loads((root / 'tests/fixtures/issue99_postfix/knowledge.json').read_text())
    source = (root / evidence['before_fixture']).read_bytes()
    assert hashlib.sha256(source).hexdigest() == evidence['before_fixture_sha256']
    before = json.loads(source)['before']
    original = evidence['accepted_extraction']
    control = deepcopy(original)
    control['events'][0]['fact_ids'] = [fact['id'] for fact in original['facts']]
    results = {}
    for name, raw in [('live_response', original), ('fact_ids_only_control', control)]:
        resolved = StateResolver(before, evidence['narrative'], evidence['player_input'],
                                 require_player_agency=True).resolve(raw)
        results[name] = dict(
            accepted=True,
            knowledge_added=sorted(set(resolved.state['knowledge']) - set(before['knowledge'])),
            knowledge_warnings=[w for w in resolved.warnings if w['code'] == 'knowledge_path_invalid'],
        )
    assert not results['live_response']['knowledge_added']
    assert len(results['live_response']['knowledge_warnings']) == 4
    assert len(results['fact_ids_only_control']['knowledge_added']) == 4
    assert not results['fact_ids_only_control']['knowledge_warnings']
    return results


if __name__ == '__main__':
    print(json.dumps(replay(), ensure_ascii=False, indent=2))
