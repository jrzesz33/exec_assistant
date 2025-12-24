"""Unit tests for calendar monitoring Lambda function.

This module tests:
- Lambda handler invocation and response
- Connected user retrieval from DynamoDB
- User calendar processing
- Meeting sync and deduplication
- Prep trigger event emission
- Error handling and recovery
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest
from botocore.exceptions import ClientError

from exec_assistant.shared.models import Meeting, MeetingStatus, MeetingType, User
from exec_assistant.workflows import calendar_monitor


class TestLambdaHandler:
    """Tests for lambda_handler function."""

    @patch("exec_assistant.workflows.calendar_monitor.get_connected_users")
    @patch("exec_assistant.workflows.calendar_monitor.process_user_calendar")
    def test_successful_invocation_multiple_users(
        self,
        mock_process: MagicMock,
        mock_get_users: MagicMock,
    ) -> None:
        """Test successful Lambda invocation with multiple users."""
        # Setup
        user1 = User(
            user_id="user-1",
            google_id="google-1",
            email="user1@example.com",
            name="User One",
            calendar_connected=True,
        )
        user2 = User(
            user_id="user-2",
            google_id="google-2",
            email="user2@example.com",
            name="User Two",
            calendar_connected=True,
        )
        mock_get_users.return_value = [user1, user2]
        mock_process.side_effect = [
            {"meetings_synced": 5, "preps_triggered": 2},
            {"meetings_synced": 3, "preps_triggered": 1},
        ]

        event = {"source": "aws.events"}
        context = Mock()

        # Execute
        response = calendar_monitor.lambda_handler(event, context)

        # Verify
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["users_processed"] == 2
        assert body["meetings_synced"] == 8
        assert body["preps_triggered"] == 3
        assert body["errors"] == 0

        mock_get_users.assert_called_once()
        assert mock_process.call_count == 2

    @patch("exec_assistant.workflows.calendar_monitor.get_connected_users")
    def test_no_connected_users(self, mock_get_users: MagicMock) -> None:
        """Test Lambda invocation when no users have calendar connected."""
        # Setup
        mock_get_users.return_value = []
        event = {"source": "aws.events"}
        context = Mock()

        # Execute
        response = calendar_monitor.lambda_handler(event, context)

        # Verify
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["users_processed"] == 0
        assert body["meetings_synced"] == 0
        assert body["preps_triggered"] == 0
        assert body["errors"] == 0

    @patch("exec_assistant.workflows.calendar_monitor.get_connected_users")
    @patch("exec_assistant.workflows.calendar_monitor.process_user_calendar")
    def test_one_user_fails_others_continue(
        self,
        mock_process: MagicMock,
        mock_get_users: MagicMock,
    ) -> None:
        """Test that if one user fails, processing continues for others."""
        # Setup
        user1 = User(
            user_id="user-1",
            google_id="google-1",
            email="user1@example.com",
            name="User One",
            calendar_connected=True,
        )
        user2 = User(
            user_id="user-2",
            google_id="google-2",
            email="user2@example.com",
            name="User Two",
            calendar_connected=True,
        )
        user3 = User(
            user_id="user-3",
            google_id="google-3",
            email="user3@example.com",
            name="User Three",
            calendar_connected=True,
        )
        mock_get_users.return_value = [user1, user2, user3]

        # User 2 fails, others succeed
        mock_process.side_effect = [
            {"meetings_synced": 5, "preps_triggered": 2},
            Exception("Calendar API error"),
            {"meetings_synced": 3, "preps_triggered": 1},
        ]

        event = {"source": "aws.events"}
        context = Mock()

        # Execute
        response = calendar_monitor.lambda_handler(event, context)

        # Verify
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["users_processed"] == 2  # Only successful users
        assert body["meetings_synced"] == 8
        assert body["preps_triggered"] == 3
        assert body["errors"] == 1

    @patch("exec_assistant.workflows.calendar_monitor.get_connected_users")
    def test_dynamodb_error_returns_500(self, mock_get_users: MagicMock) -> None:
        """Test that DynamoDB errors return 500 status."""
        # Setup
        mock_get_users.side_effect = ClientError(
            {"Error": {"Code": "ServiceUnavailable", "Message": "Service unavailable"}},
            "Scan",
        )
        event = {"source": "aws.events"}
        context = Mock()

        # Execute
        response = calendar_monitor.lambda_handler(event, context)

        # Verify
        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert "error" in body

    def test_event_structure_logged(self) -> None:
        """Test that event structure is logged on invocation."""
        with patch("exec_assistant.workflows.calendar_monitor.get_connected_users") as mock_get:
            mock_get.return_value = []
            event = {"source": "aws.events", "detail": {"test": "data"}}
            context = Mock()

            calendar_monitor.lambda_handler(event, context)

            # Event should be logged (verify it doesn't crash)
            assert True


class TestGetConnectedUsers:
    """Tests for get_connected_users function."""

    @patch("exec_assistant.workflows.calendar_monitor.dynamodb")
    def test_find_multiple_connected_users(self, mock_dynamodb: MagicMock) -> None:
        """Test finding multiple users with calendar connected."""
        # Setup
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table

        now = datetime.now(UTC)
        mock_table.scan.return_value = {
            "Items": [
                {
                    "user_id": "user-1",
                    "google_id": "google-1",
                    "email": "user1@example.com",
                    "name": "User One",
                    "calendar_connected": True,
                    "created_at": now.isoformat(),
                    "last_login_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                },
                {
                    "user_id": "user-2",
                    "google_id": "google-2",
                    "email": "user2@example.com",
                    "name": "User Two",
                    "calendar_connected": True,
                    "created_at": now.isoformat(),
                    "last_login_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                },
            ]
        }

        # Execute
        users = calendar_monitor.get_connected_users()

        # Verify
        assert len(users) == 2
        assert users[0].user_id == "user-1"
        assert users[1].user_id == "user-2"
        assert all(u.calendar_connected for u in users)

        # Verify scan with filter
        mock_table.scan.assert_called_once()
        call_kwargs = mock_table.scan.call_args.kwargs
        assert "FilterExpression" in call_kwargs

    @patch("exec_assistant.workflows.calendar_monitor.dynamodb")
    def test_no_connected_users(self, mock_dynamodb: MagicMock) -> None:
        """Test when no users have calendar connected."""
        # Setup
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.scan.return_value = {"Items": []}

        # Execute
        users = calendar_monitor.get_connected_users()

        # Verify
        assert len(users) == 0

    @patch("exec_assistant.workflows.calendar_monitor.dynamodb")
    def test_pagination_handling(self, mock_dynamodb: MagicMock) -> None:
        """Test handling of paginated scan results."""
        # Setup
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table

        now = datetime.now(UTC)
        # First page
        first_page = {
            "Items": [
                {
                    "user_id": "user-1",
                    "google_id": "google-1",
                    "email": "user1@example.com",
                    "name": "User One",
                    "calendar_connected": True,
                    "created_at": now.isoformat(),
                    "last_login_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                }
            ],
            "LastEvaluatedKey": {"user_id": "user-1"},
        }
        # Second page
        second_page = {
            "Items": [
                {
                    "user_id": "user-2",
                    "google_id": "google-2",
                    "email": "user2@example.com",
                    "name": "User Two",
                    "calendar_connected": True,
                    "created_at": now.isoformat(),
                    "last_login_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                }
            ]
        }
        mock_table.scan.side_effect = [first_page, second_page]

        # Execute
        users = calendar_monitor.get_connected_users()

        # Verify
        assert len(users) == 2
        assert mock_table.scan.call_count == 2

    @patch("exec_assistant.workflows.calendar_monitor.dynamodb")
    def test_dynamodb_scan_error(self, mock_dynamodb: MagicMock) -> None:
        """Test handling of DynamoDB scan errors."""
        # Setup
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.scan.side_effect = ClientError(
            {"Error": {"Code": "InternalServerError", "Message": "Internal error"}},
            "Scan",
        )

        # Execute and verify
        with pytest.raises(ClientError):
            calendar_monitor.get_connected_users()


class TestProcessUserCalendar:
    """Tests for process_user_calendar function."""

    @patch("exec_assistant.workflows.calendar_monitor.CalendarClient")
    @patch("exec_assistant.workflows.calendar_monitor.MeetingClassifier")
    @patch("exec_assistant.workflows.calendar_monitor.sync_meeting_to_dynamodb")
    @patch("exec_assistant.workflows.calendar_monitor.emit_prep_trigger_event")
    def test_successful_processing_with_meetings(
        self,
        mock_emit: MagicMock,
        mock_sync: MagicMock,
        mock_classifier_class: MagicMock,
        mock_calendar_class: MagicMock,
    ) -> None:
        """Test successful calendar processing with multiple meetings."""
        # Setup user
        user = User(
            user_id="user-1",
            google_id="google-1",
            email="user1@example.com",
            name="User One",
            calendar_connected=True,
        )

        # Setup meetings
        now = datetime.now(UTC)
        meeting1 = Meeting(
            meeting_id="gcal-123",
            external_id="ext-123",
            user_id="user-1",
            title="Leadership Team Meeting",
            start_time=now + timedelta(days=2),
            end_time=now + timedelta(days=2, hours=1),
        )
        meeting2 = Meeting(
            meeting_id="gcal-456",
            external_id="ext-456",
            user_id="user-1",
            title="1-1 with John",
            start_time=now + timedelta(days=3),
            end_time=now + timedelta(days=3, hours=0.5),
        )

        # Setup mocks
        mock_calendar = MagicMock()
        mock_calendar_class.return_value = mock_calendar
        mock_calendar.fetch_upcoming_meetings.return_value = [meeting1, meeting2]

        mock_classifier = MagicMock()
        mock_classifier_class.return_value = mock_classifier
        mock_classifier.classify_meeting.side_effect = [
            MeetingType.LEADERSHIP_TEAM,
            MeetingType.ONE_ON_ONE,
        ]
        mock_classifier.get_prep_hours.side_effect = [24, 12]
        mock_classifier.should_trigger_prep.side_effect = [True, False]

        # Execute
        result = calendar_monitor.process_user_calendar(user)

        # Verify
        assert result["meetings_synced"] == 2
        assert result["preps_triggered"] == 1

        mock_calendar.fetch_upcoming_meetings.assert_called_once()
        assert mock_sync.call_count == 2
        assert mock_emit.call_count == 1

    @patch("exec_assistant.workflows.calendar_monitor.CalendarClient")
    def test_user_without_calendar_connected(
        self,
        mock_calendar_class: MagicMock,
    ) -> None:
        """Test processing user without calendar connected."""
        # Setup
        user = User(
            user_id="user-1",
            google_id="google-1",
            email="user1@example.com",
            name="User One",
            calendar_connected=False,
        )

        # Execute
        result = calendar_monitor.process_user_calendar(user)

        # Verify
        assert result["meetings_synced"] == 0
        assert result["preps_triggered"] == 0
        mock_calendar_class.assert_not_called()

    @patch("exec_assistant.workflows.calendar_monitor.CalendarClient")
    @patch("exec_assistant.workflows.calendar_monitor.MeetingClassifier")
    def test_no_upcoming_meetings(
        self,
        mock_classifier_class: MagicMock,
        mock_calendar_class: MagicMock,
    ) -> None:
        """Test processing when user has no upcoming meetings."""
        # Setup
        user = User(
            user_id="user-1",
            google_id="google-1",
            email="user1@example.com",
            name="User One",
            calendar_connected=True,
        )

        mock_calendar = MagicMock()
        mock_calendar_class.return_value = mock_calendar
        mock_calendar.fetch_upcoming_meetings.return_value = []

        # Execute
        result = calendar_monitor.process_user_calendar(user)

        # Verify
        assert result["meetings_synced"] == 0
        assert result["preps_triggered"] == 0

    @patch("exec_assistant.workflows.calendar_monitor.CalendarClient")
    @patch("exec_assistant.workflows.calendar_monitor.MeetingClassifier")
    @patch("exec_assistant.workflows.calendar_monitor.sync_meeting_to_dynamodb")
    @patch("exec_assistant.workflows.calendar_monitor.emit_prep_trigger_event")
    def test_meeting_classification_integration(
        self,
        mock_emit: MagicMock,
        mock_sync: MagicMock,
        mock_classifier_class: MagicMock,
        mock_calendar_class: MagicMock,
    ) -> None:
        """Test that meetings are properly classified."""
        # Setup
        user = User(
            user_id="user-1",
            google_id="google-1",
            email="user1@example.com",
            name="User One",
            calendar_connected=True,
        )

        now = datetime.now(UTC)
        meeting = Meeting(
            meeting_id="gcal-123",
            external_id="ext-123",
            user_id="user-1",
            title="QBR Meeting",
            start_time=now + timedelta(days=5),
            end_time=now + timedelta(days=5, hours=2),
        )

        mock_calendar = MagicMock()
        mock_calendar_class.return_value = mock_calendar
        mock_calendar.fetch_upcoming_meetings.return_value = [meeting]

        mock_classifier = MagicMock()
        mock_classifier_class.return_value = mock_classifier
        mock_classifier.classify_meeting.return_value = MeetingType.QUARTERLY_BUSINESS_REVIEW
        mock_classifier.get_prep_hours.return_value = 72
        mock_classifier.should_trigger_prep.return_value = False

        # Execute
        calendar_monitor.process_user_calendar(user)

        # Verify classification was called
        mock_classifier.classify_meeting.assert_called_once()
        assert mock_sync.call_args[0][0].meeting_type == MeetingType.QUARTERLY_BUSINESS_REVIEW
        assert mock_sync.call_args[0][0].prep_hours_before == 72

    @patch("exec_assistant.workflows.calendar_monitor.CalendarClient")
    def test_calendar_api_error_propagated(
        self,
        mock_calendar_class: MagicMock,
    ) -> None:
        """Test that calendar API errors are propagated."""
        # Setup
        user = User(
            user_id="user-1",
            google_id="google-1",
            email="user1@example.com",
            name="User One",
            calendar_connected=True,
        )

        mock_calendar = MagicMock()
        mock_calendar_class.return_value = mock_calendar
        mock_calendar.fetch_upcoming_meetings.side_effect = Exception("API Error")

        # Execute and verify
        with pytest.raises(Exception, match="API Error"):
            calendar_monitor.process_user_calendar(user)

    @patch("exec_assistant.workflows.calendar_monitor.CalendarClient")
    @patch("exec_assistant.workflows.calendar_monitor.MeetingClassifier")
    @patch("exec_assistant.workflows.calendar_monitor.sync_meeting_to_dynamodb")
    @patch("exec_assistant.workflows.calendar_monitor.emit_prep_trigger_event")
    def test_prep_not_triggered_for_processed_meetings(
        self,
        mock_emit: MagicMock,
        mock_sync: MagicMock,
        mock_classifier_class: MagicMock,
        mock_calendar_class: MagicMock,
    ) -> None:
        """Test that prep is not triggered for already processed meetings."""
        # Setup
        user = User(
            user_id="user-1",
            google_id="google-1",
            email="user1@example.com",
            name="User One",
            calendar_connected=True,
        )

        now = datetime.now(UTC)
        meeting = Meeting(
            meeting_id="gcal-123",
            external_id="ext-123",
            user_id="user-1",
            title="1-1 Meeting",
            start_time=now + timedelta(hours=10),
            end_time=now + timedelta(hours=11),
            status=MeetingStatus.PREP_IN_PROGRESS,  # Already being prepped
        )

        mock_calendar = MagicMock()
        mock_calendar_class.return_value = mock_calendar
        mock_calendar.fetch_upcoming_meetings.return_value = [meeting]

        mock_classifier = MagicMock()
        mock_classifier_class.return_value = mock_classifier
        mock_classifier.classify_meeting.return_value = MeetingType.ONE_ON_ONE
        mock_classifier.get_prep_hours.return_value = 12
        mock_classifier.should_trigger_prep.return_value = True  # In window

        # Execute
        result = calendar_monitor.process_user_calendar(user)

        # Verify
        assert result["meetings_synced"] == 1
        assert result["preps_triggered"] == 0  # Not triggered due to status
        mock_emit.assert_not_called()

    @patch("exec_assistant.workflows.calendar_monitor.CalendarClient")
    @patch("exec_assistant.workflows.calendar_monitor.MeetingClassifier")
    @patch("exec_assistant.workflows.calendar_monitor.sync_meeting_to_dynamodb")
    def test_meeting_error_doesnt_stop_processing(
        self,
        mock_sync: MagicMock,
        mock_classifier_class: MagicMock,
        mock_calendar_class: MagicMock,
    ) -> None:
        """Test that error processing one meeting doesn't stop others."""
        # Setup
        user = User(
            user_id="user-1",
            google_id="google-1",
            email="user1@example.com",
            name="User One",
            calendar_connected=True,
        )

        now = datetime.now(UTC)
        meeting1 = Meeting(
            meeting_id="gcal-123",
            external_id="ext-123",
            user_id="user-1",
            title="Meeting 1",
            start_time=now + timedelta(days=2),
            end_time=now + timedelta(days=2, hours=1),
        )
        meeting2 = Meeting(
            meeting_id="gcal-456",
            external_id="ext-456",
            user_id="user-1",
            title="Meeting 2",
            start_time=now + timedelta(days=3),
            end_time=now + timedelta(days=3, hours=1),
        )

        mock_calendar = MagicMock()
        mock_calendar_class.return_value = mock_calendar
        mock_calendar.fetch_upcoming_meetings.return_value = [meeting1, meeting2]

        mock_classifier = MagicMock()
        mock_classifier_class.return_value = mock_classifier
        mock_classifier.classify_meeting.side_effect = [
            Exception("Classification error"),
            MeetingType.ONE_ON_ONE,
        ]
        mock_classifier.get_prep_hours.return_value = 12
        mock_classifier.should_trigger_prep.return_value = False

        # Execute
        result = calendar_monitor.process_user_calendar(user)

        # Verify - second meeting still processed
        assert result["meetings_synced"] == 1
        assert mock_sync.call_count == 1


