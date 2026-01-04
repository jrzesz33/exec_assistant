"""Meeting prep trigger handler Lambda function.

This Lambda is invoked by EventBridge when a meeting requires preparation.
It responds to MeetingPrepRequired events from the calendar monitor and:
1. Fetches meeting and user details from DynamoDB
2. Updates meeting status to PREP_SCHEDULED
3. Sends multi-channel notification via NotificationService
4. Tracks notification delivery status
5. Handles errors with retry logic

EventBridge Event Format:
    {
        "source": "exec-assistant.calendar-monitor",
        "detail-type": "MeetingPrepRequired",
        "detail": {
            "meeting_id": "gcal-abc123",
            "user_id": "U12345",
            "meeting_type": "leadership_team",
            "start_time": "2024-01-15T14:00:00Z",
            "title": "Leadership Team Sync"
        }
    }

Environment Variables:
    MEETINGS_TABLE_NAME: DynamoDB meetings table name
    USERS_TABLE_NAME: DynamoDB users table name
    SLACK_BOT_TOKEN: Slack bot OAuth token
    TWILIO_ACCOUNT_SID: Twilio account SID (optional)
    TWILIO_AUTH_TOKEN: Twilio auth token (optional)
    TWILIO_FROM_NUMBER: Twilio sender phone (optional)
    SES_FROM_EMAIL: SES sender email (optional)
    AWS_REGION: AWS region for DynamoDB/SES
"""

import json
import os
from datetime import UTC, datetime
from typing import Any

import boto3
from botocore.exceptions import ClientError

from exec_assistant.shared.logging import get_logger
from exec_assistant.shared.models import Meeting, MeetingStatus, NotificationChannel, User
from exec_assistant.shared.notification_service import NotificationService

logger = get_logger(__name__)

# Initialize AWS clients
dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))

