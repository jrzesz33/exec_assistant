"""Multi-channel notification service for meeting prep reminders.

This module provides notification routing with fallback support across
Slack, SMS (Twilio), and Email (SES) channels. Notifications are attempted
in priority order with automatic fallback on failure.

Environment Variables:
    SLACK_BOT_TOKEN: Slack bot OAuth token
    TWILIO_ACCOUNT_SID: Twilio account SID (optional)
    TWILIO_AUTH_TOKEN: Twilio auth token (optional)
    TWILIO_FROM_NUMBER: Twilio sender phone number (optional)
    AWS_REGION: AWS region for SES (optional)
    SES_FROM_EMAIL: SES sender email address (optional)
"""

import json
import os
from enum import Enum
from typing import Any

import boto3
import requests
from botocore.exceptions import ClientError

from exec_assistant.shared.logging import get_logger
from exec_assistant.shared.models import Meeting, NotificationChannel, User

logger = get_logger(__name__)


class NotificationStatus(str, Enum):
    """Notification delivery status."""

    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"  # Some channels succeeded, others failed


class NotificationResult:
    """Result of notification attempt."""

    def __init__(
        self,
        status: NotificationStatus,
        delivered_channels: list[NotificationChannel],
        failed_channels: dict[NotificationChannel, str],
        message_id: str | None = None,
    ) -> None:
        """Initialize notification result.

        Args:
            status: Overall delivery status
            delivered_channels: Channels that successfully delivered
            failed_channels: Map of failed channels to error messages
            message_id: Message ID from primary channel (if successful)
        """
        self.status = status
        self.delivered_channels = delivered_channels
        self.failed_channels = failed_channels
        self.message_id = message_id

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dictionary with result details
        """
        return {
            "status": self.status.value,
            "delivered_channels": [ch.value for ch in self.delivered_channels],
            "failed_channels": {ch.value: error for ch, error in self.failed_channels.items()},
            "message_id": self.message_id,
        }


class NotificationService:
    """Multi-channel notification service with fallback support."""

    def __init__(
        self,
        slack_bot_token: str | None = None,
        twilio_account_sid: str | None = None,
        twilio_auth_token: str | None = None,
        twilio_from_number: str | None = None,
        ses_from_email: str | None = None,
        aws_region: str | None = None,
    ) -> None:
        """Initialize notification service.

        Args:
            slack_bot_token: Slack bot OAuth token (defaults to env var)
            twilio_account_sid: Twilio account SID (defaults to env var)
            twilio_auth_token: Twilio auth token (defaults to env var)
            twilio_from_number: Twilio sender phone (defaults to env var)
            ses_from_email: SES sender email (defaults to env var)
            aws_region: AWS region for SES (defaults to env var)
        """
        # Slack configuration
        self.slack_bot_token = slack_bot_token or os.environ.get("SLACK_BOT_TOKEN", "")
        self.slack_enabled = bool(self.slack_bot_token)

        # Twilio configuration
        self.twilio_account_sid = twilio_account_sid or os.environ.get("TWILIO_ACCOUNT_SID", "")
        self.twilio_auth_token = twilio_auth_token or os.environ.get("TWILIO_AUTH_TOKEN", "")
        self.twilio_from_number = twilio_from_number or os.environ.get("TWILIO_FROM_NUMBER", "")
        self.twilio_enabled = bool(
            self.twilio_account_sid and self.twilio_auth_token and self.twilio_from_number
        )

        # SES configuration
        self.ses_from_email = ses_from_email or os.environ.get("SES_FROM_EMAIL", "")
        self.aws_region = aws_region or os.environ.get("AWS_REGION", "us-east-1")
        self.ses_enabled = bool(self.ses_from_email)

        # Initialize AWS SES client if enabled
        if self.ses_enabled:
            self.ses_client = boto3.client("ses", region_name=self.aws_region)
        else:
            self.ses_client = None

        logger.info(
            "slack_enabled=<%s>, twilio_enabled=<%s>, ses_enabled=<%s> | notification service initialized",
            self.slack_enabled,
            self.twilio_enabled,
            self.ses_enabled,
        )

    def send_prep_notification(
        self,
        meeting: Meeting,
        user: User,
        channels: list[NotificationChannel] | None = None,
    ) -> NotificationResult:
        """Send meeting prep notification with channel fallback.

        Attempts to send notification through channels in priority order,
        falling back to next channel on failure.

        Args:
            meeting: Meeting requiring prep
            user: User to notify
            channels: Priority-ordered list of channels (defaults to Slack -> SMS -> Email)

        Returns:
            NotificationResult with delivery status

        Raises:
            ValueError: If no channels are available or enabled
        """
        # Default channel priority
        if channels is None:
            channels = [
                NotificationChannel.SLACK,
                NotificationChannel.SMS,
                NotificationChannel.EMAIL,
            ]

        # Filter to only enabled channels
        available_channels = [ch for ch in channels if self._is_channel_enabled(ch)]

        if not available_channels:
            logger.error(
                "user_id=<%s>, meeting_id=<%s> | no notification channels available",
                user.user_id,
                meeting.meeting_id,
            )
            raise ValueError("No notification channels available or enabled")

        logger.info(
            "user_id=<%s>, meeting_id=<%s>, channels=<%s> | sending prep notification",
            user.user_id,
            meeting.meeting_id,
            [ch.value for ch in available_channels],
        )

        delivered_channels: list[NotificationChannel] = []
        failed_channels: dict[NotificationChannel, str] = {}
        message_id: str | None = None

        # Try each channel in order
        for channel in available_channels:
            try:
                if channel == NotificationChannel.SLACK:
                    msg_id = self._send_slack_notification(meeting, user)
                    delivered_channels.append(channel)
                    if message_id is None:
                        message_id = msg_id
                    logger.info(
                        "user_id=<%s>, meeting_id=<%s>, channel=<slack> | notification delivered",
                        user.user_id,
                        meeting.meeting_id,
                    )
                    break  # Success - don't try fallback channels

                elif channel == NotificationChannel.SMS:
                    msg_id = self._send_sms_notification(meeting, user)
                    delivered_channels.append(channel)
                    if message_id is None:
                        message_id = msg_id
                    logger.info(
                        "user_id=<%s>, meeting_id=<%s>, channel=<sms> | notification delivered",
                        user.user_id,
                        meeting.meeting_id,
                    )
                    break  # Success

                elif channel == NotificationChannel.EMAIL:
                    msg_id = self._send_email_notification(meeting, user)
                    delivered_channels.append(channel)
                    if message_id is None:
                        message_id = msg_id
                    logger.info(
                        "user_id=<%s>, meeting_id=<%s>, channel=<email> | notification delivered",
                        user.user_id,
                        meeting.meeting_id,
                    )
                    break  # Success

            except Exception as e:
                error_msg = str(e)
                failed_channels[channel] = error_msg
                logger.warning(
                    "user_id=<%s>, meeting_id=<%s>, channel=<%s>, error=<%s> | notification failed trying next channel",
                    user.user_id,
                    meeting.meeting_id,
                    channel.value,
                    error_msg,
                )
                # Continue to next channel

        # Determine overall status
        status = (
            NotificationStatus.SUCCESS
            if delivered_channels
            else NotificationStatus.FAILED
        )

        result = NotificationResult(
            status=status,
            delivered_channels=delivered_channels,
            failed_channels=failed_channels,
            message_id=message_id,
        )

        logger.info(
            "user_id=<%s>, meeting_id=<%s>, status=<%s>, delivered=<%s> | prep notification completed",
            user.user_id,
            meeting.meeting_id,
            status.value,
            [ch.value for ch in delivered_channels],
        )

        return result

    def _is_channel_enabled(self, channel: NotificationChannel) -> bool:
        """Check if notification channel is enabled.

        Args:
            channel: Channel to check

        Returns:
            True if channel is enabled and configured
        """
        if channel == NotificationChannel.SLACK:
            return self.slack_enabled
        elif channel == NotificationChannel.SMS:
            return self.twilio_enabled
        elif channel == NotificationChannel.EMAIL:
            return self.ses_enabled
        return False

    def _send_slack_notification(self, meeting: Meeting, user: User) -> str:
        """Send Slack notification with interactive buttons.

        Args:
            meeting: Meeting to notify about
            user: User to send to

        Returns:
            Slack message timestamp (message ID)

        Raises:
            Exception: If Slack API call fails
        """
        logger.debug(
            "user_id=<%s>, meeting_id=<%s> | sending slack notification",
            user.user_id,
            meeting.meeting_id,
        )

        # Format meeting time
        meeting_time = meeting.start_time.strftime("%A, %B %d at %I:%M %p")
        duration_mins = int((meeting.end_time - meeting.start_time).total_seconds() / 60)

        # Build message blocks with interactive buttons
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "🗓️ Meeting Prep Reminder"},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"You have a *{meeting.meeting_type.value.replace('_', ' ').title()}* coming up:\n\n"
                    f"*{meeting.title}*\n"
                    f"📅 {meeting_time}\n"
                    f"⏱️ {duration_mins} minutes\n"
                    f"👥 {len(meeting.attendees)} attendee(s)",
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "Time to prepare! I can help you create:\n"
                    "✅ Customized agenda\n"
                    "✅ Context from budget, incidents, and strategic priorities\n"
                    "✅ Question bank for discussion\n"
                    "✅ Note-taking template",
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Start Prep Session"},
                        "style": "primary",
                        "action_id": "start_prep",
                        "value": json.dumps(
                            {
                                "meeting_id": meeting.meeting_id,
                                "user_id": user.user_id,
                            }
                        ),
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Remind Me in 2 Hours"},
                        "action_id": "remind_later",
                        "value": json.dumps(
                            {
                                "meeting_id": meeting.meeting_id,
                                "user_id": user.user_id,
                            }
                        ),
                    },
                ],
            },
        ]

        # Get user's Slack user ID (from User model or lookup)
        # For now, assume user.user_id is the Slack user ID
        slack_user_id = user.user_id

        # Send message via Slack API
        response = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={
                "Authorization": f"Bearer {self.slack_bot_token}",
                "Content-Type": "application/json",
            },
            json={
                "channel": slack_user_id,
                "blocks": blocks,
                "text": f"Meeting prep reminder for {meeting.title}",  # Fallback text
            },
            timeout=10,
        )

        response_data = response.json()

        if not response_data.get("ok"):
            error = response_data.get("error", "unknown_error")
            logger.error(
                "user_id=<%s>, meeting_id=<%s>, error=<%s> | slack api error",
                user.user_id,
                meeting.meeting_id,
                error,
            )
            raise Exception(f"Slack API error: {error}")

        message_ts = response_data.get("ts", "")
        logger.debug(
            "user_id=<%s>, meeting_id=<%s>, message_ts=<%s> | slack notification sent",
            user.user_id,
            meeting.meeting_id,
            message_ts,
        )

        return message_ts

    def _send_sms_notification(self, meeting: Meeting, user: User) -> str:
        """Send SMS notification via Twilio.

        Args:
            meeting: Meeting to notify about
            user: User to send to

        Returns:
            Twilio message SID

        Raises:
            Exception: If Twilio API call fails or user has no phone number
        """
        if not user.phone_number:
            raise ValueError(f"User {user.user_id} has no phone number")

        logger.debug(
            "user_id=<%s>, meeting_id=<%s>, phone=<%s> | sending sms notification",
            user.user_id,
            meeting.meeting_id,
            user.phone_number,
        )

        # Format message
        meeting_time = meeting.start_time.strftime("%b %d at %I:%M %p")
        message_body = (
            f"Meeting prep reminder: {meeting.title}\n"
            f"When: {meeting_time}\n"
            f"Start prep: [Web link would go here]\n"
            f"Reply SKIP to dismiss"
        )

        # Send via Twilio API
        response = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{self.twilio_account_sid}/Messages.json",
            auth=(self.twilio_account_sid, self.twilio_auth_token),
            data={
                "From": self.twilio_from_number,
                "To": user.phone_number,
                "Body": message_body,
            },
            timeout=10,
        )

        if response.status_code not in (200, 201):
            error_msg = response.text
            logger.error(
                "user_id=<%s>, meeting_id=<%s>, error=<%s> | twilio api error",
                user.user_id,
                meeting.meeting_id,
                error_msg,
            )
            raise Exception(f"Twilio API error: {error_msg}")

        response_data = response.json()
        message_sid = response_data.get("sid", "")

        logger.debug(
            "user_id=<%s>, meeting_id=<%s>, message_sid=<%s> | sms notification sent",
            user.user_id,
            meeting.meeting_id,
            message_sid,
        )

        return message_sid

    def _send_email_notification(self, meeting: Meeting, user: User) -> str:
        """Send email notification via AWS SES.

        Args:
            meeting: Meeting to notify about
            user: User to send to

        Returns:
            SES message ID

        Raises:
            Exception: If SES API call fails
        """
        logger.debug(
            "user_id=<%s>, meeting_id=<%s>, email=<%s> | sending email notification",
            user.user_id,
            meeting.meeting_id,
            user.email,
        )

        # Format email
        meeting_time = meeting.start_time.strftime("%A, %B %d at %I:%M %p")
        duration_mins = int((meeting.end_time - meeting.start_time).total_seconds() / 60)

        subject = f"Meeting Prep: {meeting.title}"

        html_body = f"""
        <html>
        <head></head>
        <body>
            <h2>🗓️ Meeting Prep Reminder</h2>
            <p>You have a <strong>{meeting.meeting_type.value.replace("_", " ").title()}</strong> coming up:</p>

            <h3>{meeting.title}</h3>
            <ul>
                <li>📅 {meeting_time}</li>
                <li>⏱️ {duration_mins} minutes</li>
                <li>👥 {len(meeting.attendees)} attendee(s)</li>
            </ul>

            <p>Time to prepare! I can help you create:</p>
            <ul>
                <li>✅ Customized agenda</li>
                <li>✅ Context from budget, incidents, and strategic priorities</li>
                <li>✅ Question bank for discussion</li>
                <li>✅ Note-taking template</li>
            </ul>

            <p><a href="[Web UI link would go here]">Start Prep Session</a></p>

            <p><em>This is an automated message from your Executive Assistant.</em></p>
        </body>
        </html>
        """

        text_body = f"""
