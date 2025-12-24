"""Unit tests for Slack bot webhook handler."""

import hashlib
import hmac
import json
import time
from typing import Any
from unittest.mock import MagicMock

import pytest

from exec_assistant.interfaces.slack_bot import (
    SlackSignatureVerifier,
    SlackWebhookHandler,
)


class TestSlackSignatureVerifier:
    """Tests for Slack signature verification."""

    @pytest.fixture
    def signing_secret(self) -> str:
        """Test signing secret."""
        return "test_signing_secret_12345"

    @pytest.fixture
    def verifier(self, signing_secret: str) -> SlackSignatureVerifier:
        """Create a verifier instance."""
        return SlackSignatureVerifier(signing_secret)

    def test_verify_valid_signature(self, verifier: SlackSignatureVerifier) -> None:
        """Test verifying a valid signature."""
        # Create a valid signature
        timestamp = str(int(time.time()))
        body = "test request body"

        sig_basestring = f"v0:{timestamp}:{body}".encode()
        signature = (
            "v0="
            + hmac.new(
                verifier.signing_secret,
                sig_basestring,
                hashlib.sha256,
            ).hexdigest()
        )

        # Should verify successfully
        assert verifier.verify(body, timestamp, signature) is True

    def test_verify_invalid_signature(self, verifier: SlackSignatureVerifier) -> None:
        """Test verifying an invalid signature."""
        timestamp = str(int(time.time()))
        body = "test request body"
        signature = "v0=invalid_signature"

        # Should fail verification
        assert verifier.verify(body, timestamp, signature) is False

    def test_verify_old_timestamp_raises_error(
        self,
        verifier: SlackSignatureVerifier,
    ) -> None:
        """Test that old timestamps raise ValueError."""
        # Timestamp from 10 minutes ago
        old_timestamp = str(int(time.time()) - 600)
        body = "test request body"
        signature = "v0=dummy"

        # Should raise ValueError for old timestamp
        with pytest.raises(ValueError, match="timestamp too old"):
            verifier.verify(body, old_timestamp, signature)


class TestSlackWebhookHandler:
    """Tests for Slack webhook handler."""

    @pytest.fixture
    def handler(self) -> SlackWebhookHandler:
        """Create a webhook handler with verification disabled."""
        return SlackWebhookHandler(
            signing_secret="test_secret",
            skip_verification=True,
        )

    def test_handle_url_verification_challenge(
        self,
        handler: SlackWebhookHandler,
    ) -> None:
        """Test handling Slack URL verification challenge."""
        event = {
            "body": json.dumps(
                {
                    "type": "url_verification",
                    "challenge": "test_challenge_string",
                }
            ),
        }
        context = MagicMock()

        response = handler.handle_lambda(event, context)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["challenge"] == "test_challenge_string"

    def test_handle_meetings_slash_command(
        self,
        handler: SlackWebhookHandler,
    ) -> None:
        """Test handling /meetings slash command."""
        event = {
            "body": json.dumps(
                {
                    "command": "/meetings",
                    "user_id": "U12345",
                    "channel_id": "C67890",
                }
            ),
        }
        context = MagicMock()

        response = handler.handle_lambda(event, context)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert "response_type" in body
        assert body["response_type"] == "ephemeral"
        assert "meetings" in body["text"].lower() or "calendar" in body["text"].lower()

    def test_handle_unknown_slash_command(
        self,
        handler: SlackWebhookHandler,
    ) -> None:
        """Test handling unknown slash command."""
        event = {
            "body": json.dumps(
                {
                    "command": "/unknown",
                    "user_id": "U12345",
                    "channel_id": "C67890",
                }
            ),
        }
        context = MagicMock()

        response = handler.handle_lambda(event, context)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert "unknown" in body["text"].lower()

    def test_handle_direct_message_event(
        self,
        handler: SlackWebhookHandler,
    ) -> None:
        """Test handling direct message event."""
        event = {
            "body": json.dumps(
                {
                    "event": {
                        "type": "message",
                        "channel_type": "im",
                        "user": "U12345",
                        "text": "Hello bot!",
                        "channel": "D12345",
                    },
                }
            ),
        }
        context = MagicMock()

        response = handler.handle_lambda(event, context)

        # Should acknowledge the event
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["ok"] is True

    def test_handle_interactive_message(
        self,
        handler: SlackWebhookHandler,
    ) -> None:
        """Test handling interactive message (button click)."""
        event = {
            "body": json.dumps(
                {
                    "payload": json.dumps(
                        {
                            "type": "block_actions",
                            "user": {"id": "U12345"},
                            "actions": [
                                {
                                    "action_id": "start_prep",
                                    "value": "meeting-123",
                                }
                            ],
                        }
                    ),
                }
            ),
        }
        context = MagicMock()

        response = handler.handle_lambda(event, context)

        # Should acknowledge the interaction
        assert response["statusCode"] == 200

    def test_handle_invalid_json_returns_error(
        self,
        handler: SlackWebhookHandler,
    ) -> None:
        """Test handling invalid JSON body."""
        event = {
            "body": "invalid json {{{",
        }
        context = MagicMock()

        response = handler.handle_lambda(event, context)

        assert response["statusCode"] == 500

    def test_handle_missing_body_returns_error(
        self,
        handler: SlackWebhookHandler,
    ) -> None:
        """Test handling event with missing body."""
        event: dict[str, Any] = {}
        context = MagicMock()

        # Should handle gracefully (empty body parses as {})
        response = handler.handle_lambda(event, context)

        # Should return error for unknown type
        assert response["statusCode"] == 400