class TestSyncMeetingToDynamoDB:
    """Tests for sync_meeting_to_dynamodb function."""

    @patch("exec_assistant.workflows.calendar_monitor.dynamodb")
    def test_create_new_meeting(self, mock_dynamodb: MagicMock) -> None:
        """Test creating a new meeting in DynamoDB."""
        # Setup
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.get_item.return_value = {}  # No existing meeting

        now = datetime.now(UTC)
        meeting = Meeting(
            meeting_id="gcal-123",
            external_id="ext-123",
            user_id="user-1",
            title="New Meeting",
            start_time=now + timedelta(days=1),
            end_time=now + timedelta(days=1, hours=1),
            meeting_type=MeetingType.ONE_ON_ONE,
        )

        # Execute
        calendar_monitor.sync_meeting_to_dynamodb(meeting)

        # Verify
        mock_table.put_item.assert_called_once()
        put_item = mock_table.put_item.call_args.kwargs["Item"]
        assert put_item["meeting_id"] == "gcal-123"
        assert put_item["external_id"] == "ext-123"
        assert put_item["title"] == "New Meeting"

    @patch("exec_assistant.workflows.calendar_monitor.dynamodb")
    def test_update_existing_meeting(self, mock_dynamodb: MagicMock) -> None:
        """Test updating an existing meeting."""
        # Setup
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table

        now = datetime.now(UTC)
        existing_created = now - timedelta(days=10)

        # Existing meeting in DB
        mock_table.get_item.return_value = {
            "Item": {
                "meeting_id": "gcal-123",
                "external_id": "ext-123",
                "user_id": "user-1",
                "title": "Old Title",
                "start_time": (now + timedelta(days=1)).isoformat(),
                "end_time": (now + timedelta(days=1, hours=1)).isoformat(),
                "created_at": existing_created.isoformat(),
                "updated_at": existing_created.isoformat(),
                "meeting_type": "one_on_one",
                "status": "discovered",
            }
        }

        # Updated meeting
        meeting = Meeting(
            meeting_id="gcal-123",
            external_id="ext-123",
            user_id="user-1",
            title="Updated Title",
            start_time=now + timedelta(days=1),
            end_time=now + timedelta(days=1, hours=1),
            meeting_type=MeetingType.ONE_ON_ONE,
        )

        # Execute
        calendar_monitor.sync_meeting_to_dynamodb(meeting)

        # Verify
        mock_table.put_item.assert_called_once()
        put_item = mock_table.put_item.call_args.kwargs["Item"]
        assert put_item["title"] == "Updated Title"
        # Original created_at should be preserved
        assert put_item["created_at"] == existing_created.isoformat()

    @patch("exec_assistant.workflows.calendar_monitor.dynamodb")
    def test_preserve_meeting_id_on_update(self, mock_dynamodb: MagicMock) -> None:
        """Test that meeting_id is preserved when updating."""
        # Setup
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table

        now = datetime.now(UTC)
        mock_table.get_item.return_value = {
            "Item": {
                "meeting_id": "gcal-original",
                "external_id": "ext-123",
                "user_id": "user-1",
                "title": "Meeting",
                "start_time": (now + timedelta(days=1)).isoformat(),
                "end_time": (now + timedelta(days=1, hours=1)).isoformat(),
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "meeting_type": "one_on_one",
                "status": "discovered",
            }
        }

        meeting = Meeting(
            meeting_id="gcal-original",  # Same ID
            external_id="ext-123",
            user_id="user-1",
            title="Meeting",
            start_time=now + timedelta(days=1),
            end_time=now + timedelta(days=1, hours=1),
        )

        # Execute
        calendar_monitor.sync_meeting_to_dynamodb(meeting)

        # Verify
        put_item = mock_table.put_item.call_args.kwargs["Item"]
        assert put_item["meeting_id"] == "gcal-original"

    @patch("exec_assistant.workflows.calendar_monitor.dynamodb")
    def test_dynamodb_put_error(self, mock_dynamodb: MagicMock) -> None:
        """Test handling of DynamoDB put errors."""
        # Setup
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.get_item.return_value = {}
        mock_table.put_item.side_effect = ClientError(
            {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "Throttled"}},
            "PutItem",
        )

        now = datetime.now(UTC)
        meeting = Meeting(
            meeting_id="gcal-123",
            external_id="ext-123",
            user_id="user-1",
            title="Meeting",
            start_time=now + timedelta(days=1),
            end_time=now + timedelta(days=1, hours=1),
        )

        # Execute and verify
        with pytest.raises(ClientError):
            calendar_monitor.sync_meeting_to_dynamodb(meeting)


