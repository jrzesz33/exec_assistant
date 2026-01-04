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
import os
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
import requests
from botocore.exceptions import ClientError

from exec_assistant.shared.logging import get_logger
from exec_assistant.shared.models import ChatSession, ChatSessionState, Meeting, MeetingStatus

logger = get_logger(__name__)


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

        if not actions:
            logger.warning(
                "action_type=<%s>, user_id=<%s> | no actions in interactive payload",
                action_type,
                user_id,
            )
            return {"statusCode": 200, "body": json.dumps({"ok": True})}

        action = actions[0]
        action_id = action.get("action_id", "")
        action_value = action.get("value", "{}")

        logger.info(
            "action_type=<%s>, user_id=<%s>, action_id=<%s> | handling interactive message",
            action_type,
            user_id,
            action_id,
        )

        # Handle meeting prep buttons
        if action_id == "start_prep":
            return self.handle_start_prep(user_id, action_value, payload)
        elif action_id == "remind_later":
            return self.handle_remind_later(user_id, action_value, payload)
        else:
            logger.warning(
                "action_id=<%s>, user_id=<%s> | unknown action id",
                action_id,
                user_id,
            )
            return {"statusCode": 200, "body": json.dumps({"ok": True})}

    def handle_start_prep(
        self, user_id: str, action_value: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle "Start Prep" button click.

        Creates a chat session, updates meeting status, and initiates
        the meeting prep conversation with the Meeting Coordinator agent.

        Args:
            user_id: Slack user ID
            action_value: JSON string with meeting_id and user_id
            payload: Full interactive payload

        Returns:
            API Gateway response
        """
        try:
            # Parse action value
            value_data = json.loads(action_value)
            meeting_id = value_data.get("meeting_id")

            if not meeting_id:
                logger.error(
                    "user_id=<%s> | missing meeting_id in action value",
                    user_id,
                )
                return {"statusCode": 400, "body": json.dumps({"error": "Missing meeting_id"})}

            logger.info(
                "user_id=<%s>, meeting_id=<%s> | starting prep session",
                user_id,
                meeting_id,
            )

            # Get DynamoDB tables
            dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
            meetings_table = dynamodb.Table(os.environ.get("MEETINGS_TABLE_NAME", "exec-assistant-meetings"))
            sessions_table = dynamodb.Table(os.environ.get("CHAT_SESSIONS_TABLE_NAME", "exec-assistant-chat-sessions"))

            # Fetch meeting
            response = meetings_table.get_item(Key={"meeting_id": meeting_id})
            if "Item" not in response:
                logger.error(
                    "meeting_id=<%s> | meeting not found",
                    meeting_id,
                )
                return self._update_slack_message(
                    payload,
                    "❌ Meeting not found. It may have been cancelled.",
                )

            meeting = Meeting.from_dynamodb(response["Item"])

            # Check if session already exists
            if meeting.chat_session_id:
                logger.warning(
                    "meeting_id=<%s>, existing_session_id=<%s> | prep session already exists",
                    meeting_id,
                    meeting.chat_session_id,
                )
                return self._update_slack_message(
                    payload,
                    "✅ Prep session already started! Continuing in DM...",
                )

            # Create chat session
            session_id = f"session-{uuid.uuid4().hex[:16]}"
            expires_at = datetime.now(UTC) + timedelta(hours=24)

            chat_session = ChatSession(
                session_id=session_id,
                user_id=user_id,
                meeting_id=meeting_id,
                state=ChatSessionState.ACTIVE,
                expires_at=expires_at,
            )

            # Save chat session
            sessions_table.put_item(Item=chat_session.to_dynamodb())

            # Update meeting status and link session
            meeting.status = MeetingStatus.PREP_IN_PROGRESS
            meeting.chat_session_id = session_id
            meeting.updated_at = datetime.now(UTC)
            meetings_table.put_item(Item=meeting.to_dynamodb())

            logger.info(
                "user_id=<%s>, meeting_id=<%s>, session_id=<%s> | prep session created",
                user_id,
                meeting_id,
                session_id,
            )

            # Update Slack message to show session started
            self._update_slack_message(
                payload,
                f"✅ Prep session started! Check your DMs to continue.\n\nMeeting: *{meeting.title}*",
            )

            # Send first message to user via DM
            self._send_slack_dm(
                user_id,
                self._build_prep_greeting(meeting),
            )

            return {"statusCode": 200, "body": json.dumps({"ok": True})}

        except json.JSONDecodeError as e:
            logger.error(
                "user_id=<%s>, error=<%s> | invalid action value json",
                user_id,
                str(e),
            )
            return {"statusCode": 400, "body": json.dumps({"error": "Invalid action value"})}

        except ClientError as e:
            logger.error(
                "user_id=<%s>, error_code=<%s>, error=<%s> | dynamodb error",
                user_id,
                e.response["Error"]["Code"],
                str(e),
                exc_info=True,
            )
            return {"statusCode": 500, "body": json.dumps({"error": "Database error"})}

        except Exception as e:
            logger.error(
                "user_id=<%s>, error=<%s> | failed to start prep session",
                user_id,
                str(e),
                exc_info=True,
            )
            return {"statusCode": 500, "body": json.dumps({"error": "Internal error"})}

    def handle_remind_later(
        self, user_id: str, action_value: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle "Remind Me Later" button click.

        Schedules a reminder notification in 2 hours via EventBridge.

        Args:
            user_id: Slack user ID
            action_value: JSON string with meeting_id and user_id
            payload: Full interactive payload

        Returns:
            API Gateway response
        """
        try:
            # Parse action value
            value_data = json.loads(action_value)
            meeting_id = value_data.get("meeting_id")

            if not meeting_id:
                logger.error(
                    "user_id=<%s> | missing meeting_id in action value",
                    user_id,
                )
                return {"statusCode": 400, "body": json.dumps({"error": "Missing meeting_id"})}

            logger.info(
                "user_id=<%s>, meeting_id=<%s> | scheduling reminder",
                user_id,
                meeting_id,
            )

            # Schedule reminder event in 2 hours
            events_client = boto3.client("events", region_name=os.environ.get("AWS_REGION", "us-east-1"))
            reminder_time = datetime.now(UTC) + timedelta(hours=2)

            # Create one-time EventBridge rule
            rule_name = f"prep-reminder-{meeting_id}-{int(reminder_time.timestamp())}"
            schedule_expression = f"at({reminder_time.strftime('%Y-%m-%dT%H:%M:%S')})"

            events_client.put_rule(
                Name=rule_name,
                ScheduleExpression=schedule_expression,
                State="ENABLED",
                Description=f"Remind user {user_id} about meeting {meeting_id}",
            )

            # Add target to trigger prep handler again
            event_bus_name = os.environ.get("EVENT_BUS_NAME", "default")
            events_client.put_targets(
                Rule=rule_name,
                Targets=[
                    {
                        "Id": "1",
                        "Arn": f"arn:aws:events:{os.environ.get('AWS_REGION', 'us-east-1')}:{os.environ.get('AWS_ACCOUNT_ID', '')}:event-bus/{event_bus_name}",
                        "RoleArn": os.environ.get("EVENTBRIDGE_ROLE_ARN", ""),
                        "EventBusName": event_bus_name,
                        "Input": json.dumps(
                            {
                                "source": "exec-assistant.reminder",
                                "detail-type": "MeetingPrepRequired",
                                "detail": {
                                    "meeting_id": meeting_id,
                                    "user_id": user_id,
                                    "reminder": True,
                                },
                            }
                        ),
                    }
                ],
            )

            logger.info(
                "user_id=<%s>, meeting_id=<%s>, reminder_time=<%s> | reminder scheduled",
                user_id,
                meeting_id,
                reminder_time.isoformat(),
            )

            # Update Slack message
            self._update_slack_message(
                payload,
                f"⏰ Reminder set! I'll ping you again in 2 hours.\n\nMeeting: *{value_data.get('title', 'Untitled')}*",
            )

            return {"statusCode": 200, "body": json.dumps({"ok": True})}

        except json.JSONDecodeError as e:
            logger.error(
                "user_id=<%s>, error=<%s> | invalid action value json",
                user_id,
                str(e),
            )
            return {"statusCode": 400, "body": json.dumps({"error": "Invalid action value"})}

        except ClientError as e:
            logger.error(
                "user_id=<%s>, error_code=<%s>, error=<%s> | eventbridge error",
                user_id,
                e.response["Error"]["Code"],
                str(e),
                exc_info=True,
            )
            return {"statusCode": 500, "body": json.dumps({"error": "Scheduling error"})}

        except Exception as e:
            logger.error(
                "user_id=<%s>, error=<%s> | failed to schedule reminder",
                user_id,
                str(e),
                exc_info=True,
            )
            return {"statusCode": 500, "body": json.dumps({"error": "Internal error"})}

    def _update_slack_message(self, payload: dict[str, Any], text: str) -> dict[str, Any]:
        """Update the original Slack message.

        Args:
            payload: Interactive payload with response_url
            text: New message text

        Returns:
            API Gateway response
        """
        response_url = payload.get("response_url", "")

        if not response_url:
            logger.warning("response_url not found in payload")
            return {"statusCode": 200, "body": json.dumps({"ok": True})}

        try:
            # Send message update to Slack
            response = requests.post(
                response_url,
                json={
                    "replace_original": True,
                    "text": text,
                },
                timeout=5,
            )

            if response.status_code != 200:
                logger.warning(
                    "status_code=<%d>, response=<%s> | failed to update slack message",
                    response.status_code,
                    response.text,
                )

            return {"statusCode": 200, "body": json.dumps({"ok": True})}

        except Exception as e:
            logger.error(
                "error=<%s> | failed to update slack message",
                str(e),
                exc_info=True,
            )
            return {"statusCode": 200, "body": json.dumps({"ok": True})}

    def _send_slack_dm(self, user_id: str, message: str) -> None:
        """Send a direct message to user via Slack API.

        Args:
            user_id: Slack user ID
            message: Message text to send
        """
        try:
            slack_bot_token = os.environ.get("SLACK_BOT_TOKEN", "")

            response = requests.post(
                "https://slack.com/api/chat.postMessage",
                headers={
                    "Authorization": f"Bearer {slack_bot_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "channel": user_id,
                    "text": message,
                },
                timeout=10,
            )

            response_data = response.json()

            if not response_data.get("ok"):
                logger.error(
                    "user_id=<%s>, error=<%s> | slack api error",
                    user_id,
                    response_data.get("error", "unknown"),
                )
            else:
                logger.info(
                    "user_id=<%s> | dm sent successfully",
                    user_id,
                )

        except Exception as e:
            logger.error(
                "user_id=<%s>, error=<%s> | failed to send slack dm",
                user_id,
                str(e),
                exc_info=True,
            )

    def _build_prep_greeting(self, meeting: Meeting) -> str:
        """Build the initial prep session greeting message.

        Args:
            meeting: Meeting to prepare for

        Returns:
            Formatted greeting message
        """
        meeting_time = meeting.start_time.strftime("%A, %B %d at %I:%M %p")

        return f"""👋 Let's prepare for your meeting!

**{meeting.title}**
📅 {meeting_time}

I'll ask you a few questions to help create:
• Customized agenda
• Context from your organization
• Question bank for discussion
• Note-taking template

Ready to start? Just type your response to each question."""


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
