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
    if request.node.get_closest_marker('extraction_current') is not None:
        return
    monkeypatch.setattr('backend.runtime_v3.player_actions.EXTRACTION_VERSION',
                        8 if request.node.get_closest_marker('extraction_v8') else 7 if request.node.get_closest_marker('extraction_v7') else 6 if request.node.get_closest_marker('extraction_v6') else 5)


def pytest_configure(config):
    config.addinivalue_line('markers', 'extraction_v6: exercise recorded Extraction/6 jobs')
    config.addinivalue_line('markers', 'extraction_v7: exercise recorded Extraction/7 jobs')
    config.addinivalue_line('markers', 'extraction_v8: exercise recorded Extraction/8 jobs')
    config.addinivalue_line('markers', 'extraction_current: exercise the production default')


@pytest.fixture
def archived_world_review(monkeypatch):
    """Start the recorded pre-266 contract when replaying its repair/reaudit dialog."""
    import json
    from backend.repositories.preparation import Repository
    begin=Repository.begin_preparation

    def begin_archived(repo,wid,kind,text,config,revision,*,receipt=False):
        result=begin(repo,wid,kind,text,config,revision,receipt=receipt)
        jid=result[0] if receipt else result
        if kind=='draft_world':
            journal=json.loads(repo.preparation_job(jid)['response_journal'] or '{}')
            journal['generation_contract']={'version':6,'portrait_version':2}
            repo.save_response_journal(jid,journal)
        return result
    monkeypatch.setattr(Repository,'begin_preparation',begin_archived)