# Environment variables
MEETINGS_TABLE_NAME = os.environ.get("MEETINGS_TABLE_NAME", "exec-assistant-meetings")
USERS_TABLE_NAME = os.environ.get("USERS_TABLE_NAME", "exec-assistant-users")


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler for EventBridge MeetingPrepRequired events.

    Args:
        event: EventBridge event with meeting prep trigger
        context: Lambda context object

    Returns:
        Response dict with status and notification result

    Raises:
        ValueError: If event is invalid or missing required fields
        ClientError: If DynamoDB operations fail
    """
    logger.info("event=<%s> | prep trigger handler invoked", json.dumps(event))

    try:
        # Extract event details
        detail = event.get("detail", {})
        meeting_id = detail.get("meeting_id")
        user_id = detail.get("user_id")

        if not meeting_id or not user_id:
            logger.error(
                "meeting_id=<%s>, user_id=<%s> | missing required event fields",
                meeting_id,
                user_id,
            )
            raise ValueError("Event must contain meeting_id and user_id")

        logger.info(
            "meeting_id=<%s>, user_id=<%s> | processing prep trigger",
            meeting_id,
            user_id,
        )

        # Fetch meeting from DynamoDB
        meeting = fetch_meeting(meeting_id)
        if not meeting:
            logger.error(
                "meeting_id=<%s> | meeting not found in dynamodb",
                meeting_id,
            )
            raise ValueError(f"Meeting {meeting_id} not found")

        # Fetch user from DynamoDB
        user = fetch_user(user_id)
        if not user:
            logger.error(
                "user_id=<%s> | user not found in dynamodb",
                user_id,
            )
            raise ValueError(f"User {user_id} not found")

        # Check idempotency - prevent duplicate notifications
        if meeting.notification_sent_at is not None:
            logger.warning(
                "meeting_id=<%s>, notification_sent_at=<%s> | notification already sent skipping duplicate",
                meeting_id,
                meeting.notification_sent_at.isoformat(),
            )
            return {
                "statusCode": 200,
                "body": json.dumps(
                    {
                        "message": "Notification already sent",
                        "meeting_id": meeting_id,
                        "notification_sent_at": meeting.notification_sent_at.isoformat(),
                    }
                ),
            }

        # Validate meeting is in correct state
        if meeting.status not in (MeetingStatus.DISCOVERED, MeetingStatus.CLASSIFIED):
            logger.warning(
                "meeting_id=<%s>, status=<%s> | meeting not in valid state for prep trigger skipping",
                meeting_id,
                meeting.status.value,
            )
            return {
                "statusCode": 200,
                "body": json.dumps(
                    {
                        "message": "Meeting already processed or in invalid state",
                        "meeting_id": meeting_id,
                        "status": meeting.status.value,
                    }
                ),
            }

        # Update meeting status to PREP_SCHEDULED
        update_meeting_status(meeting, MeetingStatus.PREP_SCHEDULED)

        # Determine notification channels based on user preferences
        channels = get_notification_channels(user)

        # Send notification
        notification_service = NotificationService()
        result = notification_service.send_prep_notification(meeting, user, channels)

        # Update meeting with notification result
        if result.message_id:
            meeting.notification_id = result.message_id
            meeting.notification_sent_at = datetime.now(UTC)
            meeting.updated_at = datetime.now(UTC)
            save_meeting(meeting)

        logger.info(
            "meeting_id=<%s>, user_id=<%s>, notification_status=<%s>, channels=<%s> | prep notification sent",
            meeting_id,
            user_id,
            result.status.value,
            [ch.value for ch in result.delivered_channels],
        )

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "message": "Prep notification sent successfully",
                    "meeting_id": meeting_id,
                    "user_id": user_id,
                    "notification_result": result.to_dict(),
                }
            ),
        }

    except ValueError as e:
        logger.error(
            "error=<%s> | validation error",
            str(e),
            exc_info=True,
        )
        return {
            "statusCode": 400,
            "body": json.dumps(
                {
                    "error": "ValidationError",
                    "message": str(e),
                }
            ),
        }

    except Exception as e:
        logger.error(
            "error=<%s> | prep trigger handler failed",
            str(e),
            exc_info=True,
        )
        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "error": "InternalError",
                    "message": "Failed to process prep trigger",
                }
            ),
        }


def fetch_meeting(meeting_id: str) -> Meeting | None:
    """Fetch meeting from DynamoDB by meeting_id.

    Args:
        meeting_id: Meeting identifier

    Returns:
        Meeting object or None if not found

    Raises:
        ClientError: If DynamoDB operation fails
    """
    meetings_table = dynamodb.Table(MEETINGS_TABLE_NAME)

    try:
        logger.debug(
            "meeting_id=<%s>, table=<%s> | fetching meeting",
            meeting_id,
            MEETINGS_TABLE_NAME,
        )

        response = meetings_table.get_item(Key={"meeting_id": meeting_id})

        if "Item" not in response:
            logger.warning(
                "meeting_id=<%s> | meeting not found",
                meeting_id,
            )
            return None

        meeting = Meeting.from_dynamodb(response["Item"])

        logger.debug(
            "meeting_id=<%s>, status=<%s>, meeting_type=<%s> | meeting fetched",
            meeting_id,
            meeting.status.value,
            meeting.meeting_type.value,
        )

        return meeting

    except ClientError as e:
        logger.error(
            "meeting_id=<%s>, error_code=<%s>, error=<%s> | dynamodb get_item failed",
            meeting_id,
            e.response["Error"]["Code"],
            str(e),
            exc_info=True,
        )
        raise


def fetch_user(user_id: str) -> User | None:
    """Fetch user from DynamoDB by user_id.

    Args:
        user_id: User identifier (Slack user ID)

    Returns:
        User object or None if not found

    Raises:
        ClientError: If DynamoDB operation fails
    """
    users_table = dynamodb.Table(USERS_TABLE_NAME)

    try:
        logger.debug(
            "user_id=<%s>, table=<%s> | fetching user",
            user_id,
            USERS_TABLE_NAME,
        )

        response = users_table.get_item(Key={"user_id": user_id})

        if "Item" not in response:
            logger.warning(
                "user_id=<%s> | user not found",
                user_id,
            )
            return None

        user = User.from_dynamodb(response["Item"])

        logger.debug(
            "user_id=<%s>, email=<%s>, calendar_connected=<%s> | user fetched",
            user_id,
            user.email,
            user.calendar_connected,
        )

        return user

    except ClientError as e:
        logger.error(
            "user_id=<%s>, error_code=<%s>, error=<%s> | dynamodb get_item failed",
            user_id,
            e.response["Error"]["Code"],
            str(e),
            exc_info=True,
        )
        raise


def update_meeting_status(meeting: Meeting, new_status: MeetingStatus) -> None:
    """Update meeting status in DynamoDB.

    Args:
        meeting: Meeting object to update
        new_status: New status to set

    Raises:
        ClientError: If DynamoDB update fails
    """
    meetings_table = dynamodb.Table(MEETINGS_TABLE_NAME)

    try:
        old_status = meeting.status
        meeting.status = new_status
        meeting.updated_at = datetime.now(UTC)

        logger.debug(
            "meeting_id=<%s>, old_status=<%s>, new_status=<%s> | updating meeting status",
            meeting.meeting_id,
            old_status.value,
            new_status.value,
        )

        # Save updated meeting
        meetings_table.put_item(Item=meeting.to_dynamodb())

        logger.info(
            "meeting_id=<%s>, status=<%s> | meeting status updated",
            meeting.meeting_id,
            new_status.value,
        )

    except ClientError as e:
        logger.error(
            "meeting_id=<%s>, error_code=<%s>, error=<%s> | dynamodb put_item failed",
            meeting.meeting_id,
            e.response["Error"]["Code"],
            str(e),
            exc_info=True,
        )
        raise


def save_meeting(meeting: Meeting) -> None:
    """Save meeting to DynamoDB.

    Args:
        meeting: Meeting object to save

    Raises:
        ClientError: If DynamoDB put_item fails
    """
    meetings_table = dynamodb.Table(MEETINGS_TABLE_NAME)

    try:
        logger.debug(
            "meeting_id=<%s> | saving meeting",
            meeting.meeting_id,
        )

        meetings_table.put_item(Item=meeting.to_dynamodb())

        logger.debug(
            "meeting_id=<%s> | meeting saved",
            meeting.meeting_id,
        )

    except ClientError as e:
        logger.error(
            "meeting_id=<%s>, error_code=<%s>, error=<%s> | dynamodb put_item failed",
            meeting.meeting_id,
            e.response["Error"]["Code"],
            str(e),
            exc_info=True,
        )
        raise


def get_notification_channels(user: User) -> list[NotificationChannel]:
    """Determine notification channels for user based on preferences.

    Default priority: Slack → SMS → Email

    Args:
        user: User object with preferences

    Returns:
        Priority-ordered list of notification channels
    """
    channels: list[NotificationChannel] = []

    # Always try Slack first for DM-based interactions
    channels.append(NotificationChannel.SLACK)

    # Add SMS if user has phone number
    if user.phone_number:
        channels.append(NotificationChannel.SMS)

    # Always add email as final fallback
    channels.append(NotificationChannel.EMAIL)

    logger.debug(
        "user_id=<%s>, channels=<%s> | determined notification channels",
        user.user_id,
        [ch.value for ch in channels],
    )

    return channels
