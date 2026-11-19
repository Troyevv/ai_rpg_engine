"""Distribute the entire collected suite across isolated CI runners, keeping module fixtures local."""
import json
import os
from collections import defaultdict
from pathlib import Path


def assignments(modules, timings, total):
    loads = [0.0] * total
    assigned = {}
    estimates = {path:timings.get(path, max(1.0, count * 0.5)) for path,count in modules.items()}
    for path in sorted(modules, key=lambda p:(-estimates[p],p)):
        shard = min(range(total), key=loads.__getitem__)
        assigned[path] = shard + 1
        loads[shard] += estimates[path]
    return assigned


def pytest_collection_modifyitems(config, items):
    index, total = map(int, os.environ['PYTEST_CI_SHARD'].split('/'))
    if not 1 <= index <= total:
        raise ValueError('Invalid CI shard index')
    modules = defaultdict(int)
    for item in items:
        modules[item.nodeid.split('::',1)[0]] += 1
    timings = json.loads(Path(__file__).with_name('pytest-seconds.json').read_text())
    owners = assignments(modules, timings, total)
    selected, rest = [], []
    for item in items:
        (selected if owners[item.nodeid.split('::',1)[0]]==index else rest).append(item)
    config.hook.pytest_deselected(items=rest)
    items[:] = selected
