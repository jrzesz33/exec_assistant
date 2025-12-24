"""Slack bot webhook handler for Executive Assistant.

This module implements the Slack bot interface including:
- Webhook signature verification
- Event and command routing
- Slash commands (/meetings)
- Interactive message handling (buttons, modals)
- DM message handling for chat sessions
"""

import hashlib
import hmac
import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class SlackSignatureVerifier:
    """Verifies Slack request signatures for security."""

    def __init__(self, signing_secret: str) -> None:
        """Initialize verifier with Slack signing secret.

        Args:
            signing_secret: Slack app signing secret
        """
        self.signing_secret = signing_secret.encode("utf-8")

    def verify(
        self,
        request_body: str,
        timestamp: str,
        signature: str,
    ) -> bool:
        """Verify Slack request signature.

        Args:
            request_body: Raw request body string
            timestamp: X-Slack-Request-Timestamp header
            signature: X-Slack-Signature header

        Returns:
            True if signature is valid, False otherwise

        Raises:
            ValueError: If timestamp is too old (replay attack protection)
        """
        # Check timestamp is recent (within 5 minutes)
        current_time = int(time.time())
        if abs(current_time - int(timestamp)) > 60 * 5:
            msg = "request_timestamp=<%s> | request timestamp too old"
            logger.warning(msg, timestamp)
            raise ValueError("Request timestamp too old")

        # Compute expected signature
        sig_basestring = f"v0:{timestamp}:{request_body}".encode()
        expected_signature = (
            "v0="
            + hmac.new(
                self.signing_secret,
                sig_basestring,
                hashlib.sha256,
            ).hexdigest()
        )

        # Compare signatures (constant time comparison)
        is_valid = hmac.compare_digest(expected_signature, signature)

        if not is_valid:
            logger.warning("signature_valid=<false> | invalid slack signature")

        return is_valid


