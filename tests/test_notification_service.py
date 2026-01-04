"""Unit tests for multi-channel notification service.

This module tests the notification service with mocked external API calls
for Slack, Twilio SMS, and AWS SES email delivery.
"""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest
from botocore.exceptions import ClientError

from exec_assistant.shared.models import Meeting, MeetingType, NotificationChannel, User
from exec_assistant.shared.notification_service import (
    NotificationResult,
    NotificationService,
    NotificationStatus,
)


class TestNotificationStatus:
    """Tests for NotificationStatus enum."""

    def test_status_values(self) -> None:
        """Test notification status enum values."""
        assert NotificationStatus.SUCCESS.value == "success"
        assert NotificationStatus.FAILED.value == "failed"
        assert NotificationStatus.PARTIAL.value == "partial"


class TestNotificationResult:
    """Tests for NotificationResult model."""

    def test_result_creation(self) -> None:
        """Test creating a notification result."""
        result = NotificationResult(
            status=NotificationStatus.SUCCESS,
            delivered_channels=[NotificationChannel.SLACK],
            failed_channels={},
            message_id="ts_123456",
        )

        assert result.status == NotificationStatus.SUCCESS
        assert NotificationChannel.SLACK in result.delivered_channels
        assert len(result.failed_channels) == 0
        assert result.message_id == "ts_123456"

    def test_result_to_dict(self) -> None:
        """Test converting result to dictionary."""
        result = NotificationResult(
            status=NotificationStatus.PARTIAL,
            delivered_channels=[NotificationChannel.SLACK],
            failed_channels={NotificationChannel.SMS: "Phone number missing"},
            message_id="ts_123456",
        )

        result_dict = result.to_dict()

        assert result_dict["status"] == "partial"
        assert result_dict["delivered_channels"] == ["slack"]
        assert result_dict["failed_channels"] == {"sms": "Phone number missing"}
        assert result_dict["message_id"] == "ts_123456"

    def test_result_with_multiple_failures(self) -> None:
        """Test result with multiple channel failures."""
        result = NotificationResult(
            status=NotificationStatus.FAILED,
            delivered_channels=[],
            failed_channels={
                NotificationChannel.SLACK: "API token invalid",
                NotificationChannel.SMS: "Phone number missing",
                NotificationChannel.EMAIL: "SES quota exceeded",
            },
            message_id=None,
        )

        assert result.status == NotificationStatus.FAILED
        assert len(result.delivered_channels) == 0
        assert len(result.failed_channels) == 3


