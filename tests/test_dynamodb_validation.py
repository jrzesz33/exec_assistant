"""DynamoDB validation tests.

Tests to ensure all models properly handle DynamoDB constraints:
- No empty strings in index keys (primary or secondary)
- Proper handling of None/null values
- Correct data type conversions

These tests use moto to mock DynamoDB operations locally.
"""

from datetime import UTC, datetime, timedelta

import pytest
from moto import mock_aws

from exec_assistant.shared.models import (
    ActionItem,
    ChatSession,
    ChatSessionState,
    Meeting,
    MeetingStatus,
    MeetingType,
    User,
)


@pytest.fixture
def chat_sessions_table():
    """Create a mocked DynamoDB chat sessions table with MeetingIndex."""
    with mock_aws():
        import boto3

        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

        # Create table matching infrastructure/storage.py schema
        table = dynamodb.create_table(
            TableName="test-chat-sessions",
            KeySchema=[
                {"AttributeName": "session_id", "KeyType": "HASH"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "session_id", "AttributeType": "S"},
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "meeting_id", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "UserIndex",
                    "KeySchema": [{"AttributeName": "user_id", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": "MeetingIndex",
                    "KeySchema": [{"AttributeName": "meeting_id", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        yield table


@pytest.fixture
def meetings_table():
    """Create a mocked DynamoDB meetings table."""
    with mock_aws():
        import boto3

        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

        table = dynamodb.create_table(
            TableName="test-meetings",
            KeySchema=[
                {"AttributeName": "meeting_id", "KeyType": "HASH"},
                {"AttributeName": "user_id", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "meeting_id", "AttributeType": "S"},
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "start_time", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "UserStartTimeIndex",
                    "KeySchema": [
                        {"AttributeName": "user_id", "KeyType": "HASH"},
                        {"AttributeName": "start_time", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        yield table


@pytest.fixture
def action_items_table():
    """Create a mocked DynamoDB action items table."""
    with mock_aws():
        import boto3

        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

        table = dynamodb.create_table(
            TableName="test-action-items",
            KeySchema=[
                {"AttributeName": "action_id", "KeyType": "HASH"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "action_id", "AttributeType": "S"},
                {"AttributeName": "meeting_id", "AttributeType": "S"},
                {"AttributeName": "owner", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "MeetingIndex",
                    "KeySchema": [{"AttributeName": "meeting_id", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": "OwnerIndex",
                    "KeySchema": [{"AttributeName": "owner", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        yield table


class TestChatSessionDynamoDB:
    """Tests for ChatSession DynamoDB serialization."""

    def test_chat_session_with_meeting_id(self, chat_sessions_table):
        """Test ChatSession with a valid meeting_id can be stored."""
        session = ChatSession(
            session_id="test-session-1",
            user_id="U123456",
            meeting_id="meeting-123",
            state=ChatSessionState.ACTIVE,
            expires_at=datetime.now(UTC) + timedelta(hours=2),
        )

        # Convert to DynamoDB format
        item = session.to_dynamodb()

        # Verify meeting_id is present
        assert "meeting_id" in item
        assert item["meeting_id"] == "meeting-123"

        # Should successfully put item
        chat_sessions_table.put_item(Item=item)

        # Verify we can retrieve it
        response = chat_sessions_table.get_item(Key={"session_id": "test-session-1"})
        assert "Item" in response
        assert response["Item"]["meeting_id"] == "meeting-123"

    def test_chat_session_without_meeting_id(self, chat_sessions_table):
        """Test ChatSession without meeting_id (general chat) omits field."""
        session = ChatSession(
            session_id="test-session-2",
            user_id="U123456",
            meeting_id=None,
            state=ChatSessionState.ACTIVE,
            expires_at=datetime.now(UTC) + timedelta(hours=2),
        )

        # Convert to DynamoDB format
        item = session.to_dynamodb()

        # Verify meeting_id is NOT present (omitted, not empty string)
        assert "meeting_id" not in item

        # Should successfully put item without validation error
        chat_sessions_table.put_item(Item=item)

        # Verify we can retrieve it
        response = chat_sessions_table.get_item(Key={"session_id": "test-session-2"})
        assert "Item" in response
        assert "meeting_id" not in response["Item"]

    def test_chat_session_with_empty_string_meeting_id(self, chat_sessions_table):
        """Test ChatSession with empty string meeting_id is omitted."""
        # Create session with meeting_id=""
        session = ChatSession(
            session_id="test-session-3",
            user_id="U123456",
            meeting_id="",
            state=ChatSessionState.ACTIVE,
            expires_at=datetime.now(UTC) + timedelta(hours=2),
        )

        # Convert to DynamoDB format
        item = session.to_dynamodb()

        # Verify empty string is omitted
        assert "meeting_id" not in item

        # Should successfully put item
        chat_sessions_table.put_item(Item=item)

    def test_chat_session_from_dynamodb_without_meeting_id(self):
        """Test loading ChatSession from DynamoDB item without meeting_id."""
        item = {
            "session_id": "test-session-4",
            "user_id": "U123456",
            # No meeting_id field
            "state": "active",
            "messages": [],
            "context": {},
            "prep_responses": {},
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }

        # Should load successfully with meeting_id=None
        session = ChatSession.from_dynamodb(item)
        assert session.meeting_id is None

    def test_chat_session_with_messages(self, chat_sessions_table):
        """Test ChatSession with messages serializes correctly."""
        session = ChatSession(
            session_id="test-session-5",
            user_id="U123456",
            meeting_id="meeting-123",
            state=ChatSessionState.ACTIVE,
            expires_at=datetime.now(UTC) + timedelta(hours=2),
        )

        # Add messages
        session.add_message("user", "Hello")
        session.add_message("assistant", "Hi there!")

        # Convert to DynamoDB
        item = session.to_dynamodb()

        # Verify messages are serialized
        assert len(item["messages"]) == 2
        assert item["messages"][0]["role"] == "user"
        assert item["messages"][0]["content"] == "Hello"
        assert "timestamp" in item["messages"][0]

        # Should store successfully
        chat_sessions_table.put_item(Item=item)


class TestMeetingDynamoDB:
    """Tests for Meeting DynamoDB serialization."""

    def test_meeting_basic_serialization(self, meetings_table):
        """Test Meeting can be stored in DynamoDB."""
        now = datetime.now(UTC)
        meeting = Meeting(
            meeting_id="meeting-1",
            user_id="U123456",
            title="Team Sync",
            start_time=now + timedelta(hours=24),
            end_time=now + timedelta(hours=25),
            meeting_type=MeetingType.LEADERSHIP_TEAM,
            status=MeetingStatus.DISCOVERED,
        )

        # Convert to DynamoDB
        item = meeting.to_dynamodb()

        # Verify datetime fields are ISO strings
        assert isinstance(item["start_time"], str)
        assert isinstance(item["end_time"], str)

        # Should store successfully
        meetings_table.put_item(Item=item)

    def test_meeting_with_optional_fields(self, meetings_table):
        """Test Meeting with optional fields handles None correctly."""
        now = datetime.now(UTC)
        meeting = Meeting(
            meeting_id="meeting-2",
            user_id="U123456",
            title="1-1 with Alice",
            start_time=now + timedelta(hours=24),
            end_time=now + timedelta(hours=25),
            description=None,  # Optional
            location=None,  # Optional
            organizer=None,  # Optional
            chat_session_id=None,  # Optional
        )

        # Convert to DynamoDB
        item = meeting.to_dynamodb()

        # Should store successfully with None values
        meetings_table.put_item(Item=item)

        # Verify retrieval
        response = meetings_table.get_item(Key={"meeting_id": "meeting-2", "user_id": "U123456"})
        assert "Item" in response

    def test_meeting_from_dynamodb_roundtrip(self):
        """Test Meeting can be serialized and deserialized."""
        now = datetime.now(UTC)
        original = Meeting(
            meeting_id="meeting-3",
            user_id="U123456",
            title="QBR",
            start_time=now + timedelta(days=7),
            end_time=now + timedelta(days=7, hours=2),
            meeting_type=MeetingType.QUARTERLY_BUSINESS_REVIEW,
            status=MeetingStatus.PREP_COMPLETED,
            prep_hours_before=48,
        )

        # Serialize and deserialize
        item = original.to_dynamodb()
        # Ensure datetime strings are properly formatted with timezone
        restored = Meeting.from_dynamodb(item)

        # Verify key fields match
        assert restored.meeting_id == original.meeting_id
        assert restored.title == original.title
        assert restored.meeting_type == original.meeting_type
        assert restored.prep_hours_before == original.prep_hours_before
        # Verify datetimes are close (within 1 second to account for serialization)
        assert abs((restored.start_time - original.start_time).total_seconds()) < 1
        assert abs((restored.end_time - original.end_time).total_seconds()) < 1


class TestActionItemDynamoDB:
    """Tests for ActionItem DynamoDB serialization."""

    def test_action_item_with_owner(self, action_items_table):
        """Test ActionItem with owner can be stored."""
        now = datetime.now(UTC)
        action = ActionItem(
            action_id="action-1",
            meeting_id="meeting-1",
            description="Update documentation",
            owner="alice@example.com",
            due_date=now + timedelta(days=7),
        )

        # Convert to DynamoDB
        item = action.to_dynamodb()

        # Verify owner is present
        assert "owner" in item
        assert item["owner"] == "alice@example.com"

        # Should store successfully
        action_items_table.put_item(Item=item)

    def test_action_item_without_owner(self, action_items_table):
        """Test ActionItem without owner handles None correctly."""
        action = ActionItem(
            action_id="action-2",
            meeting_id="meeting-1",
            description="Review proposal",
            owner=None,  # No owner assigned yet
        )

        # Convert to DynamoDB
        item = action.to_dynamodb()

        # Should store successfully
        action_items_table.put_item(Item=item)

    def test_action_item_with_empty_string_owner_omits_field(self, action_items_table):
        """Test that empty string owner is omitted from DynamoDB item.

        Note: ActionItem.owner is Optional[str], but DynamoDB does not allow
        empty strings or null values in GSI keys. The model omits the owner
        field entirely when it's empty or None to avoid ValidationException.
        """
        action = ActionItem(
            action_id="action-3",
            meeting_id="meeting-1",
            description="Test task",
            owner="",  # Empty string
        )

        item = action.to_dynamodb()

        # Empty string should be omitted to avoid GSI constraint violation
        assert "owner" not in item

        # Should store successfully without validation error
        action_items_table.put_item(Item=item)


class TestUserDynamoDB:
    """Tests for User DynamoDB serialization."""

    def test_user_basic_serialization(self):
        """Test User can be serialized to DynamoDB format."""
        user = User(
            user_id="user-1",
            google_id="google-123",
            email="alice@example.com",
            name="Alice Smith",
        )

        # Convert to DynamoDB
        item = user.to_dynamodb()

        # Verify required fields
        assert item["user_id"] == "user-1"
        assert item["google_id"] == "google-123"
        assert item["email"] == "alice@example.com"

        # Verify datetime fields are ISO strings
        assert isinstance(item["created_at"], str)
        assert isinstance(item["last_login_at"], str)

    def test_user_with_calendar_connection(self):
        """Test User with calendar connection serializes correctly."""
        user = User(
            user_id="user-2",
            google_id="google-456",
            email="bob@example.com",
            name="Bob Jones",
        )

        # Connect calendar
        user.connect_calendar("encrypted-refresh-token-here")

        # Convert to DynamoDB
        item = user.to_dynamodb()

        # Verify calendar fields
        assert item["calendar_connected"] is True
        assert item["calendar_refresh_token"] == "encrypted-refresh-token-here"
        assert "calendar_last_sync" in item


class TestDynamoDBConstraints:
    """Tests for general DynamoDB constraints."""

    def test_no_empty_strings_in_required_fields(self):
        """Verify all models avoid empty strings in required fields."""
        # ChatSession with empty meeting_id should omit field
        session = ChatSession(
            session_id="s1",
            user_id="U1",
            meeting_id="",
        )
        item = session.to_dynamodb()
        assert "meeting_id" not in item

        # Meeting with empty strings in optional fields should work
        # (but we should use None instead)
        now = datetime.now(UTC)
        meeting = Meeting(
            meeting_id="m1",
            user_id="U1",
            title="Test",
            start_time=now + timedelta(hours=1),
            end_time=now + timedelta(hours=2),
            description=None,  # Correct: use None
            location=None,  # Correct: use None
        )
        item = meeting.to_dynamodb()
        # None values should be present but null
        assert item.get("description") is None
        assert item.get("location") is None

    def test_datetime_serialization_is_consistent(self):
        """Verify all datetime fields are serialized to ISO format strings."""
        now = datetime.now(UTC)

        # ChatSession
        session = ChatSession(
            session_id="s1",
            user_id="U1",
            expires_at=now + timedelta(hours=2),
        )
        item = session.to_dynamodb()
        assert isinstance(item["created_at"], str)
        assert isinstance(item["updated_at"], str)
        assert isinstance(item["expires_at"], str)

        # Meeting
        meeting = Meeting(
            meeting_id="m1",
            user_id="U1",
            title="Test",
            start_time=now + timedelta(hours=1),
            end_time=now + timedelta(hours=2),
        )
        item = meeting.to_dynamodb()
        assert isinstance(item["start_time"], str)
        assert isinstance(item["end_time"], str)
        assert isinstance(item["created_at"], str)

    def test_roundtrip_preserves_data(self):
        """Verify serialization and deserialization preserves data integrity."""
        now = datetime.now(UTC)

        # Create ChatSession with various field types
        original = ChatSession(
            session_id="s1",
            user_id="U123",
            meeting_id="m1",
            state=ChatSessionState.ACTIVE,
            context={"budget_variance": 5000, "incidents": ["INC-123"]},
            prep_responses={"q1": "answer1", "q2": "answer2"},
            expires_at=now + timedelta(hours=2),
        )
        original.add_message("user", "Hello")
        original.add_message("assistant", "Hi there")

        # Roundtrip
        item = original.to_dynamodb()
        restored = ChatSession.from_dynamodb(item)

        # Verify critical fields
        assert restored.session_id == original.session_id
        assert restored.user_id == original.user_id
        assert restored.meeting_id == original.meeting_id
        assert restored.state == original.state
        assert len(restored.messages) == 2
        assert restored.messages[0].content == "Hello"
        assert restored.context == original.context
        assert restored.prep_responses == original.prep_responses