Meeting Prep Reminder

You have a {meeting.meeting_type.value.replace("_", " ").title()} coming up:

{meeting.title}
- When: {meeting_time}
- Duration: {duration_mins} minutes
- Attendees: {len(meeting.attendees)}

Time to prepare! I can help you create an agenda, gather context, and prepare materials.

Start prep: [Web UI link would go here]
        """

        # Send via SES
        try:
            response = self.ses_client.send_email(
                Source=self.ses_from_email,
                Destination={"ToAddresses": [user.email]},
                Message={
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {
                        "Html": {"Data": html_body, "Charset": "UTF-8"},
                        "Text": {"Data": text_body, "Charset": "UTF-8"},
                    },
                },
            )

            message_id = response["MessageId"]

            logger.debug(
                "user_id=<%s>, meeting_id=<%s>, message_id=<%s> | email notification sent",
                user.user_id,
                meeting.meeting_id,
                message_id,
            )

            return message_id

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_msg = e.response["Error"]["Message"]
            logger.error(
                "user_id=<%s>, meeting_id=<%s>, error_code=<%s>, error=<%s> | ses api error",
                user.user_id,
                meeting.meeting_id,
                error_code,
                error_msg,
            )
            raise Exception(f"SES API error: {error_code} - {error_msg}") from e
