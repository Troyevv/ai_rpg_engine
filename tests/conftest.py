"""Keep general runtime tests reproducible without model weights or network.

Semantic tests inject controlled encoders; benchmark_semantic_v2 runs real weights.
"""
import pytest

@pytest.fixture(autouse=True)
def deterministic_retrieval_environment(monkeypatch):
    monkeypatch.setenv('RPG_SEMANTIC_ENABLED', '0')

@pytest.fixture
def legacy_generation_v5(monkeypatch):
    """Exercise captured pre-Blueprint jobs without changing their contract."""
    from backend.services import world_generation
    monkeypatch.setattr(world_generation, 'PROMPT_VERSION', 'initial-world-stages-5')
