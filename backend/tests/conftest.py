"""Pytest config for PatchPilot backend tests."""

import os

import pytest
from dotenv import load_dotenv

load_dotenv()


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: real LLM or GitHub network; opt-in via -m integration",
    )


def pytest_collection_modifyitems(config, items):
    """Keep default pytest free of network and paid LLM calls."""

    if config.option.markexpr:
        return

    items[:] = [
        item
        for item in items
        if item.get_closest_marker("integration") is None
    ]


def pytest_runtest_setup(item):
    if item.get_closest_marker("integration") is None:
        return

    missing = [
        name
        for name in ("OPEN_AI_KEY", "GITHUB_TOKEN")
        if not os.getenv(name)
    ]

    if missing:
        pytest.skip(
            "integration test requires "
            + ", ".join(missing)
        )
