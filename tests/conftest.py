import pytest

from agent.config import Settings


@pytest.fixture
def settings() -> Settings:
    """Fake settings: no test ever talks to the real helpdesk or the real model."""
    return Settings(
        helpdesk_url="https://helpdesk.test",
        helpdesk_key="test-key",
        candidate_email="me@example.com",
        candidate_name="",
        llm_base_url="https://llm.test/v1",
        llm_model="test-model",
        llm_api_key="test-llm-key",
        llm_reasoning_effort="",
    )
