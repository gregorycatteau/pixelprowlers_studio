import pytest
from ai_assistants.utils.registry import get_assistant_id_from_registry, load_agents_registry


@pytest.mark.agents
def test_registry_loads_entries():
    registry = load_agents_registry()
    assert "Bruce" in registry
    assert registry["Bruce"].startswith("asst_")


@pytest.mark.agents
def test_registry_resolution_bruce_and_claire():
    bruce_id = get_assistant_id_from_registry("Bruce")
    claire_id = get_assistant_id_from_registry("claire")
    assert bruce_id and bruce_id.startswith("asst_")
    assert claire_id and claire_id.startswith("asst_")
