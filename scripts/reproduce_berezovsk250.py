"""Read-only replay of independent #250 findings. Never calls a provider.

Run from the repository with PYTHONPATH=. and the extracted original archive
life248-playability-live as the sole argument. No saves or responses are edited.
"""
from copy import deepcopy
import gzip
import json
from pathlib import Path
import sys

from backend.runtime_v3.models import WorldHistoryV3
from backend.runtime_v3.long_term import advance_clock
from backend.runtime_v3.player_actions import resolver_options
from backend.runtime_v3.resolver import StateResolver


def read(path):
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == '.gz' else data)


def reproduce(archive):
    fixture = read(Path(__file__).resolve().parents[1] / 'tests/fixtures/issue250/berezovsk.json.gz')['002']
    state = fixture['before']
    resolved = StateResolver(state, fixture['narrative'], fixture['player_input'],
        **resolver_options(state, fixture['player_input'], contract_version=3)).resolve(fixture['responses']['D'][0])
    leaked = [choice for choice in resolved.choices if 'Про письмо' in choice.get('speech', '')]
    secret = state['knowledge'].get('char_alexey:fact_viktor_letter')

    directory = archive / 'lta/turns/001'
    original = read(directory / 'before.json.gz')['snapshot']
    requests = read(directory / 'requests.json.gz')
    narrative, extraction = requests[2:4]
    messages = json.loads(extraction['context_json'])
    current = json.loads(next(m['content'].split('\n', 1)[1] for m in messages
        if m['content'].startswith('Текущее состояние / GM-only\n')))
    candidate = deepcopy(original)
    candidate['world_state']['meta']['turn_id'] = current['meta']['turn_id']
    advance_clock(candidate, current['meta']['world_time'], WorldHistoryV3().to_dict())
    # The exact recorded private camera is the LTA resolver input. Relevance
    # selection changed in #250; this isolates the original second group.
    candidate['world_state']['camera'] = current['camera']
    before = candidate['world_state']
    protected = original['world_state']['camera']['controlled_actor_id']
    result = StateResolver(before, narrative['response_text'], '', observed=False,
        mode='background', protected_actor_id=protected,
        protected_knowledge_actor_ids=[protected]).resolve(extraction['response_text'])
    return dict(provider_calls=0, replay='original D/002 and original LTA second group',
        choice_secret_known=bool(secret and secret['status']=='known'), leaked_choices=leaked,
        pasha_before=before['characters']['char_pasha']['location_id'],
        pasha_after=result.state['characters']['char_pasha']['location_id'],
        knowledge_unchanged=result.state['knowledge']==before['knowledge'])


if __name__ == '__main__':
    print(json.dumps(reproduce(Path(sys.argv[1])), ensure_ascii=False, indent=2))