class TestNotificationServiceInitialization:
    """Tests for NotificationService initialization."""

    def test_init_with_all_credentials(self) -> None:
        """Test initialization with all credentials provided."""
        service = NotificationService(
            slack_bot_token="xoxb-test",
            twilio_account_sid="AC123",
            twilio_auth_token="token123",
            twilio_from_number="+12345678901",
            ses_from_email="test@example.com",
            aws_region="us-east-1",
        )

        assert service.slack_enabled is True
        assert service.twilio_enabled is True
        assert service.ses_enabled is True

    def test_init_with_only_slack(self) -> None:
        """Test initialization with only Slack credentials."""
        service = NotificationService(
            slack_bot_token="xoxb-test",
        )

        assert service.slack_enabled is True
        assert service.twilio_enabled is False
        assert service.ses_enabled is False

    def test_init_with_environment_variables(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test initialization from environment variables."""
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-env-test")
        monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC456")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "token456")
        monkeypatch.setenv("TWILIO_FROM_NUMBER", "+19876543210")

        service = NotificationService()

        assert service.slack_enabled is True
        assert service.twilio_enabled is True
        assert service.slack_bot_token == "xoxb-env-test"

    def test_init_without_credentials(self) -> None:
        """Test initialization without any credentials."""
        service = NotificationService()

        assert service.slack_enabled is False
        assert service.twilio_enabled is False
        assert service.ses_enabled is False

    @patch("boto3.client")
    def test_ses_client_created_when_enabled(self, mock_boto_client: Mock) -> None:
        """Test that SES client is created when SES is enabled."""
        service = NotificationService(
            ses_from_email="test@example.com",
            aws_region="us-west-2",
        )

        assert service.ses_enabled is True
        mock_boto_client.assert_called_once_with("ses", region_name="us-west-2")

    def test_ses_client_not_created_when_disabled(self) -> None:
        """Test that SES client is not created when SES is disabled."""
        service = NotificationService()

        assert service.ses_enabled is False
        assert service.ses_client is None


class TestChannelEnabled:
    """Tests for _is_channel_enabled method."""

    def test_slack_enabled(self) -> None:
        """Test checking if Slack channel is enabled."""
        service = NotificationService(slack_bot_token="xoxb-test")

        assert service._is_channel_enabled(NotificationChannel.SLACK) is True
        assert service._is_channel_enabled(NotificationChannel.SMS) is False
        assert service._is_channel_enabled(NotificationChannel.EMAIL) is False

    def test_sms_enabled(self) -> None:
        """Test checking if SMS channel is enabled."""
        service = NotificationService(
            twilio_account_sid="AC123",
            twilio_auth_token="token123",
            twilio_from_number="+12345678901",
        )

        assert service._is_channel_enabled(NotificationChannel.SLACK) is False
        assert service._is_channel_enabled(NotificationChannel.SMS) is True
        assert service._is_channel_enabled(NotificationChannel.EMAIL) is False

    def test_email_enabled(self) -> None:
        """Test checking if Email channel is enabled."""
        service = NotificationService(ses_from_email="test@example.com")

        assert service._is_channel_enabled(NotificationChannel.SLACK) is False
        assert service._is_channel_enabled(NotificationChannel.SMS) is False
        assert service._is_channel_enabled(NotificationChannel.EMAIL) is True


class TestSendPrepNotification:
    """Tests for send_prep_notification method."""

    @pytest.fixture
    def sample_meeting(self) -> Meeting:
        """Create a sample meeting for testing."""
        start_time = datetime.now(UTC) + timedelta(days=1)
        end_time = start_time + timedelta(hours=1)

        return Meeting(
            meeting_id="mtg-123",
            user_id="U12345",
            title="Leadership Team Sync",
            start_time=start_time,
            end_time=end_time,
            meeting_type=MeetingType.LEADERSHIP_TEAM,
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

    def test_send_notification_no_channels_available(
        self,
        sample_meeting: Meeting,
        sample_user: User,
    ) -> None:
        """Test sending notification when no channels are available."""
        service = NotificationService()  # No credentials

        with pytest.raises(ValueError, match="No notification channels available"):
            service.send_prep_notification(sample_meeting, sample_user)

    @patch("requests.post")
    def test_send_notification_slack_success(
        self,
        mock_post: Mock,
        sample_meeting: Meeting,
        sample_user: User,
    ) -> None:
        """Test successful Slack notification."""
        # Mock Slack API response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "ok": True,
            "ts": "1234567890.123456",
        }
        mock_post.return_value = mock_response

        service = NotificationService(slack_bot_token="xoxb-test")
        result = service.send_prep_notification(sample_meeting, sample_user)

        # Verify result
        assert result.status == NotificationStatus.SUCCESS
        assert NotificationChannel.SLACK in result.delivered_channels
        assert len(result.failed_channels) == 0
        assert result.message_id == "1234567890.123456"

        # Verify API call
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args.kwargs["json"]["channel"] == "U12345"
        assert "Meeting Prep Reminder" in str(call_args.kwargs["json"]["blocks"])

    @patch("requests.post")
    def test_send_notification_slack_api_error(
        self,
        mock_post: Mock,
        sample_meeting: Meeting,
        sample_user: User,
    ) -> None:
        """Test Slack API error with fallback to SMS."""
        # Mock Slack API error
        mock_slack_response = MagicMock()
        mock_slack_response.json.return_value = {
            "ok": False,
            "error": "channel_not_found",
        }

        # Mock Twilio success
        mock_twilio_response = MagicMock()
        mock_twilio_response.status_code = 200
        mock_twilio_response.json.return_value = {"sid": "SM123456"}

        # First call returns Slack error, second call returns Twilio success
        mock_post.side_effect = [mock_slack_response, mock_twilio_response]

        service = NotificationService(
            slack_bot_token="xoxb-test",
            twilio_account_sid="AC123",
            twilio_auth_token="token123",
            twilio_from_number="+19876543210",
        )

        result = service.send_prep_notification(sample_meeting, sample_user)

        # Verify fallback to SMS
        assert result.status == NotificationStatus.SUCCESS
        assert NotificationChannel.SMS in result.delivered_channels
        assert NotificationChannel.SLACK in result.failed_channels
        assert "channel_not_found" in result.failed_channels[NotificationChannel.SLACK]

    @patch("requests.post")
    def test_send_notification_sms_success(
        self,
        mock_post: Mock,
        sample_meeting: Meeting,
        sample_user: User,
    ) -> None:
        """Test successful SMS notification."""
        # Mock Twilio API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"sid": "SM123456789"}
        mock_post.return_value = mock_response

        service = NotificationService(
            twilio_account_sid="AC123",
            twilio_auth_token="token123",
            twilio_from_number="+19876543210",
        )

        result = service.send_prep_notification(
            sample_meeting,
            sample_user,
            channels=[NotificationChannel.SMS],
        )

        # Verify result
        assert result.status == NotificationStatus.SUCCESS
        assert NotificationChannel.SMS in result.delivered_channels
        assert result.message_id == "SM123456789"

        # Verify API call
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args.kwargs["data"]["To"] == "+12345678901"
        assert call_args.kwargs["data"]["From"] == "+19876543210"
        assert "Meeting prep reminder" in call_args.kwargs["data"]["Body"]

    @patch("requests.post")
    def test_send_notification_sms_no_phone_number(
        self,
        mock_post: Mock,
        sample_meeting: Meeting,
    ) -> None:
        """Test SMS notification when user has no phone number."""
        user_no_phone = User(
            user_id="U12345",
            google_id="google-123",
            email="user@example.com",
            name="Test User",
            phone_number=None,  # No phone number
        )

        service = NotificationService(
            twilio_account_sid="AC123",
            twilio_auth_token="token123",
            twilio_from_number="+19876543210",
        )

        result = service.send_prep_notification(
            sample_meeting,
            user_no_phone,
            channels=[NotificationChannel.SMS],
        )

        # Should fail due to missing phone number
        assert result.status == NotificationStatus.FAILED
        assert len(result.delivered_channels) == 0
        assert NotificationChannel.SMS in result.failed_channels

    @patch("requests.post")
    def test_send_notification_sms_api_error(
        self,
        mock_post: Mock,
        sample_meeting: Meeting,
        sample_user: User,
    ) -> None:
        """Test SMS API error."""
        # Mock Twilio API error
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Invalid phone number"
        mock_post.return_value = mock_response

        service = NotificationService(
            twilio_account_sid="AC123",
            twilio_auth_token="token123",
            twilio_from_number="+19876543210",
        )

        result = service.send_prep_notification(
            sample_meeting,
            sample_user,
            channels=[NotificationChannel.SMS],
        )

        # Should fail
        assert result.status == NotificationStatus.FAILED
        assert NotificationChannel.SMS in result.failed_channels

    def test_send_notification_email_success(
        self,
        sample_meeting: Meeting,
        sample_user: User,
    ) -> None:
        """Test successful email notification."""
        # Mock SES client
        mock_ses = MagicMock()
        mock_ses.send_email.return_value = {"MessageId": "msg-123456"}

        service = NotificationService(ses_from_email="noreply@example.com")
        service.ses_client = mock_ses

        result = service.send_prep_notification(
            sample_meeting,
            sample_user,
            channels=[NotificationChannel.EMAIL],
        )

        # Verify result
        assert result.status == NotificationStatus.SUCCESS
        assert NotificationChannel.EMAIL in result.delivered_channels
        assert result.message_id == "msg-123456"

        # Verify API call
        mock_ses.send_email.assert_called_once()
        call_args = mock_ses.send_email.call_args
        assert call_args.kwargs["Source"] == "noreply@example.com"
        assert call_args.kwargs["Destination"]["ToAddresses"] == ["user@example.com"]
        assert "Meeting Prep" in call_args.kwargs["Message"]["Subject"]["Data"]

    def test_send_notification_email_ses_error(
        self,
        sample_meeting: Meeting,
        sample_user: User,
    ) -> None:
        """Test email notification with SES error."""
        # Mock SES client error
        mock_ses = MagicMock()
        mock_ses.send_email.side_effect = ClientError(
            {"Error": {"Code": "MessageRejected", "Message": "Email address not verified"}},
            "SendEmail",
        )

        service = NotificationService(ses_from_email="noreply@example.com")
        service.ses_client = mock_ses

        result = service.send_prep_notification(
            sample_meeting,
            sample_user,
            channels=[NotificationChannel.EMAIL],
        )

        # Should fail
        assert result.status == NotificationStatus.FAILED
        assert NotificationChannel.EMAIL in result.failed_channels
        assert "MessageRejected" in result.failed_channels[NotificationChannel.EMAIL]

    @patch("requests.post")
    def test_send_notification_all_channels_fail(
        self,
        mock_post: Mock,
        sample_meeting: Meeting,
        sample_user: User,
    ) -> None:
        """Test when all notification channels fail."""
        # Mock all APIs to fail
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": False, "error": "api_error"}
        mock_response.status_code = 500
        mock_response.text = "Server error"
        mock_post.return_value = mock_response

        mock_ses = MagicMock()
        mock_ses.send_email.side_effect = ClientError(
            {"Error": {"Code": "ServiceUnavailable", "Message": "Service unavailable"}},
            "SendEmail",
        )

        service = NotificationService(
            slack_bot_token="xoxb-test",
            twilio_account_sid="AC123",
            twilio_auth_token="token123",
            twilio_from_number="+19876543210",
            ses_from_email="noreply@example.com",
        )
        service.ses_client = mock_ses

        result = service.send_prep_notification(sample_meeting, sample_user)

        # All channels should fail
        assert result.status == NotificationStatus.FAILED
        assert len(result.delivered_channels) == 0
        assert len(result.failed_channels) == 3
        assert result.message_id is None

    @patch("requests.post")
    def test_send_notification_custom_channel_order(
        self,
        mock_post: Mock,
        sample_meeting: Meeting,
        sample_user: User,
    ) -> None:
        """Test notification with custom channel priority order."""
        # Mock SMS success
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"sid": "SM123"}
        mock_post.return_value = mock_response

        service = NotificationService(
            slack_bot_token="xoxb-test",
            twilio_account_sid="AC123",
            twilio_auth_token="token123",
            twilio_from_number="+19876543210",
        )

        # Specify SMS first (skip Slack)
        result = service.send_prep_notification(
            sample_meeting,
            sample_user,
            channels=[NotificationChannel.SMS, NotificationChannel.SLACK],
        )

        # Should use SMS (first in list)
        assert result.status == NotificationStatus.SUCCESS
        assert NotificationChannel.SMS in result.delivered_channels
        assert NotificationChannel.SLACK not in result.delivered_channels


class TestSlackNotificationContent:
    """Tests for Slack notification message formatting."""

    @pytest.fixture
    def sample_meeting(self) -> Meeting:
        """Create a sample meeting for testing."""
        start_time = datetime(2026, 1, 15, 14, 0, tzinfo=UTC)
        end_time = datetime(2026, 1, 15, 15, 30, tzinfo=UTC)

        return Meeting(
            meeting_id="mtg-123",
            user_id="U12345",
            title="Q1 Planning Session",
            start_time=start_time,
            end_time=end_time,
            meeting_type=MeetingType.QUARTERLY_BUSINESS_REVIEW,
            attendees=["ceo@example.com", "cto@example.com", "cfo@example.com"],
        )

    @pytest.fixture
    def sample_user(self) -> User:
        """Create a sample user for testing."""
        return User(
            user_id="U12345",
            google_id="google-123",
            email="user@example.com",
            name="Test User",
        )

    @patch("requests.post")
    def test_slack_message_contains_meeting_details(
        self,
        mock_post: Mock,
        sample_meeting: Meeting,
        sample_user: User,
    ) -> None:
        """Test that Slack message contains all meeting details."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True, "ts": "123.456"}
        mock_post.return_value = mock_response

        service = NotificationService(slack_bot_token="xoxb-test")
        service.send_prep_notification(sample_meeting, sample_user)

        # Verify message content
        call_args = mock_post.call_args
        message_json = call_args.kwargs["json"]

        # Check blocks contain key information
        blocks_str = json.dumps(message_json["blocks"])
        assert "Q1 Planning Session" in blocks_str
        assert "Qbr" in blocks_str or "QBR" in blocks_str.upper()
        assert "3 attendee" in blocks_str

    @patch("requests.post")
    def test_slack_message_has_interactive_buttons(
        self,
        mock_post: Mock,
        sample_meeting: Meeting,
        sample_user: User,
    ) -> None:
        """Test that Slack message includes interactive buttons."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True, "ts": "123.456"}
        mock_post.return_value = mock_response

        service = NotificationService(slack_bot_token="xoxb-test")
        service.send_prep_notification(sample_meeting, sample_user)

        # Verify buttons are present
        call_args = mock_post.call_args
        message_json = call_args.kwargs["json"]

        # Find actions block
        actions_block = None
        for block in message_json["blocks"]:
            if block.get("type") == "actions":
                actions_block = block
                break

        assert actions_block is not None
        assert len(actions_block["elements"]) == 2

        # Check button action IDs
        action_ids = [el["action_id"] for el in actions_block["elements"]]
        assert "start_prep" in action_ids
        assert "remind_later" in action_ids

    @patch("requests.post")
    def test_slack_button_values_contain_meeting_data(
        self,
        mock_post: Mock,
        sample_meeting: Meeting,
        sample_user: User,
    ) -> None:
        """Test that button values contain meeting and user IDs."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True, "ts": "123.456"}
        mock_post.return_value = mock_response

        service = NotificationService(slack_bot_token="xoxb-test")
        service.send_prep_notification(sample_meeting, sample_user)

        # Verify button values
        call_args = mock_post.call_args
        message_json = call_args.kwargs["json"]

        actions_block = next(
            block for block in message_json["blocks"] if block.get("type") == "actions"
        )

        for element in actions_block["elements"]:
            value_data = json.loads(element["value"])
            assert value_data["meeting_id"] == "mtg-123"
            assert value_data["user_id"] == "U12345"


class TestSMSNotificationContent:
    """Tests for SMS notification message formatting."""

    @pytest.fixture
    def sample_meeting(self) -> Meeting:
        """Create a sample meeting for testing."""
        start_time = datetime(2026, 1, 15, 14, 0, tzinfo=UTC)
        end_time = datetime(2026, 1, 15, 15, 0, tzinfo=UTC)

        return Meeting(
            meeting_id="mtg-123",
            user_id="U12345",
            title="Weekly Sync",
            start_time=start_time,
            end_time=end_time,
            meeting_type=MeetingType.ONE_ON_ONE,
            attendees=["manager@example.com"],
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

    @patch("requests.post")
    def test_sms_message_format(
        self,
        mock_post: Mock,
        sample_meeting: Meeting,
        sample_user: User,
    ) -> None:
        """Test SMS message formatting."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"sid": "SM123"}
        mock_post.return_value = mock_response

        service = NotificationService(
            twilio_account_sid="AC123",
            twilio_auth_token="token123",
            twilio_from_number="+19876543210",
        )

        service.send_prep_notification(
            sample_meeting,
            sample_user,
            channels=[NotificationChannel.SMS],
        )

        # Verify message content
        call_args = mock_post.call_args
        message_body = call_args.kwargs["data"]["Body"]

        assert "Meeting prep reminder" in message_body
        assert "Weekly Sync" in message_body
        assert "Jan 15" in message_body


class TestEmailNotificationContent:
    """Tests for email notification content formatting."""

    @pytest.fixture
    def sample_meeting(self) -> Meeting:
        """Create a sample meeting for testing."""
        start_time = datetime(2026, 1, 15, 14, 0, tzinfo=UTC)
        end_time = datetime(2026, 1, 15, 16, 0, tzinfo=UTC)

        return Meeting(
            meeting_id="mtg-123",
            user_id="U12345",
            title="Infrastructure Review",
            start_time=start_time,
            end_time=end_time,
            meeting_type=MeetingType.RELIABILITY_REVIEW,
            attendees=[
                "sre1@example.com",
                "sre2@example.com",
                "manager@example.com",
            ],
        )

    @pytest.fixture
    def sample_user(self) -> User:
        """Create a sample user for testing."""
        return User(
            user_id="U12345",
            google_id="google-123",
            email="user@example.com",
            name="Test User",
        )

    def test_email_subject_line(
        self,
        sample_meeting: Meeting,
        sample_user: User,
    ) -> None:
        """Test email subject line formatting."""
        mock_ses = MagicMock()
        mock_ses.send_email.return_value = {"MessageId": "msg-123"}

        service = NotificationService(ses_from_email="noreply@example.com")
        service.ses_client = mock_ses

        service.send_prep_notification(
            sample_meeting,
            sample_user,
            channels=[NotificationChannel.EMAIL],
        )

        # Verify subject
        call_args = mock_ses.send_email.call_args
        subject = call_args.kwargs["Message"]["Subject"]["Data"]

        assert "Meeting Prep" in subject
        assert "Infrastructure Review" in subject

    def test_email_html_body_content(
        self,
        sample_meeting: Meeting,
        sample_user: User,
    ) -> None:
        """Test email HTML body contains all details."""
        mock_ses = MagicMock()
        mock_ses.send_email.return_value = {"MessageId": "msg-123"}

        service = NotificationService(ses_from_email="noreply@example.com")
        service.ses_client = mock_ses

        service.send_prep_notification(
            sample_meeting,
            sample_user,
            channels=[NotificationChannel.EMAIL],
        )

        # Verify HTML body
        call_args = mock_ses.send_email.call_args
        html_body = call_args.kwargs["Message"]["Body"]["Html"]["Data"]

        assert "Infrastructure Review" in html_body
        assert "Reliability Review" in html_body
        assert "120 minutes" in html_body  # 2 hour meeting
        assert "3 attendee" in html_body

    def test_email_text_body_content(
        self,
        sample_meeting: Meeting,
        sample_user: User,
    ) -> None:
        """Test email plain text body as fallback."""
        mock_ses = MagicMock()
        mock_ses.send_email.return_value = {"MessageId": "msg-123"}

        service = NotificationService(ses_from_email="noreply@example.com")
        service.ses_client = mock_ses

        service.send_prep_notification(
            sample_meeting,
            sample_user,
            channels=[NotificationChannel.EMAIL],
        )

        # Verify text body
        call_args = mock_ses.send_email.call_args
        text_body = call_args.kwargs["Message"]["Body"]["Text"]["Data"]

        assert "Infrastructure Review" in text_body
        assert "Reliability Review" in text_body
        assert "120 minutes" in text_body


class TestNotificationServiceEdgeCases:
    """Tests for edge cases and error scenarios."""

    @pytest.fixture
    def sample_meeting(self) -> Meeting:
        """Create a sample meeting for testing."""
        start_time = datetime.now(UTC) + timedelta(days=1)
        end_time = start_time + timedelta(hours=1)

        return Meeting(
            meeting_id="mtg-123",
            user_id="U12345",
            title="Test Meeting",
            start_time=start_time,
            end_time=end_time,
            meeting_type=MeetingType.UNKNOWN,
            attendees=[],
        )

    @pytest.fixture
    def sample_user(self) -> User:
        """Create a sample user for testing."""
        return User(
            user_id="U12345",
            google_id="google-123",
            email="user@example.com",
            name="Test User",
        )

    @patch("requests.post")
    def test_network_timeout_handling(
        self,
        mock_post: Mock,
        sample_meeting: Meeting,
        sample_user: User,
    ) -> None:
        """Test handling of network timeout errors."""
        import requests

        # Simulate timeout
        mock_post.side_effect = requests.Timeout("Connection timed out")

        service = NotificationService(slack_bot_token="xoxb-test")

        result = service.send_prep_notification(sample_meeting, sample_user)

        # Should fail gracefully
        assert result.status == NotificationStatus.FAILED
        assert NotificationChannel.SLACK in result.failed_channels

    @patch("requests.post")
    def test_connection_error_handling(
        self,
        mock_post: Mock,
        sample_meeting: Meeting,
        sample_user: User,
    ) -> None:
        """Test handling of connection errors."""
        import requests

        # Simulate connection error
        mock_post.side_effect = requests.ConnectionError("Network unreachable")

        service = NotificationService(slack_bot_token="xoxb-test")

        result = service.send_prep_notification(sample_meeting, sample_user)

        # Should fail gracefully
        assert result.status == NotificationStatus.FAILED
        assert NotificationChannel.SLACK in result.failed_channels

    def test_meeting_with_empty_attendees(
        self,
        sample_user: User,
    ) -> None:
        """Test notification for meeting with no attendees."""
        meeting_no_attendees = Meeting(
            meeting_id="mtg-123",
            user_id="U12345",
            title="Solo Work Time",
            start_time=datetime.now(UTC) + timedelta(days=1),
            end_time=datetime.now(UTC) + timedelta(days=1, hours=1),
            meeting_type=MeetingType.UNKNOWN,
            attendees=[],  # Empty attendees
        )

        mock_ses = MagicMock()
        mock_ses.send_email.return_value = {"MessageId": "msg-123"}

        service = NotificationService(ses_from_email="noreply@example.com")
        service.ses_client = mock_ses

        # Should not crash with empty attendees
        result = service.send_prep_notification(
            meeting_no_attendees,
            sample_user,
            channels=[NotificationChannel.EMAIL],
        )

        assert result.status == NotificationStatus.SUCCESS

    def test_meeting_with_long_title(
        self,
        sample_user: User,
    ) -> None:
        """Test notification with very long meeting title."""
        long_title = "A" * 500  # Very long title

        meeting_long_title = Meeting(
            meeting_id="mtg-123",
            user_id="U12345",
            title=long_title,
            start_time=datetime.now(UTC) + timedelta(days=1),
            end_time=datetime.now(UTC) + timedelta(days=1, hours=1),
            meeting_type=MeetingType.UNKNOWN,
            attendees=["user@example.com"],
        )

        mock_ses = MagicMock()
        mock_ses.send_email.return_value = {"MessageId": "msg-123"}

        service = NotificationService(ses_from_email="noreply@example.com")
        service.ses_client = mock_ses

        # Should handle long title without errors
        result = service.send_prep_notification(
            meeting_long_title,
            sample_user,
            channels=[NotificationChannel.EMAIL],
        )

        assert result.status == NotificationStatus.SUCCESS
