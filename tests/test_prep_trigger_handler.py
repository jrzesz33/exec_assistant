"""Unit tests for EventBridge prep trigger handler Lambda.

This module tests the meeting prep notification trigger handler that responds
to MeetingPrepRequired events from the calendar monitor.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest
from botocore.exceptions import ClientError

from exec_assistant.shared.models import (
    Meeting,
    MeetingStatus,
    MeetingType,
    NotificationChannel,
    User,
)
from exec_assistant.shared.notification_service import NotificationResult, NotificationStatus
from exec_assistant.workflows.prep_trigger_handler import (
    fetch_meeting,
    fetch_user,
    get_notification_channels,
    lambda_handler,
    save_meeting,
    update_meeting_status,
)


class TestLambdaHandler:
    """Tests for lambda_handler function."""

    @pytest.fixture
    def valid_event(self) -> dict[str, Any]:
        """Create a valid EventBridge event."""
        return {
            "version": "0",
            "id": "event-123",
            "detail-type": "MeetingPrepRequired",
            "source": "exec-assistant.calendar-monitor",
            "account": "123456789012",
            "time": "2026-01-04T10:00:00Z",
            "region": "us-east-1",
            "resources": [],
            "detail": {
                "meeting_id": "gcal-abc123",
                "user_id": "U12345",
                "meeting_type": "leadership_team",
                "start_time": "2026-01-05T14:00:00Z",
                "title": "Leadership Team Sync",
            },
        }

    @pytest.fixture
    def sample_meeting(self) -> Meeting:
        """Create a sample meeting for testing."""
        start_time = datetime(2026, 1, 5, 14, 0, tzinfo=UTC)
        end_time = start_time + timedelta(hours=1)

        return Meeting(
            meeting_id="gcal-abc123",
            user_id="U12345",
            title="Leadership Team Sync",
            start_time=start_time,
            end_time=end_time,
            meeting_type=MeetingType.LEADERSHIP_TEAM,
            status=MeetingStatus.CLASSIFIED,
            attendees=["user1@example.com", "user2@example.com"],
        )

    @pytest.fixture
    def sample_user(self) -> User:
        """Create a sample user for testing."""
        return User(
            user_id="U12345",
            google_id="google-123",
            email="user@example.com",
            name="Test User",
            phone_number="+12345678901",
        )

    @patch("exec_assistant.workflows.prep_trigger_handler.NotificationService")
    @patch("exec_assistant.workflows.prep_trigger_handler.save_meeting")
    @patch("exec_assistant.workflows.prep_trigger_handler.update_meeting_status")
    @patch("exec_assistant.workflows.prep_trigger_handler.fetch_user")
    @patch("exec_assistant.workflows.prep_trigger_handler.fetch_meeting")
    def test_successful_notification(
        self,
        mock_fetch_meeting: Mock,
        mock_fetch_user: Mock,
        mock_update_status: Mock,
        mock_save_meeting: Mock,
        mock_notification_service: Mock,
        valid_event: dict[str, Any],
        sample_meeting: Meeting,
        sample_user: User,
    ) -> None:
        """Test successful prep notification flow."""
        # Setup mocks
        mock_fetch_meeting.return_value = sample_meeting
        mock_fetch_user.return_value = sample_user

        mock_service_instance = MagicMock()
        mock_notification_service.return_value = mock_service_instance

        notification_result = NotificationResult(
            status=NotificationStatus.SUCCESS,
            delivered_channels=[NotificationChannel.SLACK],
            failed_channels={},
            message_id="ts_123456.789",
        )
        mock_service_instance.send_prep_notification.return_value = notification_result

        # Execute handler
        response = lambda_handler(valid_event, None)

        # Verify response
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["message"] == "Prep notification sent successfully"
        assert body["meeting_id"] == "gcal-abc123"
        assert body["user_id"] == "U12345"
        assert body["notification_result"]["status"] == "success"

        # Verify calls
        mock_fetch_meeting.assert_called_once_with("gcal-abc123")
        mock_fetch_user.assert_called_once_with("U12345")
        mock_update_status.assert_called_once_with(sample_meeting, MeetingStatus.PREP_SCHEDULED)
        mock_service_instance.send_prep_notification.assert_called_once()
        mock_save_meeting.assert_called_once()

    def test_missing_meeting_id(self) -> None:
        """Test handler with missing meeting_id in event."""
        event = {
            "detail": {
                "user_id": "U12345",
                # missing meeting_id
            }
        }

        response = lambda_handler(event, None)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["error"] == "ValidationError"
        assert "meeting_id" in body["message"]

    def test_missing_user_id(self) -> None:
        """Test handler with missing user_id in event."""
        event = {
            "detail": {
                "meeting_id": "gcal-abc123",
                # missing user_id
            }
        }

        response = lambda_handler(event, None)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["error"] == "ValidationError"
        assert "user_id" in body["message"]

    def test_empty_detail_field(self) -> None:
        """Test handler with empty detail field."""
        event = {"detail": {}}

        response = lambda_handler(event, None)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["error"] == "ValidationError"

    @patch("exec_assistant.workflows.prep_trigger_handler.fetch_meeting")
    def test_meeting_not_found(
        self,
        mock_fetch_meeting: Mock,
        valid_event: dict[str, Any],
    ) -> None:
        """Test handler when meeting is not found in DynamoDB."""
        mock_fetch_meeting.return_value = None

        response = lambda_handler(valid_event, None)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["error"] == "ValidationError"
        assert "Meeting" in body["message"]
        assert "not found" in body["message"]

    @patch("exec_assistant.workflows.prep_trigger_handler.fetch_user")
    @patch("exec_assistant.workflows.prep_trigger_handler.fetch_meeting")
    def test_user_not_found(
        self,
        mock_fetch_meeting: Mock,
        mock_fetch_user: Mock,
        valid_event: dict[str, Any],
        sample_meeting: Meeting,
    ) -> None:
        """Test handler when user is not found in DynamoDB."""
        mock_fetch_meeting.return_value = sample_meeting
        mock_fetch_user.return_value = None

        response = lambda_handler(valid_event, None)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["error"] == "ValidationError"
        assert "User" in body["message"]
        assert "not found" in body["message"]

    @patch("exec_assistant.workflows.prep_trigger_handler.fetch_user")
    @patch("exec_assistant.workflows.prep_trigger_handler.fetch_meeting")
    def test_meeting_invalid_status_prep_in_progress(
        self,
        mock_fetch_meeting: Mock,
        mock_fetch_user: Mock,
        valid_event: dict[str, Any],
        sample_user: User,
    ) -> None:
        """Test handler when meeting is already in PREP_IN_PROGRESS status."""
        # Meeting already being prepped
        meeting = Meeting(
            meeting_id="gcal-abc123",
            user_id="U12345",
            title="Test Meeting",
            start_time=datetime.now(UTC) + timedelta(days=1),
            end_time=datetime.now(UTC) + timedelta(days=1, hours=1),
            status=MeetingStatus.PREP_IN_PROGRESS,
        )
        mock_fetch_meeting.return_value = meeting
        mock_fetch_user.return_value = sample_user

        response = lambda_handler(valid_event, None)

        # Should return 200 but skip processing
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert "already processed" in body["message"]
        assert body["status"] == MeetingStatus.PREP_IN_PROGRESS.value

    @patch("exec_assistant.workflows.prep_trigger_handler.fetch_user")
    @patch("exec_assistant.workflows.prep_trigger_handler.fetch_meeting")
    def test_meeting_invalid_status_completed(
        self,
        mock_fetch_meeting: Mock,
        mock_fetch_user: Mock,
        valid_event: dict[str, Any],
        sample_user: User,
    ) -> None:
        """Test handler when meeting is already COMPLETED."""
        # Meeting already completed
        meeting = Meeting(
            meeting_id="gcal-abc123",
            user_id="U12345",
            title="Test Meeting",
            start_time=datetime.now(UTC) - timedelta(days=1),
            end_time=datetime.now(UTC) - timedelta(days=1, hours=1),
            status=MeetingStatus.COMPLETED,
        )
        mock_fetch_meeting.return_value = meeting
        mock_fetch_user.return_value = sample_user

        response = lambda_handler(valid_event, None)

        # Should return 200 but skip processing
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert "already processed" in body["message"] or "invalid state" in body["message"]

    @patch("exec_assistant.workflows.prep_trigger_handler.NotificationService")
    @patch("exec_assistant.workflows.prep_trigger_handler.update_meeting_status")
    @patch("exec_assistant.workflows.prep_trigger_handler.fetch_user")
    @patch("exec_assistant.workflows.prep_trigger_handler.fetch_meeting")
    def test_notification_service_failure(
        self,
        mock_fetch_meeting: Mock,
        mock_fetch_user: Mock,
        mock_update_status: Mock,
        mock_notification_service: Mock,
        valid_event: dict[str, Any],
        sample_meeting: Meeting,
        sample_user: User,
    ) -> None:
        """Test handler when notification service fails completely."""
        mock_fetch_meeting.return_value = sample_meeting
        mock_fetch_user.return_value = sample_user

        mock_service_instance = MagicMock()
        mock_notification_service.return_value = mock_service_instance

        # Notification fails
        notification_result = NotificationResult(
            status=NotificationStatus.FAILED,
            delivered_channels=[],
            failed_channels={
                NotificationChannel.SLACK: "API error",
                NotificationChannel.SMS: "Phone invalid",
                NotificationChannel.EMAIL: "SES quota exceeded",
            },
            message_id=None,
        )
        mock_service_instance.send_prep_notification.return_value = notification_result

        response = lambda_handler(valid_event, None)

        # Should still return 200 (notification attempted)
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["notification_result"]["status"] == "failed"
        assert len(body["notification_result"]["failed_channels"]) == 3

    @patch("exec_assistant.workflows.prep_trigger_handler.NotificationService")
    @patch("exec_assistant.workflows.prep_trigger_handler.save_meeting")
    @patch("exec_assistant.workflows.prep_trigger_handler.update_meeting_status")
    @patch("exec_assistant.workflows.prep_trigger_handler.fetch_user")
    @patch("exec_assistant.workflows.prep_trigger_handler.fetch_meeting")
    def test_notification_no_message_id(
        self,
        mock_fetch_meeting: Mock,
        mock_fetch_user: Mock,
        mock_update_status: Mock,
        mock_save_meeting: Mock,
        mock_notification_service: Mock,
        valid_event: dict[str, Any],
        sample_meeting: Meeting,
        sample_user: User,
    ) -> None:
        """Test handler when notification succeeds but has no message_id."""
        mock_fetch_meeting.return_value = sample_meeting
        mock_fetch_user.return_value = sample_user

        mock_service_instance = MagicMock()
        mock_notification_service.return_value = mock_service_instance

        # Notification succeeds but no message_id
        notification_result = NotificationResult(
            status=NotificationStatus.SUCCESS,
            delivered_channels=[NotificationChannel.EMAIL],
            failed_channels={},
            message_id=None,  # No message ID
        )
        mock_service_instance.send_prep_notification.return_value = notification_result

        response = lambda_handler(valid_event, None)

        # Should return 200
        assert response["statusCode"] == 200

        # save_meeting should not be called when message_id is None
        mock_save_meeting.assert_not_called()

    @patch("exec_assistant.workflows.prep_trigger_handler.fetch_user")
    @patch("exec_assistant.workflows.prep_trigger_handler.fetch_meeting")
    def test_dynamodb_error_on_fetch(
        self,
        mock_fetch_meeting: Mock,
        mock_fetch_user: Mock,
        valid_event: dict[str, Any],
    ) -> None:
        """Test handler when DynamoDB raises error during fetch."""
        mock_fetch_meeting.side_effect = ClientError(
            {"Error": {"Code": "ServiceUnavailable", "Message": "Service unavailable"}},
            "GetItem",
        )

        response = lambda_handler(valid_event, None)

        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert body["error"] == "InternalError"

    @patch("exec_assistant.workflows.prep_trigger_handler.save_meeting")
    @patch("exec_assistant.workflows.prep_trigger_handler.NotificationService")
    @patch("exec_assistant.workflows.prep_trigger_handler.update_meeting_status")
    @patch("exec_assistant.workflows.prep_trigger_handler.fetch_user")
    @patch("exec_assistant.workflows.prep_trigger_handler.fetch_meeting")
    def test_dynamodb_error_on_save(
        self,
        mock_fetch_meeting: Mock,
        mock_fetch_user: Mock,
        mock_update_status: Mock,
        mock_notification_service: Mock,
        mock_save_meeting: Mock,
        valid_event: dict[str, Any],
        sample_meeting: Meeting,
        sample_user: User,
    ) -> None:
        """Test handler when DynamoDB raises error during save."""
        mock_fetch_meeting.return_value = sample_meeting
        mock_fetch_user.return_value = sample_user

        mock_service_instance = MagicMock()
        mock_notification_service.return_value = mock_service_instance
        notification_result = NotificationResult(
            status=NotificationStatus.SUCCESS,
            delivered_channels=[NotificationChannel.SLACK],
            failed_channels={},
            message_id="ts_123",
        )
        mock_service_instance.send_prep_notification.return_value = notification_result

        # Save fails
        mock_save_meeting.side_effect = ClientError(
            {
                "Error": {
                    "Code": "ProvisionedThroughputExceededException",
                    "Message": "Rate exceeded",
                }
            },
            "PutItem",
        )

        response = lambda_handler(valid_event, None)

        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert body["error"] == "InternalError"


class TestFetchMeeting:
    """Tests for fetch_meeting function."""

    @patch("exec_assistant.workflows.prep_trigger_handler.dynamodb")
    def test_fetch_meeting_success(self, mock_dynamodb: Mock) -> None:
        """Test successful meeting fetch from DynamoDB."""
        # Setup mock table
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table

        meeting_data = {
            "meeting_id": "mtg-123",
            "user_id": "U12345",
            "title": "Test Meeting",
            "start_time": "2026-01-05T14:00:00+00:00",
            "end_time": "2026-01-05T15:00:00+00:00",
            "meeting_type": "leadership_team",
            "status": "classified",
            "attendees": ["user@example.com"],
            "created_at": "2026-01-04T10:00:00+00:00",
            "updated_at": "2026-01-04T10:00:00+00:00",
        }

        mock_table.get_item.return_value = {"Item": meeting_data}

        # Execute
        meeting = fetch_meeting("mtg-123")

        # Verify
        assert meeting is not None
        assert meeting.meeting_id == "mtg-123"
        assert meeting.title == "Test Meeting"
        assert meeting.status == MeetingStatus.CLASSIFIED
        mock_table.get_item.assert_called_once_with(Key={"meeting_id": "mtg-123"})

    @patch("exec_assistant.workflows.prep_trigger_handler.dynamodb")
    def test_fetch_meeting_not_found(self, mock_dynamodb: Mock) -> None:
        """Test fetching non-existent meeting."""
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.get_item.return_value = {}  # No Item key

        meeting = fetch_meeting("mtg-nonexistent")

        assert meeting is None

    @patch("exec_assistant.workflows.prep_trigger_handler.dynamodb")
    def test_fetch_meeting_dynamodb_error(self, mock_dynamodb: Mock) -> None:
        """Test DynamoDB error during fetch."""
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.get_item.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "Table not found"}},
            "GetItem",
        )

        with pytest.raises(ClientError):
            fetch_meeting("mtg-123")


class TestFetchUser:
    """Tests for fetch_user function."""

    @patch("exec_assistant.workflows.prep_trigger_handler.dynamodb")
    def test_fetch_user_success(self, mock_dynamodb: Mock) -> None:
        """Test successful user fetch from DynamoDB."""
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table

        user_data = {
            "user_id": "U12345",
            "google_id": "google-123",
            "email": "user@example.com",
            "name": "Test User",
            "phone_number": "+12345678901",
            "calendar_connected": True,
            "created_at": "2026-01-01T00:00:00+00:00",
            "last_login_at": "2026-01-04T10:00:00+00:00",
            "updated_at": "2026-01-04T10:00:00+00:00",
        }

        mock_table.get_item.return_value = {"Item": user_data}

        user = fetch_user("U12345")

        assert user is not None
        assert user.user_id == "U12345"
        assert user.email == "user@example.com"
        assert user.phone_number == "+12345678901"
        mock_table.get_item.assert_called_once_with(Key={"user_id": "U12345"})

    @patch("exec_assistant.workflows.prep_trigger_handler.dynamodb")
    def test_fetch_user_not_found(self, mock_dynamodb: Mock) -> None:
        """Test fetching non-existent user."""
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.get_item.return_value = {}

        user = fetch_user("U99999")

        assert user is None

    @patch("exec_assistant.workflows.prep_trigger_handler.dynamodb")
    def test_fetch_user_dynamodb_error(self, mock_dynamodb: Mock) -> None:
        """Test DynamoDB error during user fetch."""
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.get_item.side_effect = ClientError(
            {"Error": {"Code": "InternalServerError", "Message": "Internal error"}},
            "GetItem",
        )

        with pytest.raises(ClientError):
            fetch_user("U12345")


class TestUpdateMeetingStatus:
    """Tests for update_meeting_status function."""

    @pytest.fixture
    def sample_meeting(self) -> Meeting:
        """Create a sample meeting for testing."""
        return Meeting(
            meeting_id="mtg-123",
            user_id="U12345",
            title="Test Meeting",
            start_time=datetime.now(UTC) + timedelta(days=1),
            end_time=datetime.now(UTC) + timedelta(days=1, hours=1),
            status=MeetingStatus.CLASSIFIED,
        )

    @patch("exec_assistant.workflows.prep_trigger_handler.dynamodb")
    def test_update_meeting_status_success(
        self,
        mock_dynamodb: Mock,
        sample_meeting: Meeting,
    ) -> None:
        """Test successful status update."""
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table

        original_status = sample_meeting.status
        update_meeting_status(sample_meeting, MeetingStatus.PREP_SCHEDULED)

        # Verify status was updated
        assert sample_meeting.status == MeetingStatus.PREP_SCHEDULED
        assert sample_meeting.status != original_status

        # Verify DynamoDB call
        mock_table.put_item.assert_called_once()
        call_args = mock_table.put_item.call_args
        assert call_args.kwargs["Item"]["status"] == "prep_scheduled"

    @patch("exec_assistant.workflows.prep_trigger_handler.dynamodb")
    def test_update_meeting_status_updates_timestamp(
        self,
        mock_dynamodb: Mock,
        sample_meeting: Meeting,
    ) -> None:
        """Test that updated_at timestamp is updated."""
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table

        original_updated_at = sample_meeting.updated_at
        update_meeting_status(sample_meeting, MeetingStatus.PREP_SCHEDULED)

        # Timestamp should be updated
        assert sample_meeting.updated_at > original_updated_at

    @patch("exec_assistant.workflows.prep_trigger_handler.dynamodb")
    def test_update_meeting_status_dynamodb_error(
        self,
        mock_dynamodb: Mock,
        sample_meeting: Meeting,
    ) -> None:
        """Test DynamoDB error during status update."""
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.put_item.side_effect = ClientError(
            {"Error": {"Code": "ConditionalCheckFailedException", "Message": "Condition failed"}},
            "PutItem",
        )

        with pytest.raises(ClientError):
            update_meeting_status(sample_meeting, MeetingStatus.PREP_SCHEDULED)


class TestSaveMeeting:
    """Tests for save_meeting function."""

    @pytest.fixture
    def sample_meeting(self) -> Meeting:
        """Create a sample meeting for testing."""
        return Meeting(
            meeting_id="mtg-123",
            user_id="U12345",
            title="Test Meeting",
            start_time=datetime.now(UTC) + timedelta(days=1),
            end_time=datetime.now(UTC) + timedelta(days=1, hours=1),
            status=MeetingStatus.PREP_SCHEDULED,
            notification_id="ts_123456.789",
            notification_sent_at=datetime.now(UTC),
        )

    @patch("exec_assistant.workflows.prep_trigger_handler.dynamodb")
    def test_save_meeting_success(
        self,
        mock_dynamodb: Mock,
        sample_meeting: Meeting,
    ) -> None:
        """Test successful meeting save."""
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table

        save_meeting(sample_meeting)

        mock_table.put_item.assert_called_once()
        call_args = mock_table.put_item.call_args
        item = call_args.kwargs["Item"]
        assert item["meeting_id"] == "mtg-123"
        assert item["notification_id"] == "ts_123456.789"
        assert "notification_sent_at" in item

    @patch("exec_assistant.workflows.prep_trigger_handler.dynamodb")
    def test_save_meeting_dynamodb_error(
        self,
        mock_dynamodb: Mock,
        sample_meeting: Meeting,
    ) -> None:
        """Test DynamoDB error during save."""
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.put_item.side_effect = ClientError(
            {"Error": {"Code": "ValidationException", "Message": "Invalid item"}},
            "PutItem",
        )

        with pytest.raises(ClientError):
            save_meeting(sample_meeting)


class TestGetNotificationChannels:
    """Tests for get_notification_channels function."""

    def test_channels_with_phone_number(self) -> None:
        """Test channel selection when user has phone number."""
        user = User(
            user_id="U12345",
            google_id="google-123",
            email="user@example.com",
            name="Test User",
            phone_number="+12345678901",
        )

        channels = get_notification_channels(user)

        assert NotificationChannel.SLACK in channels
        assert NotificationChannel.SMS in channels
        assert NotificationChannel.EMAIL in channels
        # Slack should be first
        assert channels[0] == NotificationChannel.SLACK

    def test_channels_without_phone_number(self) -> None:
        """Test channel selection when user has no phone number."""
        user = User(
            user_id="U12345",
            google_id="google-123",
            email="user@example.com",
            name="Test User",
            phone_number=None,
        )

        channels = get_notification_channels(user)

        assert NotificationChannel.SLACK in channels
        assert NotificationChannel.SMS not in channels
        assert NotificationChannel.EMAIL in channels

    def test_channels_priority_order(self) -> None:
        """Test that channels are returned in priority order."""
        user = User(
            user_id="U12345",
            google_id="google-123",
            email="user@example.com",
            name="Test User",
            phone_number="+12345678901",
        )

        channels = get_notification_channels(user)

        # Expected order: Slack, SMS, Email
        expected_order = [
            NotificationChannel.SLACK,
            NotificationChannel.SMS,
            NotificationChannel.EMAIL,
        ]
        assert channels == expected_order


class TestIdempotency:
    """Tests for idempotent behavior of handler.

    Note: Current implementation does NOT check notification_sent_at
    for idempotency. These tests document the expected behavior that
    should be implemented.
    """

    @pytest.mark.skip(reason="Idempotency not yet implemented - TODO")
    @patch("exec_assistant.workflows.prep_trigger_handler.NotificationService")
    @patch("exec_assistant.workflows.prep_trigger_handler.fetch_user")
    @patch("exec_assistant.workflows.prep_trigger_handler.fetch_meeting")
    def test_duplicate_event_skip_notification(
        self,
        mock_fetch_meeting: Mock,
        mock_fetch_user: Mock,
        mock_notification_service: Mock,
    ) -> None:
        """Test that duplicate events don't trigger duplicate notifications."""
        # Meeting already has notification_sent_at set
        meeting = Meeting(
            meeting_id="gcal-abc123",
            user_id="U12345",
            title="Test Meeting",
            start_time=datetime.now(UTC) + timedelta(days=1),
            end_time=datetime.now(UTC) + timedelta(days=1, hours=1),
            status=MeetingStatus.PREP_SCHEDULED,
            notification_id="ts_original",
            notification_sent_at=datetime.now(UTC) - timedelta(minutes=5),
        )

        user = User(
            user_id="U12345",
            google_id="google-123",
            email="user@example.com",
            name="Test User",
        )

        mock_fetch_meeting.return_value = meeting
        mock_fetch_user.return_value = user

        event = {
            "detail": {
                "meeting_id": "gcal-abc123",
                "user_id": "U12345",
            }
        }

        response = lambda_handler(event, None)

        # Should skip notification
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert "already sent" in body["message"].lower()

        # Notification service should not be called
        mock_notification_service.assert_not_called()


