"""Calendar monitoring Lambda function.

This Lambda is triggered by EventBridge every 2 hours to:
1. Find all users with calendar_connected=true
2. Fetch their upcoming calendar meetings (next 14 days)
3. Classify each meeting using MeetingClassifier
4. Sync meetings to DynamoDB (create/update)
5. Check if meetings need prep triggered
6. Emit EventBridge events for meetings requiring prep

Environment Variables:
    USERS_TABLE_NAME: DynamoDB users table name
    MEETINGS_TABLE_NAME: DynamoDB meetings table name
    GOOGLE_CALENDAR_CLIENT_ID: Google OAuth client ID
    GOOGLE_CALENDAR_CLIENT_SECRET: Google OAuth client secret
    GOOGLE_CALENDAR_REDIRECT_URI: OAuth redirect URI
    AWS_REGION: AWS region for DynamoDB and EventBridge
    EVENT_BUS_NAME: EventBridge event bus name (optional, defaults to "default")
    CALENDAR_LOOKAHEAD_DAYS: Days ahead to fetch meetings (default: "14")
"""

import json
import os
import uuid
from datetime import UTC, datetime
from typing import Any

import boto3
from botocore.exceptions import ClientError

from exec_assistant.shared.calendar import CalendarClient
from exec_assistant.shared.logging import get_logger
from exec_assistant.shared.meeting_classifier import MeetingClassifier
from exec_assistant.shared.models import Meeting, MeetingStatus, User

logger = get_logger(__name__)

# Initialize AWS clients
dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
events_client = boto3.client("events", region_name=os.environ.get("AWS_REGION", "us-east-1"))

