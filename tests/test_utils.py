"""Test utilities for agent testing.

This module provides helpers for testing Strands agents in local development.
"""

import os
import uuid
from typing import Any
from unittest.mock import MagicMock, AsyncMock

import boto3
from moto import mock_aws


def set_local_test_env() -> dict[str, str]:
    """Set up environment variables for local testing.

    Returns:
        Dictionary of environment variables set
    """
    env_vars = {
        "ENV": "local",
        "AWS_REGION": "us-east-1",
        "AWS_DEFAULT_REGION": "us-east-1",
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SECURITY_TOKEN": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "CHAT_SESSIONS_TABLE_NAME": "test-chat-sessions",
        "MEETINGS_TABLE_NAME": "test-meetings",
        "SESSIONS_BUCKET_NAME": "",  # Not needed for local
        "JWT_SECRET_KEY": "test-secret-key-for-development-only",
    }

    for key, value in env_vars.items():
        os.environ[key] = value

    return env_vars


def generate_test_session_id() -> str:
    """Generate a test session ID.

    Returns:
        UUID string for test session
    """
    return f"test-session-{uuid.uuid4()}"


def generate_test_user_id() -> str:
    """Generate a test user ID.

    Returns:
        UUID string for test user
    """
    return f"test-user-{uuid.uuid4()}"


@mock_aws
def create_test_dynamodb_tables() -> dict[str, Any]:
    """Create mock DynamoDB tables for testing.

    Returns:
        Dictionary with table resources
    """
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

    # Create chat sessions table
    chat_sessions_table = dynamodb.create_table(
        TableName="test-chat-sessions",
        KeySchema=[{"AttributeName": "session_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "session_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )

    # Create meetings table
    meetings_table = dynamodb.create_table(
        TableName="test-meetings",
        KeySchema=[{"AttributeName": "meeting_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "meeting_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )

    return {
        "chat_sessions": chat_sessions_table,
        "meetings": meetings_table,
    }


def mock_bedrock_response(content: str) -> dict[str, Any]:
    """Create a mock Bedrock model response.

    Args:
        content: Response content to return

    Returns:
        Mock response dictionary
    """
    return {
        "content": content,
        "role": "assistant",
        "stop_reason": "end_turn",
    }


def create_mock_bedrock_model(response_content: str = "Test response"):
    """Create a mock BedrockModel for testing.

    Args:
        response_content: Content to return in mock responses

    Returns:
        Mock BedrockModel instance
    """
    mock_model = MagicMock()
    mock_model.generate = AsyncMock(return_value=mock_bedrock_response(response_content))
    return mock_model


class AgentTestHelper:
    """Helper class for testing Strands agents."""

    def __init__(self):
        """Initialize test helper with default test IDs."""
        self.session_id = generate_test_session_id()
        self.user_id = generate_test_user_id()
        self.messages: list[dict[str, str]] = []

    def add_user_message(self, content: str) -> None:
        """Add a user message to the conversation history.

        Args:
            content: Message content
        """
        self.messages.append({"role": "user", "content": content})

    def add_assistant_message(self, content: str) -> None:
        """Add an assistant message to the conversation history.

        Args:
            content: Message content
        """
        self.messages.append({"role": "assistant", "content": content})

    def get_conversation_history(self) -> list[dict[str, str]]:
        """Get full conversation history.

        Returns:
            List of message dictionaries
        """
        return self.messages.copy()

    def reset(self) -> None:
        """Reset test helper state."""
        self.session_id = generate_test_session_id()
        self.user_id = generate_test_user_id()
        self.messages.clear()