class TestEdgeCases:
    """Tests for edge cases and unusual scenarios."""

    @patch("exec_assistant.workflows.prep_trigger_handler.NotificationService")
    @patch("exec_assistant.workflows.prep_trigger_handler.save_meeting")
    @patch("exec_assistant.workflows.prep_trigger_handler.update_meeting_status")
    @patch("exec_assistant.workflows.prep_trigger_handler.fetch_user")
    @patch("exec_assistant.workflows.prep_trigger_handler.fetch_meeting")
    def test_meeting_with_discovered_status(
        self,
        mock_fetch_meeting: Mock,
        mock_fetch_user: Mock,
        mock_update_status: Mock,
        mock_save_meeting: Mock,
        mock_notification_service: Mock,
    ) -> None:
        """Test handler with meeting in DISCOVERED status (valid for prep)."""
        meeting = Meeting(
            meeting_id="gcal-abc123",
            user_id="U12345",
            title="Test Meeting",
            start_time=datetime.now(UTC) + timedelta(days=1),
            end_time=datetime.now(UTC) + timedelta(days=1, hours=1),
            status=MeetingStatus.DISCOVERED,  # Valid status
        )

        user = User(
            user_id="U12345",
            google_id="google-123",
            email="user@example.com",
            name="Test User",
        )

        mock_fetch_meeting.return_value = meeting
        mock_fetch_user.return_value = user

        mock_service_instance = MagicMock()
        mock_notification_service.return_value = mock_service_instance
        mock_service_instance.send_prep_notification.return_value = NotificationResult(
            status=NotificationStatus.SUCCESS,
            delivered_channels=[NotificationChannel.SLACK],
            failed_channels={},
            message_id="ts_123",
        )

        event = {
            "detail": {
                "meeting_id": "gcal-abc123",
                "user_id": "U12345",
            }
        }

        response = lambda_handler(event, None)

        # Should process successfully
        assert response["statusCode"] == 200
        mock_update_status.assert_called_once()

    @patch("exec_assistant.workflows.prep_trigger_handler.fetch_user")
    @patch("exec_assistant.workflows.prep_trigger_handler.fetch_meeting")
    def test_meeting_with_cancelled_status(
        self,
        mock_fetch_meeting: Mock,
        mock_fetch_user: Mock,
    ) -> None:
        """Test handler with cancelled meeting."""
        meeting = Meeting(
            meeting_id="gcal-abc123",
            user_id="U12345",
            title="Test Meeting",
            start_time=datetime.now(UTC) + timedelta(days=1),
            end_time=datetime.now(UTC) + timedelta(days=1, hours=1),
            status=MeetingStatus.CANCELLED,
        )

        user = User(
            user_id="U12345",
            google_id="google-123",
            email="user@example.com",
            name="Test User",
        )

        mock_fetch_meeting.return_value = meeting
        mock_fetch_user.return_value = user

        event = {
            "detail": {
                "meeting_id": "gcal-abc123",
                "user_id": "U12345",
            }
        }

        response = lambda_handler(event, None)

        # Should skip cancelled meetings
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert "already processed" in body["message"] or "invalid state" in body["message"]

    def test_malformed_event_structure(self) -> None:
        """Test handler with completely malformed event."""
        event = "not a dict"  # type: ignore

        response = lambda_handler(event, None)  # type: ignore

        # Should return 500 error
        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert body["error"] == "InternalError"

    def test_event_with_extra_fields(self) -> None:
        """Test that handler ignores extra fields in event."""
        event = {
            "detail": {
                "meeting_id": "gcal-abc123",
                "user_id": "U12345",
                "extra_field": "should be ignored",
                "another_field": 12345,
            }
        }

        # Should not crash with extra fields
        response = lambda_handler(event, None)
        # Will fail on fetch_meeting, but shouldn't crash on event parsing
        assert response["statusCode"] in (400, 500)