# Environment variables
USERS_TABLE_NAME = os.environ.get("USERS_TABLE_NAME", "exec-assistant-users")
MEETINGS_TABLE_NAME = os.environ.get("MEETINGS_TABLE_NAME", "exec-assistant-meetings")
GOOGLE_CALENDAR_CLIENT_ID = os.environ.get("GOOGLE_CALENDAR_CLIENT_ID", "")
GOOGLE_CALENDAR_CLIENT_SECRET = os.environ.get("GOOGLE_CALENDAR_CLIENT_SECRET", "")
GOOGLE_CALENDAR_REDIRECT_URI = os.environ.get("GOOGLE_CALENDAR_REDIRECT_URI", "")
EVENT_BUS_NAME = os.environ.get("EVENT_BUS_NAME", "default")
CALENDAR_LOOKAHEAD_DAYS = int(os.environ.get("CALENDAR_LOOKAHEAD_DAYS", "14"))


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Main Lambda handler for EventBridge scheduled trigger.

    Args:
        event: EventBridge event data
        context: Lambda context object

    Returns:
        Response dict with status and summary statistics

    Raises:
        ClientError: If DynamoDB operations fail
    """
    logger.info("event=<%s> | calendar monitor lambda invoked", json.dumps(event))

    try:
        # Initialize statistics
        users_processed = 0
        meetings_synced = 0
        preps_triggered = 0
        errors = 0

        # Get all connected users
        connected_users = get_connected_users()
        logger.info("users_found=<%d> | fetched connected users", len(connected_users))

        # Process each user's calendar
        for user in connected_users:
            try:
                result = process_user_calendar(user)
                users_processed += 1
                meetings_synced += result["meetings_synced"]
                preps_triggered += result["preps_triggered"]

                logger.info(
                    "user_id=<%s>, meetings_synced=<%d>, preps_triggered=<%d> | processed user calendar",
                    user.user_id,
                    result["meetings_synced"],
                    result["preps_triggered"],
                )

            except Exception as e:
                # Log error but continue to next user (don't fail entire batch)
                errors += 1
                logger.error(
                    "user_id=<%s>, error=<%s> | failed to process user calendar",
                    user.user_id,
                    str(e),
                    exc_info=True,
                )

        # Return summary
        logger.info(
            "users_processed=<%d>, meetings_synced=<%d>, preps_triggered=<%d>, errors=<%d> | calendar monitor completed",
            users_processed,
            meetings_synced,
            preps_triggered,
            errors,
        )

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "users_processed": users_processed,
                    "meetings_synced": meetings_synced,
                    "preps_triggered": preps_triggered,
                    "errors": errors,
                }
            ),
        }

    except Exception as e:
        logger.error(
            "error=<%s> | calendar monitor failed",
            str(e),
            exc_info=True,
        )
        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "error": str(e),
                    "message": "calendar monitor failed",
                }
            ),
        }


def get_connected_users() -> list[User]:
    """Query DynamoDB users table for users with calendar_connected=true.

    Returns:
        List of User objects with calendar connected

    Raises:
        ClientError: If DynamoDB scan fails
    """
    users_table = dynamodb.Table(USERS_TABLE_NAME)

    try:
        logger.debug("table=<%s> | scanning for connected users", USERS_TABLE_NAME)

        # Scan with filter for calendar_connected=true
        response = users_table.scan(
            FilterExpression="calendar_connected = :connected",
            ExpressionAttributeValues={":connected": True},
        )

        items = response.get("Items", [])

        # Handle pagination
        while "LastEvaluatedKey" in response:
            logger.debug(
                "table=<%s>, items_so_far=<%d> | continuing scan",
                USERS_TABLE_NAME,
                len(items),
            )
            response = users_table.scan(
                FilterExpression="calendar_connected = :connected",
                ExpressionAttributeValues={":connected": True},
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            items.extend(response.get("Items", []))

        logger.info(
            "table=<%s>, users_found=<%d> | scan completed",
            USERS_TABLE_NAME,
            len(items),
        )

        # Convert to User objects
        users = []
        for item in items:
            try:
                user = User.from_dynamodb(item)
                users.append(user)
            except Exception as e:
                logger.warning(
                    "user_id=<%s>, error=<%s> | failed to parse user from dynamodb",
                    item.get("user_id", "unknown"),
                    str(e),
                )

        return users

    except ClientError as e:
        logger.error(
            "table=<%s>, error_code=<%s>, error=<%s> | dynamodb scan failed",
            USERS_TABLE_NAME,
            e.response["Error"]["Code"],
            str(e),
            exc_info=True,
        )
        raise


def process_user_calendar(user: User) -> dict[str, Any]:
    """Process calendar for a single user.

    This function:
    1. Creates CalendarClient for the user
    2. Fetches upcoming meetings (configurable days ahead)
    3. For each meeting:
       - Classifies using MeetingClassifier
       - Syncs to DynamoDB (create or update)
       - Checks if prep should be triggered
       - If yes, emits EventBridge event

    Args:
        user: User object with calendar connected

    Returns:
        Summary dict with meetings_synced and preps_triggered counts

    Raises:
        ValueError: If user validation fails
        CalendarError: If calendar API fails (propagated from CalendarClient)
    """
    # Validate user
    if not user.user_id:
        raise ValueError("user_id is required")

    if not user.calendar_connected:
        logger.warning(
            "user_id=<%s> | skipping user without calendar connected",
            user.user_id,
        )
        return {"meetings_synced": 0, "preps_triggered": 0}

    logger.info(
        "user_id=<%s>, lookahead_days=<%d> | processing user calendar",
        user.user_id,
        CALENDAR_LOOKAHEAD_DAYS,
    )

    # Create calendar client
    calendar_client = CalendarClient(
        user_id=user.user_id,
        client_id=GOOGLE_CALENDAR_CLIENT_ID,
        client_secret=GOOGLE_CALENDAR_CLIENT_SECRET,
        redirect_uri=GOOGLE_CALENDAR_REDIRECT_URI,
    )

    # Fetch upcoming meetings
    try:
        meetings = calendar_client.fetch_upcoming_meetings(days_ahead=CALENDAR_LOOKAHEAD_DAYS)
        logger.info(
            "user_id=<%s>, meetings_found=<%d> | fetched calendar meetings",
            user.user_id,
            len(meetings),
        )
    except Exception as e:
        logger.error(
            "user_id=<%s>, error=<%s> | failed to fetch calendar meetings",
            user.user_id,
            str(e),
            exc_info=True,
        )
        raise

    # Initialize classifier
    classifier = MeetingClassifier()

    # Process each meeting
    meetings_synced = 0
    preps_triggered = 0
    current_time = datetime.now(UTC)

    for meeting in meetings:
        try:
            # Classify meeting
            meeting_type = classifier.classify_meeting(meeting)
            meeting.meeting_type = meeting_type

            # Update status based on classification
            if meeting.status == MeetingStatus.DISCOVERED:
                meeting.status = MeetingStatus.CLASSIFIED

            # Calculate prep trigger time
            prep_hours = classifier.get_prep_hours(meeting_type)
            meeting.prep_hours_before = prep_hours

            # Update last synced timestamp
            meeting.last_synced_at = current_time

            logger.debug(
                "user_id=<%s>, meeting_id=<%s>, meeting_type=<%s>, prep_hours=<%d> | classified meeting",
                user.user_id,
                meeting.meeting_id,
                meeting_type.value,
                prep_hours,
            )

            # Sync to DynamoDB
            sync_meeting_to_dynamodb(meeting)
            meetings_synced += 1

            # Check if prep should be triggered
            if classifier.should_trigger_prep(meeting, current_time):
                # Only trigger if not already scheduled or in progress
                if meeting.status in (MeetingStatus.DISCOVERED, MeetingStatus.CLASSIFIED):
                    emit_prep_trigger_event(meeting)
                    preps_triggered += 1

                    logger.info(
                        "user_id=<%s>, meeting_id=<%s>, meeting_type=<%s> | triggered prep notification",
                        user.user_id,
                        meeting.meeting_id,
                        meeting_type.value,
                    )
                else:
                    logger.debug(
                        "user_id=<%s>, meeting_id=<%s>, status=<%s> | skipping prep trigger for already processed meeting",
                        user.user_id,
                        meeting.meeting_id,
                        meeting.status.value,
                    )
            else:
                logger.debug(
                    "user_id=<%s>, meeting_id=<%s> | meeting not in prep window",
                    user.user_id,
                    meeting.meeting_id,
                )

        except Exception as e:
            # Log error but continue to next meeting
            logger.error(
                "user_id=<%s>, meeting_id=<%s>, error=<%s> | failed to process meeting",
                user.user_id,
                meeting.meeting_id,
                str(e),
                exc_info=True,
            )

    return {
        "meetings_synced": meetings_synced,
        "preps_triggered": preps_triggered,
    }


def sync_meeting_to_dynamodb(meeting: Meeting) -> None:
    """Save or update meeting in DynamoDB meetings table.

    This function handles deduplication based on external_id (calendar event ID).
    - If meeting exists with same external_id: updates existing record, preserves meeting_id
    - If new: assigns new meeting_id, creates record

    Args:
        meeting: Meeting object to sync

    Raises:
        ClientError: If DynamoDB operations fail
    """
    meetings_table = dynamodb.Table(MEETINGS_TABLE_NAME)

    try:
        # Check if meeting already exists by external_id
        existing_meeting = None
        if meeting.external_id:
            logger.debug(
                "meeting_id=<%s>, external_id=<%s> | checking for existing meeting",
                meeting.meeting_id,
                meeting.external_id,
            )

            # Query by external_id (requires GSI if using external_id as search key)
            # For now, we'll use the meeting_id from calendar client which includes external_id
            try:
                response = meetings_table.get_item(Key={"meeting_id": meeting.meeting_id})
                if "Item" in response:
                    existing_meeting = Meeting.from_dynamodb(response["Item"])
                    logger.debug(
                        "meeting_id=<%s>, external_id=<%s> | found existing meeting",
                        meeting.meeting_id,
                        meeting.external_id,
                    )
            except ClientError:
                # Meeting doesn't exist, will create new one
                pass

        # Update timestamps
        meeting.updated_at = datetime.now(UTC)
        if not existing_meeting:
            # New meeting - ensure meeting_id is set
            if not meeting.meeting_id or not meeting.meeting_id.startswith("gcal-"):
                meeting.meeting_id = f"gcal-{uuid.uuid4().hex[:16]}"
            meeting.created_at = datetime.now(UTC)
            logger.debug(
                "meeting_id=<%s> | creating new meeting",
                meeting.meeting_id,
            )
        else:
            # Preserve original created_at
            meeting.created_at = existing_meeting.created_at
            logger.debug(
                "meeting_id=<%s> | updating existing meeting",
                meeting.meeting_id,
            )

        # Convert to DynamoDB format and save
        item = meeting.to_dynamodb()
        meetings_table.put_item(Item=item)

        logger.info(
            "meeting_id=<%s>, user_id=<%s>, meeting_type=<%s> | synced meeting to dynamodb",
            meeting.meeting_id,
            meeting.user_id,
            meeting.meeting_type.value,
        )

    except ClientError as e:
        logger.error(
            "meeting_id=<%s>, error_code=<%s>, error=<%s> | failed to sync meeting to dynamodb",
            meeting.meeting_id,
            e.response["Error"]["Code"],
            str(e),
            exc_info=True,
        )
        raise


def emit_prep_trigger_event(meeting: Meeting) -> None:
    """Emit EventBridge event to trigger meeting prep workflow.

    The event structure follows the exec-assistant event schema for
    meeting prep triggers. This event will be consumed by Step Functions
    or Lambda to initiate the prep workflow.

    Args:
        meeting: Meeting object requiring prep

    Raises:
        ClientError: If EventBridge put_events fails
    """
    event_detail = {
        "meeting_id": meeting.meeting_id,
        "user_id": meeting.user_id,
        "meeting_type": meeting.meeting_type.value,
        "start_time": meeting.start_time.isoformat(),
        "title": meeting.title,
    }

    event_entry = {
        "Source": "exec-assistant.calendar-monitor",
        "DetailType": "MeetingPrepRequired",
        "Detail": json.dumps(event_detail),
        "EventBusName": EVENT_BUS_NAME,
    }

    try:
        logger.debug(
            "meeting_id=<%s>, event_bus=<%s> | emitting prep trigger event",
            meeting.meeting_id,
            EVENT_BUS_NAME,
        )

        response = events_client.put_events(Entries=[event_entry])

        # Check for failures
        if response.get("FailedEntryCount", 0) > 0:
            failed_entries = response.get("Entries", [])
            logger.error(
                "meeting_id=<%s>, failed_entries=<%s> | eventbridge put_events failed",
                meeting.meeting_id,
                json.dumps(failed_entries),
            )
            raise ClientError(
                {
                    "Error": {
                        "Code": "EventBridgeFailed",
                        "Message": f"Failed to emit event: {failed_entries}",
                    }
                },
                "put_events",
            )

        logger.info(
            "meeting_id=<%s>, user_id=<%s>, event_bus=<%s> | emitted prep trigger event",
            meeting.meeting_id,
            meeting.user_id,
            EVENT_BUS_NAME,
        )

    except ClientError as e:
        logger.error(
            "meeting_id=<%s>, error_code=<%s>, error=<%s> | failed to emit prep trigger event",
            meeting.meeting_id,
            e.response["Error"]["Code"],
            str(e),
            exc_info=True,
        )
        raise