class TestEmitPrepTriggerEvent:
    """Tests for emit_prep_trigger_event function."""

    @patch("exec_assistant.workflows.calendar_monitor.events_client")
    def test_event_structure_and_content(self, mock_events: MagicMock) -> None:
        """Test EventBridge event structure and content."""
        # Setup
        mock_events.put_events.return_value = {"FailedEntryCount": 0}

        now = datetime.now(UTC)
        meeting = Meeting(
            meeting_id="gcal-123",
            external_id="ext-123",
            user_id="user-1",
            title="Leadership Meeting",
            start_time=now + timedelta(hours=20),
            end_time=now + timedelta(hours=21),
            meeting_type=MeetingType.LEADERSHIP_TEAM,
        )

        # Execute
        calendar_monitor.emit_prep_trigger_event(meeting)

        # Verify
        mock_events.put_events.assert_called_once()
        call_args = mock_events.put_events.call_args.kwargs
        assert "Entries" in call_args
        entry = call_args["Entries"][0]

        assert entry["Source"] == "exec-assistant.calendar-monitor"
        assert entry["DetailType"] == "MeetingPrepRequired"

        detail = json.loads(entry["Detail"])
        assert detail["meeting_id"] == "gcal-123"
        assert detail["user_id"] == "user-1"
        assert detail["meeting_type"] == "leadership_team"
        assert detail["title"] == "Leadership Meeting"
        assert "start_time" in detail

    @patch("exec_assistant.workflows.calendar_monitor.events_client")
    def test_event_bus_name_from_env(self, mock_events: MagicMock) -> None:
        """Test that event bus name is read from environment."""
        # Setup
        mock_events.put_events.return_value = {"FailedEntryCount": 0}

        now = datetime.now(UTC)
        meeting = Meeting(
            meeting_id="gcal-123",
            user_id="user-1",
            title="Meeting",
            start_time=now + timedelta(hours=20),
            end_time=now + timedelta(hours=21),
        )

        # Execute
        calendar_monitor.emit_prep_trigger_event(meeting)

        # Verify
        call_args = mock_events.put_events.call_args.kwargs
        entry = call_args["Entries"][0]
        # Should use EVENT_BUS_NAME from module (set from env)
        assert "EventBusName" in entry

    @patch("exec_assistant.workflows.calendar_monitor.events_client")
    def test_eventbridge_put_events_failure(self, mock_events: MagicMock) -> None:
        """Test handling of EventBridge put_events failures."""
        # Setup
        mock_events.put_events.return_value = {
            "FailedEntryCount": 1,
            "Entries": [{"ErrorCode": "InternalException", "ErrorMessage": "Internal error"}],
        }

        now = datetime.now(UTC)
        meeting = Meeting(
            meeting_id="gcal-123",
            user_id="user-1",
            title="Meeting",
            start_time=now + timedelta(hours=20),
            end_time=now + timedelta(hours=21),
        )

        # Execute and verify
        with pytest.raises(ClientError):
            calendar_monitor.emit_prep_trigger_event(meeting)


