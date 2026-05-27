"""Auto-discovered conftest for tests/conversational/.

Re-exports fixtures from conftest_conversational so pytest finds them,
and applies the conversational + live_llm markers to all tests in this package.
"""

from tests.conversational.conftest_conversational import (  # noqa: F401
    live_minimax_handler,
    lingwen_handler,
    send_message,
)

import pytest


def pytest_collection_modifyitems(items):
    """Auto-add conversational + live_llm markers to every test in this package."""
    for item in items:
        if "conversational" in str(item.fspath):
            item.add_marker(pytest.mark.conversational)
            item.add_marker(pytest.mark.live_llm)
