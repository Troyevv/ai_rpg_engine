"""Keep general runtime tests reproducible without model weights or network.

Semantic tests inject controlled encoders; benchmark_semantic_v2 runs real weights.
"""
import pytest

@pytest.fixture(autouse=True)
def deterministic_retrieval_environment(monkeypatch):
    monkeypatch.setenv('RPG_SEMANTIC_ENABLED', '0')