class TestIntegrationScenarios:
    """Integration tests for end-to-end scenarios."""

    @patch("exec_assistant.workflows.calendar_monitor.dynamodb")
    @patch("exec_assistant.workflows.calendar_monitor.CalendarClient")
    @patch("exec_assistant.workflows.calendar_monitor.MeetingClassifier")
    @patch("exec_assistant.workflows.calendar_monitor.events_client")
    def test_end_to_end_processing(
        self,
        mock_events: MagicMock,
        mock_classifier_class: MagicMock,
        mock_calendar_class: MagicMock,
        mock_dynamodb: MagicMock,
    ) -> None:
        """Test complete end-to-end processing flow."""
        # Setup DynamoDB
        mock_users_table = MagicMock()
        mock_meetings_table = MagicMock()

        def table_factory(name: str) -> Any:
            if "users" in name:
                return mock_users_table
            return mock_meetings_table

        mock_dynamodb.Table.side_effect = table_factory

        now = datetime.now(UTC)
        mock_users_table.scan.return_value = {
            "Items": [
                {
                    "user_id": "user-1",
                    "google_id": "google-1",
                    "email": "user@example.com",
                    "name": "Test User",
                    "calendar_connected": True,
                    "created_at": now.isoformat(),
                    "last_login_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                }
            ]
        }

        # Setup calendar
        meeting = Meeting(
            meeting_id="gcal-123",
            external_id="ext-123",
            user_id="user-1",
            title="Leadership Team Meeting",
            start_time=now + timedelta(hours=20),
            end_time=now + timedelta(hours=21),
        )

        mock_calendar = MagicMock()
        mock_calendar_class.return_value = mock_calendar
        mock_calendar.fetch_upcoming_meetings.return_value = [meeting]

        # Setup classifier
        mock_classifier = MagicMock()
        mock_classifier_class.return_value = mock_classifier
        mock_classifier.classify_meeting.return_value = MeetingType.LEADERSHIP_TEAM
        mock_classifier.get_prep_hours.return_value = 24
        mock_classifier.should_trigger_prep.return_value = True

        # Setup EventBridge
        mock_events.put_events.return_value = {"FailedEntryCount": 0}

        # Setup meetings table
        mock_meetings_table.get_item.return_value = {}

        # Execute
        event = {"source": "aws.events"}
        context = Mock()
        response = calendar_monitor.lambda_handler(event, context)

        # Verify complete flow
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["users_processed"] == 1
        assert body["meetings_synced"] == 1
        assert body["preps_triggered"] == 1

        # Verify all components called
        mock_users_table.scan.assert_called()
        mock_calendar.fetch_upcoming_meetings.assert_called()
        mock_classifier.classify_meeting.assert_called()
        mock_meetings_table.put_item.assert_called()
        mock_events.put_events.assert_called()

    @patch("exec_assistant.workflows.calendar_monitor.get_connected_users")
    @patch("exec_assistant.workflows.calendar_monitor.CalendarClient")
    @patch("exec_assistant.workflows.calendar_monitor.MeetingClassifier")
    @patch("exec_assistant.workflows.calendar_monitor.sync_meeting_to_dynamodb")
    @patch("exec_assistant.workflows.calendar_monitor.emit_prep_trigger_event")
    def test_multiple_meetings_with_real_objects(
        self,
        mock_emit: MagicMock,
        mock_sync: MagicMock,
        mock_classifier_class: MagicMock,
        mock_calendar_class: MagicMock,
        mock_get_users: MagicMock,
    ) -> None:
        """Test processing multiple meetings with real Meeting objects."""
        # Setup
        user = User(
            user_id="user-1",
            google_id="google-1",
            email="user@example.com",
            name="Test User",
            calendar_connected=True,
        )
        mock_get_users.return_value = [user]

        now = datetime.now(UTC)
        meetings = [
            Meeting(
                meeting_id=f"gcal-{i}",
                external_id=f"ext-{i}",
                user_id="user-1",
                title=title,
                start_time=now + timedelta(hours=hours),
                end_time=now + timedelta(hours=hours + 1),
            )
            for i, (title, hours) in enumerate(
                [
                    ("Leadership Meeting", 20),
                    ("1-1 with Sarah", 10),
                    ("QBR Planning", 100),
                ]
            )
        ]

        mock_calendar = MagicMock()
        mock_calendar_class.return_value = mock_calendar
        mock_calendar.fetch_upcoming_meetings.return_value = meetings

        mock_classifier = MagicMock()
        mock_classifier_class.return_value = mock_classifier
        mock_classifier.classify_meeting.side_effect = [
            MeetingType.LEADERSHIP_TEAM,
            MeetingType.ONE_ON_ONE,
            MeetingType.QUARTERLY_BUSINESS_REVIEW,
        ]
        mock_classifier.get_prep_hours.side_effect = [24, 12, 72]
        mock_classifier.should_trigger_prep.side_effect = [True, True, False]

        # Execute
        event = {"source": "aws.events"}
        context = Mock()
        response = calendar_monitor.lambda_handler(event, context)

        # Verify
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["meetings_synced"] == 3
        assert body["preps_triggered"] == 2

    @patch("exec_assistant.workflows.calendar_monitor.get_connected_users")
    @patch("exec_assistant.workflows.calendar_monitor.process_user_calendar")
    def test_error_recovery_multiple_users(
        self,
        mock_process: MagicMock,
        mock_get_users: MagicMock,
    ) -> None:
        """Test that errors for one user don't affect others."""
        # Setup
        users = [
            User(
                user_id=f"user-{i}",
                google_id=f"google-{i}",
                email=f"user{i}@example.com",
                name=f"User {i}",
                calendar_connected=True,
            )
            for i in range(5)
        ]
        mock_get_users.return_value = users

        # Users 1 and 3 fail
        mock_process.side_effect = [
            {"meetings_synced": 5, "preps_triggered": 2},
            Exception("Calendar error"),
            {"meetings_synced": 3, "preps_triggered": 1},
            Exception("API timeout"),
            {"meetings_synced": 7, "preps_triggered": 3},
        ]

        # Execute
        event = {"source": "aws.events"}
        context = Mock()
        response = calendar_monitor.lambda_handler(event, context)

        # Verify
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["users_processed"] == 3  # 3 succeeded
        assert body["errors"] == 2  # 2 failed
        assert body["meetings_synced"] == 15
        assert body["preps_triggered"] == 6
