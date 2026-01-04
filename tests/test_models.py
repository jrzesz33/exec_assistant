"""Unit tests for data models."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from exec_assistant.shared.models import (
    ActionItem,
    ChatMessage,
    ChatSession,
    ChatSessionState,
    Meeting,
    MeetingMaterials,
    MeetingStatus,
    MeetingType,
    User,
)


class TestMeeting:
    """Tests for Meeting model."""

    def test_create_meeting_minimal(self) -> None:
        """Test creating a meeting with minimal required fields."""
        meeting = Meeting(
            meeting_id="meeting-123",
            user_id="U12345",
            title="Leadership Team Sync",
            start_time=datetime(2025, 1, 15, 14, 0, tzinfo=UTC),
            end_time=datetime(2025, 1, 15, 15, 0, tzinfo=UTC),
        )
        assert meeting.meeting_id == "meeting-123"
        assert meeting.user_id == "U12345"
        assert meeting.title == "Leadership Team Sync"
        assert meeting.meeting_type == MeetingType.UNKNOWN
        assert meeting.status == MeetingStatus.DISCOVERED
        assert meeting.attendees == []

    def test_create_meeting_full(self) -> None:
        """Test creating a meeting with all fields."""
        meeting = Meeting(
            meeting_id="meeting-456",
            user_id="U67890",
            title="Q1 Business Review",
            description="Quarterly review of infrastructure metrics",
            start_time=datetime(2025, 4, 1, 10, 0, tzinfo=UTC),
            end_time=datetime(2025, 4, 1, 12, 0, tzinfo=UTC),
            location="https://zoom.us/j/123456789",
            attendees=["cio@company.com", "vp-infra@company.com"],
            organizer="assistant@company.com",
            meeting_type=MeetingType.QUARTERLY_BUSINESS_REVIEW,
            status=MeetingStatus.CLASSIFIED,
            prep_hours_before=48,
        )
        assert meeting.meeting_type == MeetingType.QUARTERLY_BUSINESS_REVIEW
        assert len(meeting.attendees) == 2
        assert meeting.prep_hours_before == 48

    def test_meeting_requires_timezone_aware_datetimes(self) -> None:
        """Test that meeting requires timezone-aware datetimes."""
        with pytest.raises(ValidationError, match="Datetime must be timezone-aware"):
            Meeting(
                meeting_id="meeting-789",
                user_id="U11111",
                title="Test Meeting",
                start_time=datetime(2025, 1, 1, 10, 0),  # No timezone!
                end_time=datetime(2025, 1, 1, 11, 0, tzinfo=UTC),
            )

    def test_meeting_to_dynamodb(self) -> None:
        """Test serializing meeting to DynamoDB format."""
        meeting = Meeting(
            meeting_id="meeting-db",
            user_id="U99999",
            title="Test DB Serialization",
            start_time=datetime(2025, 2, 1, 9, 0, tzinfo=UTC),
            end_time=datetime(2025, 2, 1, 10, 0, tzinfo=UTC),
            meeting_type=MeetingType.ONE_ON_ONE,
        )
        item = meeting.to_dynamodb()

        assert item["meeting_id"] == "meeting-db"
        assert isinstance(item["start_time"], str)
        assert item["start_time"] == "2025-02-01T09:00:00+00:00"
        assert item["meeting_type"] == "one_on_one"

    def test_meeting_with_notification_fields(self) -> None:
        """Test meeting with notification tracking fields."""
        notification_time = datetime(2025, 2, 1, 8, 0, tzinfo=UTC)
        meeting = Meeting(
            meeting_id="meeting-notif",
            user_id="U12345",
            title="Meeting with Notification",
            start_time=datetime(2025, 2, 1, 14, 0, tzinfo=UTC),
            end_time=datetime(2025, 2, 1, 15, 0, tzinfo=UTC),
            notification_id="ts_1234567890.123456",
            notification_sent_at=notification_time,
        )

        assert meeting.notification_id == "ts_1234567890.123456"
        assert meeting.notification_sent_at == notification_time

    def test_meeting_notification_fields_to_dynamodb(self) -> None:
        """Test that notification fields serialize to DynamoDB correctly."""
        notification_time = datetime(2025, 2, 1, 8, 0, tzinfo=UTC)
        meeting = Meeting(
            meeting_id="meeting-notif-db",
            user_id="U12345",
            title="Test Notification Serialization",
            start_time=datetime(2025, 2, 1, 14, 0, tzinfo=UTC),
            end_time=datetime(2025, 2, 1, 15, 0, tzinfo=UTC),
            notification_id="ts_9876543210.654321",
            notification_sent_at=notification_time,
        )

        item = meeting.to_dynamodb()

        assert item["notification_id"] == "ts_9876543210.654321"
        assert isinstance(item["notification_sent_at"], str)
        assert item["notification_sent_at"] == "2025-02-01T08:00:00+00:00"

    def test_meeting_notification_fields_from_dynamodb(self) -> None:
        """Test that notification fields deserialize from DynamoDB correctly."""
        item = {
            "meeting_id": "meeting-notif-restore",
            "user_id": "U67890",
            "title": "Restored Meeting with Notification",
            "start_time": "2025-03-01T14:00:00+00:00",
            "end_time": "2025-03-01T15:00:00+00:00",
            "meeting_type": "one_on_one",
            "status": "prep_scheduled",
            "notification_id": "SM123456789",
            "notification_sent_at": "2025-03-01T08:00:00+00:00",
            "attendees": [],
            "created_at": "2025-02-28T10:00:00+00:00",
            "updated_at": "2025-03-01T08:00:00+00:00",
        }

        meeting = Meeting.from_dynamodb(item)

        assert meeting.notification_id == "SM123456789"
        assert isinstance(meeting.notification_sent_at, datetime)
        assert meeting.notification_sent_at.tzinfo is not None
        assert meeting.notification_sent_at == datetime(2025, 3, 1, 8, 0, tzinfo=UTC)

    def test_meeting_from_dynamodb(self) -> None:
        """Test deserializing meeting from DynamoDB format."""
        item = {
            "meeting_id": "meeting-restore",
            "user_id": "U88888",
            "title": "Restored Meeting",
            "start_time": "2025-03-01T14:00:00+00:00",
            "end_time": "2025-03-01T15:00:00+00:00",
            "meeting_type": "leadership_team",
            "status": "classified",
            "attendees": ["leader@company.com"],
            "created_at": "2025-01-01T00:00:00+00:00",
            "updated_at": "2025-01-01T00:00:00+00:00",
        }
        meeting = Meeting.from_dynamodb(item)

        assert meeting.meeting_id == "meeting-restore"
        assert isinstance(meeting.start_time, datetime)
        assert meeting.start_time.tzinfo is not None
        assert meeting.meeting_type == MeetingType.LEADERSHIP_TEAM
        assert meeting.status == MeetingStatus.CLASSIFIED


class TestChatMessage:
    """Tests for ChatMessage model."""

    def test_create_user_message(self) -> None:
        """Test creating a user message."""
        msg = ChatMessage(role="user", content="What should I discuss in this meeting?")
        assert msg.role == "user"
        assert msg.content == "What should I discuss in this meeting?"
        assert isinstance(msg.timestamp, datetime)

    def test_create_assistant_message(self) -> None:
        """Test creating an assistant message."""
        msg = ChatMessage(role="assistant", content="Let me help you prepare.")
        assert msg.role == "assistant"

    def test_invalid_role_raises_error(self) -> None:
        """Test that invalid role raises ValidationError."""
        with pytest.raises(ValidationError, match="Role must be"):
            ChatMessage(role="invalid", content="Test")


class TestChatSession:
    """Tests for ChatSession model."""

    def test_create_chat_session(self) -> None:
        """Test creating a chat session."""
        session = ChatSession(
            session_id="session-123",
            user_id="U12345",
            meeting_id="meeting-456",
        )
        assert session.session_id == "session-123"
        assert session.state == ChatSessionState.CREATED
        assert len(session.messages) == 0
        assert session.context == {}
        assert session.prep_responses == {}

    def test_add_message_to_session(self) -> None:
        """Test adding messages to a session."""
        session = ChatSession(
            session_id="session-789",
            user_id="U99999",
            meeting_id="meeting-999",
        )
        initial_updated = session.updated_at

        session.add_message("user", "Hello")
        assert len(session.messages) == 1
        assert session.messages[0].role == "user"
        assert session.messages[0].content == "Hello"
        assert session.updated_at > initial_updated

        session.add_message("assistant", "Hi there!")
        assert len(session.messages) == 2

    def test_chat_session_to_dynamodb(self) -> None:
        """Test serializing chat session to DynamoDB."""
        session = ChatSession(
            session_id="session-db",
            user_id="U11111",
            meeting_id="meeting-222",
        )
        session.add_message("user", "Test message")
        session.context = {"budget_variance": 0.15}
        session.prep_responses = {"key_topics": "infrastructure costs"}

        item = session.to_dynamodb()
        assert item["session_id"] == "session-db"
        assert isinstance(item["created_at"], str)
        assert len(item["messages"]) == 1
        assert item["messages"][0]["role"] == "user"
        assert isinstance(item["messages"][0]["timestamp"], str)
        assert item["context"]["budget_variance"] == 0.15

    def test_chat_session_from_dynamodb(self) -> None:
        """Test deserializing chat session from DynamoDB."""
        item = {
            "session_id": "session-restore",
            "user_id": "U22222",
            "meeting_id": "meeting-333",
            "state": "active",
            "messages": [
                {
                    "role": "user",
                    "content": "Hello",
                    "timestamp": "2025-01-15T10:00:00+00:00",
                }
            ],
            "context": {"incidents": 3},
            "prep_responses": {},
            "created_at": "2025-01-15T09:00:00+00:00",
            "updated_at": "2025-01-15T10:00:00+00:00",
        }
        session = ChatSession.from_dynamodb(item)

        assert session.session_id == "session-restore"
        assert session.state == ChatSessionState.ACTIVE
        assert len(session.messages) == 1
        assert isinstance(session.messages[0], ChatMessage)
        assert session.messages[0].content == "Hello"
        assert session.context["incidents"] == 3


class TestMeetingMaterials:
    """Tests for MeetingMaterials model."""

    def test_create_meeting_materials(self) -> None:
        """Test creating meeting materials."""
        materials = MeetingMaterials(
            meeting_id="meeting-123",
            session_id="session-456",
            agenda="1. Review Q1 metrics\n2. Discuss hiring\n3. Budget update",
            question_bank=["What is our current cloud spend?", "Any new incidents?"],
            note_template="# Meeting Notes\n\n## Attendees\n\n## Discussion\n",
        )
        assert materials.meeting_id == "meeting-123"
        assert len(materials.question_bank) == 2
        assert "Review Q1 metrics" in materials.agenda

    def test_materials_to_html(self) -> None:
        """Test rendering materials as HTML."""
        materials = MeetingMaterials(
            meeting_id="meeting-html",
            session_id="session-html",
            agenda="Test agenda",
            question_bank=["Question 1", "Question 2"],
            context_summary="Budget variance: 15%",
            note_template="# Notes",
        )
        html = materials.to_html()

        assert "<!DOCTYPE html>" in html
        assert "Test agenda" in html
        assert "Question 1" in html
        assert "Budget variance: 15%" in html

    def test_materials_to_markdown(self) -> None:
        """Test rendering materials as Markdown."""
        materials = MeetingMaterials(
            meeting_id="meeting-md",
            session_id="session-md",
            agenda="Test agenda",
            question_bank=["Question 1"],
            note_template="# Notes",
        )
        md = materials.to_markdown()

        assert "# Meeting Preparation Materials" in md
        assert "Test agenda" in md
        assert "- Question 1" in md
        assert "```" in md


class TestActionItem:
    """Tests for ActionItem model."""

    def test_create_action_item(self) -> None:
        """Test creating an action item."""
        action = ActionItem(
            action_id=str(uuid4()),
            meeting_id="meeting-123",
            description="Review and approve Q2 budget",
            owner="vp-infra@company.com",
            due_date=datetime(2025, 3, 1, 23, 59, tzinfo=UTC),
        )
        assert action.description == "Review and approve Q2 budget"
        assert action.owner == "vp-infra@company.com"
        assert not action.completed
        assert action.completed_at is None

    def test_action_item_to_dynamodb(self) -> None:
        """Test serializing action item to DynamoDB."""
        action = ActionItem(
            action_id="action-123",
            meeting_id="meeting-456",
            description="Follow up on incident metrics",
            owner="U12345",
            due_date=datetime(2025, 2, 15, 17, 0, tzinfo=UTC),
            completed=True,
            completed_at=datetime(2025, 2, 14, 10, 0, tzinfo=UTC),
        )
        item = action.to_dynamodb()

        assert item["action_id"] == "action-123"
        assert isinstance(item["due_date"], str)
        assert isinstance(item["completed_at"], str)
        assert item["completed"] is True

    def test_action_item_from_dynamodb(self) -> None:
        """Test deserializing action item from DynamoDB."""
        item = {
            "action_id": "action-restore",
            "meeting_id": "meeting-789",
            "description": "Test action",
            "owner": "U99999",
            "due_date": "2025-04-01T17:00:00+00:00",
            "completed": False,
            "created_at": "2025-01-15T10:00:00+00:00",
            "updated_at": "2025-01-15T10:00:00+00:00",
        }
        action = ActionItem.from_dynamodb(item)

        assert action.action_id == "action-restore"
        assert isinstance(action.due_date, datetime)
        assert action.due_date.tzinfo is not None
        assert not action.completed


class TestUser:
    """Tests for User model."""

    def test_create_user_minimal(self) -> None:
        """Test creating a user with minimal required fields."""
        user = User(
            user_id="user-123",
            google_id="google-abc",
            email="test@example.com",
            name="Test User",
        )
        assert user.user_id == "user-123"
        assert user.google_id == "google-abc"
        assert user.email == "test@example.com"
        assert user.name == "Test User"
        assert user.calendar_connected is False
        assert user.timezone == "America/New_York"

    def test_create_user_full(self) -> None:
        """Test creating a user with all fields."""
        user = User(
            user_id="user-456",
            google_id="google-xyz",
            email="admin@company.com",
            name="Admin User",
            picture_url="https://example.com/picture.jpg",
            calendar_connected=True,
            calendar_refresh_token="encrypted_token",
            timezone="America/Los_Angeles",
            notification_preferences={
                "prep_reminders": True,
                "meeting_updates": False,
                "daily_summary": True,
            },
        )
        assert user.calendar_connected is True
        assert user.timezone == "America/Los_Angeles"
        assert user.notification_preferences["daily_summary"] is True

    def test_email_validation(self) -> None:
        """Test email validation."""
        # Valid email should work
        user = User(
            user_id="user-1",
            google_id="google-1",
            email="valid@example.com",
            name="User",
        )
        assert user.email == "valid@example.com"

        # Email should be lowercased
        user2 = User(
            user_id="user-2",
            google_id="google-2",
            email="UPPER@EXAMPLE.COM",
            name="User",
        )
        assert user2.email == "upper@example.com"

        # Invalid email should raise error
        with pytest.raises(ValidationError):
            User(
                user_id="user-3",
                google_id="google-3",
                email="invalid-email",
                name="User",
            )

    def test_update_last_login(self) -> None:
        """Test updating last login timestamp."""
        user = User(
            user_id="user-789",
            google_id="google-789",
            email="user@example.com",
            name="Test User",
        )
        initial_login = user.last_login_at
        initial_updated = user.updated_at

        # Small delay to ensure timestamp changes
        import time

        time.sleep(0.01)

        user.update_last_login()

        assert user.last_login_at > initial_login
        assert user.updated_at > initial_updated

    def test_connect_calendar(self) -> None:
        """Test connecting Google Calendar."""
        user = User(
            user_id="user-cal",
            google_id="google-cal",
            email="calendar@example.com",
            name="Calendar User",
        )
        assert user.calendar_connected is False
        assert user.calendar_refresh_token is None

        user.connect_calendar("encrypted_refresh_token")

        assert user.calendar_connected is True
        assert user.calendar_refresh_token == "encrypted_refresh_token"
        assert user.calendar_last_sync is not None

    def test_disconnect_calendar(self) -> None:
        """Test disconnecting Google Calendar."""
        user = User(
            user_id="user-disco",
            google_id="google-disco",
            email="disconnect@example.com",
            name="Disconnect User",
            calendar_connected=True,
            calendar_refresh_token="token",
        )

        user.disconnect_calendar()

        assert user.calendar_connected is False
        assert user.calendar_refresh_token is None
        assert user.calendar_last_sync is None

    def test_user_to_dynamodb(self) -> None:
        """Test serializing user to DynamoDB."""
        user = User(
            user_id="user-db",
            google_id="google-db",
            email="db@example.com",
            name="DB User",
            calendar_connected=True,
        )
        item = user.to_dynamodb()

        assert item["user_id"] == "user-db"
        assert item["google_id"] == "google-db"
        assert item["email"] == "db@example.com"
        assert isinstance(item["created_at"], str)
        assert isinstance(item["last_login_at"], str)

    def test_user_from_dynamodb(self) -> None:
        """Test deserializing user from DynamoDB."""
        item = {
            "user_id": "user-restore",
            "google_id": "google-restore",
            "email": "restore@example.com",
            "name": "Restored User",
            "picture_url": "https://example.com/pic.jpg",
            "calendar_connected": True,
            "calendar_refresh_token": "token",
            "calendar_last_sync": "2025-01-15T10:00:00+00:00",
            "timezone": "America/Chicago",
            "notification_preferences": {
                "prep_reminders": False,
                "meeting_updates": True,
                "daily_summary": False,
            },
            "created_at": "2025-01-01T00:00:00+00:00",
            "last_login_at": "2025-01-15T09:00:00+00:00",
            "updated_at": "2025-01-15T10:00:00+00:00",
        }
        user = User.from_dynamodb(item)

        assert user.user_id == "user-restore"
        assert user.google_id == "google-restore"
        assert user.email == "restore@example.com"
        assert user.calendar_connected is True
        assert isinstance(user.created_at, datetime)
        assert isinstance(user.last_login_at, datetime)
        assert user.timezone == "America/Chicago"

    def test_user_to_api_response(self) -> None:
        """Test converting user to API response format."""
        user = User(
            user_id="user-api",
            google_id="google-api",
            email="api@example.com",
            name="API User",
            calendar_refresh_token="sensitive_token",
        )
        api_response = user.to_api_response()

        # Should include public fields
        assert api_response["user_id"] == "user-api"
        assert api_response["email"] == "api@example.com"
        assert api_response["name"] == "API User"
        assert api_response["calendar_connected"] is False

        # Should NOT include sensitive fields
        assert "calendar_refresh_token" not in api_response
        assert "google_id" not in api_response
