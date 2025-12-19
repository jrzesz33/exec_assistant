"""Pytest configuration and fixtures for agent testing."""

import os
import shutil
from pathlib import Path

import pytest
from moto import mock_aws

from tests.test_utils import set_local_test_env, create_test_dynamodb_tables


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Set up test environment variables for all tests."""
    set_local_test_env()


@pytest.fixture
def clean_session_dir():
    """Clean up .sessions directory before and after each test."""
    sessions_dir = Path(".sessions")

    # Clean before test
    if sessions_dir.exists():
        shutil.rmtree(sessions_dir)

    yield

    # Clean after test
    if sessions_dir.exists():
        shutil.rmtree(sessions_dir)


@pytest.fixture
def mock_aws_services():
    """Mock AWS services for testing."""
    with mock_aws():
        tables = create_test_dynamodb_tables()
        yield tables


@pytest.fixture
def test_session_id() -> str:
    """Generate a unique test session ID."""
    from tests.test_utils import generate_test_session_id

    return generate_test_session_id()


@pytest.fixture
def test_user_id() -> str:
    """Generate a unique test user ID."""
    from tests.test_utils import generate_test_user_id

    return generate_test_user_id()
