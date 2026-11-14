"""Keep general runtime tests reproducible without model weights or network.

Semantic tests inject controlled encoders; benchmark_semantic_v2 runs real weights.
"""
import pytest

@pytest.fixture(autouse=True)
def deterministic_retrieval_environment(monkeypatch):
    monkeypatch.setenv('RPG_SEMANTIC_ENABLED', '0')


@pytest.fixture(autouse=True)
def recorded_extraction_fixture_version(request, monkeypatch):
    """Pre-255 provider fixtures are recorded RawTurnResult/v5 payloads.

    Keep exercising those jobs with their actual wire contract. New v6 suites
    opt out explicitly; no production parser accepts legacy payloads as v6.
    Direct tests specifying v1-v5 resolver/context options remain unchanged.
    """
    if request.node.get_closest_marker('extraction_v6') is None:
        monkeypatch.setattr('backend.runtime_v3.player_actions.EXTRACTION_VERSION', 5)


def pytest_configure(config):
    config.addinivalue_line('markers', 'extraction_v6: exercise new server-default Extraction/6 jobs')