class TestSlackWebhookHandlerWithVerification:
    """Tests for Slack webhook handler with signature verification enabled."""

    @pytest.fixture
    def signing_secret(self) -> str:
        """Test signing secret."""
        return "test_signing_secret_xyz"

    @pytest.fixture
    def handler(self, signing_secret: str) -> SlackWebhookHandler:
        """Create a webhook handler with verification enabled."""
        return SlackWebhookHandler(
            signing_secret=signing_secret,
            skip_verification=False,
        )

    def create_signed_event(
        self,
        body_dict: dict[str, Any],
        signing_secret: str,
    ) -> dict[str, Any]:
        """Create a properly signed Slack event.

        Args:
            body_dict: Event body to sign
            signing_secret: Signing secret to use

        Returns:
            Lambda event with valid signature
        """
        timestamp = str(int(time.time()))
        body = json.dumps(body_dict)

        sig_basestring = f"v0:{timestamp}:{body}".encode()
        signature = (
            "v0="
            + hmac.new(
                signing_secret.encode("utf-8"),
                sig_basestring,
                hashlib.sha256,
            ).hexdigest()
        )

        return {
            "body": body,
            "headers": {
                "X-Slack-Request-Timestamp": timestamp,
                "X-Slack-Signature": signature,
            },
        }

    def test_valid_signature_accepted(
        self,
        handler: SlackWebhookHandler,
        signing_secret: str,
    ) -> None:
        """Test that valid signature is accepted."""
        event = self.create_signed_event(
            {
                "command": "/meetings",
                "user_id": "U12345",
                "channel_id": "C67890",
            },
            signing_secret,
        )
        context = MagicMock()

        response = handler.handle_lambda(event, context)

        # Should succeed
        assert response["statusCode"] == 200

    def test_invalid_signature_rejected(
        self,
        handler: SlackWebhookHandler,
    ) -> None:
        """Test that invalid signature is rejected."""
        event = {
            "body": json.dumps({"command": "/meetings"}),
            "headers": {
                "X-Slack-Request-Timestamp": str(int(time.time())),
                "X-Slack-Signature": "v0=invalid_signature",
            },
        }
        context = MagicMock()

        response = handler.handle_lambda(event, context)

        # Should reject with 401
        assert response["statusCode"] == 401
        body = json.loads(response["body"])
        assert "error" in body

    def test_missing_signature_rejected(
        self,
        handler: SlackWebhookHandler,
    ) -> None:
        """Test that missing signature is rejected."""
        event = {
            "body": json.dumps({"command": "/meetings"}),
            "headers": {},  # Missing signature headers
        }
        context = MagicMock()

        response = handler.handle_lambda(event, context)

        # Should reject
        assert response["statusCode"] in [401, 500]