class SlackWebhookHandler:
    """Handles incoming Slack webhooks and routes to appropriate handlers."""

    def __init__(
        self,
        signing_secret: str,
        skip_verification: bool = False,
    ) -> None:
        """Initialize webhook handler.

        Args:
            signing_secret: Slack app signing secret
            skip_verification: Skip signature verification (for local dev only!)
        """
        self.verifier = SlackSignatureVerifier(signing_secret)
        self.skip_verification = skip_verification

        if skip_verification:
            logger.warning("skip_verification=<true> | signature verification disabled!")

    def handle_lambda(self, event: dict[str, Any], context: Any) -> dict[str, Any]:
        """Lambda handler entrypoint for Slack webhooks.

        Args:
            event: Lambda event (API Gateway proxy format)
            context: Lambda context

        Returns:
            API Gateway response dict
        """
        logger.debug(
            "event=<%s> | processing slack webhook",
            event.get("requestContext", {}).get("requestId"),
        )

        try:
            # Verify signature
            if not self.skip_verification:
                request_body = event.get("body", "")
                timestamp = event.get("headers", {}).get("X-Slack-Request-Timestamp", "")
                signature = event.get("headers", {}).get("X-Slack-Signature", "")

                if not self.verifier.verify(request_body, timestamp, signature):
                    return {
                        "statusCode": 401,
                        "body": json.dumps({"error": "Invalid signature"}),
                    }

            # Parse body
            body = json.loads(event.get("body", "{}"))

            # Handle URL verification challenge
            if body.get("type") == "url_verification":
                return {
                    "statusCode": 200,
                    "body": json.dumps({"challenge": body.get("challenge")}),
                }

            # Route to appropriate handler
            if "command" in body:
                # Slash command
                return self.handle_slash_command(body)
            elif "event" in body:
                # Event subscription
                return self.handle_event(body)
            elif "payload" in body:
                # Interactive message (button click, etc.)
                payload = json.loads(body["payload"])
                return self.handle_interactive(payload)
            else:
                logger.warning("body=<%s> | unknown webhook type", body.get("type"))
                return {
                    "statusCode": 400,
                    "body": json.dumps({"error": "Unknown webhook type"}),
                }

        except Exception as e:
            logger.error("error=<%s> | error handling webhook", str(e), exc_info=True)
            return {
                "statusCode": 500,
                "body": json.dumps({"error": "Internal server error"}),
            }

    def handle_slash_command(self, body: dict[str, Any]) -> dict[str, Any]:
        """Handle slash commands.

        Args:
            body: Parsed request body

        Returns:
            API Gateway response
        """
        command = body.get("command", "")
        user_id = body.get("user_id", "")
        channel_id = body.get("channel_id", "")

        logger.info(
            "command=<%s>, user_id=<%s> | handling slash command",
            command,
            user_id,
        )

        if command == "/meetings":
            return self.handle_meetings_command(user_id, channel_id, body)
        else:
            return {
                "statusCode": 200,
                "body": json.dumps(
                    {
                        "text": f"Unknown command: {command}",
                        "response_type": "ephemeral",
                    }
                ),
            }

    def handle_meetings_command(
        self,
        user_id: str,
        channel_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle /meetings slash command.

        Args:
            user_id: Slack user ID
            channel_id: Slack channel ID
            body: Command body

        Returns:
            API Gateway response with meeting list
        """
        logger.info("user_id=<%s> | listing meetings", user_id)

        # TODO: Query DynamoDB for user's meetings
        # For Phase 1, return placeholder message

        response_text = (
            ":calendar: *Your Upcoming Meetings*\n\n"
            "No meetings found yet. Calendar integration coming soon!\n\n"
            "_This is a Phase 1 placeholder. Once calendar integration is complete, "
            "you'll see your upcoming meetings here._"
        )

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(
                {
                    "response_type": "ephemeral",  # Only visible to user
                    "text": response_text,
                }
            ),
        }

    def handle_event(self, body: dict[str, Any]) -> dict[str, Any]:
        """Handle event subscriptions.

        Args:
            body: Event body

        Returns:
            API Gateway response
        """
        event = body.get("event", {})
        event_type = event.get("type", "")
        user_id = event.get("user", "")

        logger.info(
            "event_type=<%s>, user_id=<%s> | handling event",
            event_type,
            user_id,
        )

        # Handle direct messages (for chat sessions)
        if event_type == "message" and event.get("channel_type") == "im":
            return self.handle_direct_message(event)

        # Acknowledge other events
        return {"statusCode": 200, "body": json.dumps({"ok": True})}

    def handle_direct_message(self, event: dict[str, Any]) -> dict[str, Any]:
        """Handle direct messages to the bot.

        Args:
            event: Message event

        Returns:
            API Gateway response
        """
        user_id = event.get("user", "")
        text = event.get("text", "")
        channel = event.get("channel", "")

        logger.info(
            "user_id=<%s>, text=<%s> | handling direct message",
            user_id,
            text,
        )

        # TODO: Check if user has active chat session
        # TODO: Route message to appropriate chat session handler
        # For Phase 1, just acknowledge

        return {"statusCode": 200, "body": json.dumps({"ok": True})}

    def handle_interactive(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Handle interactive messages (button clicks, etc.).

        Args:
            payload: Interactive payload

        Returns:
            API Gateway response
        """
        action_type = payload.get("type", "")
        user_id = payload.get("user", {}).get("id", "")
        actions = payload.get("actions", [])

        logger.info(
            "action_type=<%s>, user_id=<%s>, actions=<%s> | handling interactive message",
            action_type,
            user_id,
            len(actions),
        )

        # TODO: Handle "Start Prep" button clicks
        # TODO: Handle "Remind me later" button clicks
        # For Phase 1, acknowledge

        return {"statusCode": 200, "body": json.dumps({"ok": True})}


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entrypoint for Slack webhooks.

    Args:
        event: API Gateway event
        context: Lambda context

    Returns:
        API Gateway response
    """
    # Get configuration from environment
    import os

    signing_secret = os.environ.get("SLACK_SIGNING_SECRET", "")
    skip_verification = os.environ.get("SKIP_SIGNATURE_VERIFICATION", "false").lower() == "true"

    # Create handler and process event
    handler = SlackWebhookHandler(
        signing_secret=signing_secret,
        skip_verification=skip_verification,
    )

    return handler.handle_lambda(event, context)
