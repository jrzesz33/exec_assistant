"""Unit tests for Google Calendar integration.

This module tests:
- OAuth authorization flow
- Token storage and refresh
- Calendar event fetching
- Meeting data conversion
- Error handling and edge cases
"""

import json
import sys
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

# Mock Google API modules before importing calendar module
sys.modules["googleapiclient"] = MagicMock()
sys.modules["googleapiclient.discovery"] = MagicMock()
sys.modules["googleapiclient.errors"] = MagicMock()
sys.modules["google.auth.transport"] = MagicMock()
sys.modules["google.auth.transport.requests"] = MagicMock()
sys.modules["google.oauth2"] = MagicMock()
sys.modules["google.oauth2.credentials"] = MagicMock()
sys.modules["google_auth_oauthlib"] = MagicMock()
sys.modules["google_auth_oauthlib.flow"] = MagicMock()

# Create mock classes
Request = MagicMock


class MockCredentials:
    """Mock Credentials class for testing."""

    def __init__(self, *args, **kwargs):
        self.token = kwargs.get("token")
        self.refresh_token = kwargs.get("refresh_token")
        self.token_uri = kwargs.get("token_uri")
        self.client_id = kwargs.get("client_id")
        self.client_secret = kwargs.get("client_secret")
        self.scopes = kwargs.get("scopes")
        self.expired = False

    def refresh(self, request):
        """Mock refresh method."""
        pass


Credentials = MockCredentials


class MockHttpError(Exception):
    """Mock HttpError for testing."""

    def __init__(self, resp=None, content=b"", uri=None):
        self.resp = resp
        self.content = content
        self.uri = uri
        super().__init__(f"HTTP Error {resp.status if resp else 'Unknown'}")


# Inject MockHttpError into googleapiclient.errors module
sys.modules["googleapiclient.errors"].HttpError = MockHttpError

from exec_assistant.shared.calendar import (
    APIError,
    CalendarClient,
    CalendarError,
    OAuthError,
)


class TestCalendarClientInit:
    """Tests for CalendarClient initialization."""

    def test_init_with_defaults(self) -> None:
        """Test client initialization with default scopes."""
        client = CalendarClient(
            user_id="user-123",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        assert client.user_id == "user-123"
        assert client.client_id == "test-client-id"
        assert client.client_secret == "test-secret"
        assert client.redirect_uri == "https://example.com/callback"
        assert len(client.scopes) == 2
        assert "https://www.googleapis.com/auth/calendar.readonly" in client.scopes

    def test_init_with_custom_scopes(self) -> None:
        """Test client initialization with custom scopes."""
        custom_scopes = ["https://www.googleapis.com/auth/calendar"]
        client = CalendarClient(
            user_id="user-456",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
            scopes=custom_scopes,
        )

        assert client.scopes == custom_scopes

    def test_secrets_manager_initialized(self) -> None:
        """Test that Secrets Manager client is initialized."""
        client = CalendarClient(
            user_id="user-789",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        assert client.secrets_manager is not None


class TestOAuthFlow:
    """Tests for OAuth authorization flow."""

    def test_get_authorization_url_success(self) -> None:
        """Test generating OAuth authorization URL."""
        client = CalendarClient(
            user_id="user-123",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        with patch.object(client, "_create_flow") as mock_create_flow:
            mock_flow = MagicMock()
            mock_flow.authorization_url.return_value = (
                "https://accounts.google.com/o/oauth2/auth?client_id=test",
                "state-123",
            )
            mock_create_flow.return_value = mock_flow

            url = client.get_authorization_url(state="custom-state")

            assert url.startswith("https://accounts.google.com/o/oauth2/auth")
            mock_flow.authorization_url.assert_called_once()
            call_kwargs = mock_flow.authorization_url.call_args[1]
            assert call_kwargs["access_type"] == "offline"
            assert call_kwargs["prompt"] == "consent"
            assert call_kwargs["state"] == "custom-state"

    def test_get_authorization_url_with_default_state(self) -> None:
        """Test generating OAuth URL with default state (user_id)."""
        client = CalendarClient(
            user_id="user-456",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        with patch.object(client, "_create_flow") as mock_create_flow:
            mock_flow = MagicMock()
            mock_flow.authorization_url.return_value = ("https://test.com", "state")
            mock_create_flow.return_value = mock_flow

            client.get_authorization_url()

            call_kwargs = mock_flow.authorization_url.call_args[1]
            assert call_kwargs["state"] == "user-456"

    def test_get_authorization_url_failure(self) -> None:
        """Test OAuth URL generation failure."""
        client = CalendarClient(
            user_id="user-789",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        with patch.object(client, "_create_flow") as mock_create_flow:
            mock_create_flow.side_effect = Exception("OAuth config error")

            with pytest.raises(OAuthError, match="Failed to generate authorization URL"):
                client.get_authorization_url()

    @pytest.mark.asyncio
    async def test_handle_oauth_callback_success(self) -> None:
        """Test successful OAuth callback handling."""
        client = CalendarClient(
            user_id="user-123",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        mock_credentials = MagicMock(spec=Credentials)
        mock_credentials.token = "access-token-123"
        mock_credentials.refresh_token = "refresh-token-123"
        mock_credentials.scopes = client.scopes

        with (
            patch.object(client, "_create_flow") as mock_create_flow,
            patch.object(client, "_save_credentials") as mock_save,
        ):
            mock_flow = MagicMock()
            mock_flow.credentials = mock_credentials
            mock_create_flow.return_value = mock_flow

            result = await client.handle_oauth_callback(code="auth-code-123", state="user-123")

            assert result["status"] == "connected"
            assert result["user_id"] == "user-123"
            assert result["has_refresh_token"] is True
            mock_flow.fetch_token.assert_called_once_with(code="auth-code-123")
            mock_save.assert_called_once_with(mock_credentials)

    @pytest.mark.asyncio
    async def test_handle_oauth_callback_state_mismatch(self) -> None:
        """Test OAuth callback with mismatched state (CSRF protection)."""
        client = CalendarClient(
            user_id="user-123",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        with pytest.raises(OAuthError, match="State mismatch"):
            await client.handle_oauth_callback(code="auth-code", state="wrong-state")

    @pytest.mark.asyncio
    async def test_handle_oauth_callback_token_exchange_failure(self) -> None:
        """Test OAuth callback when token exchange fails."""
        client = CalendarClient(
            user_id="user-123",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        with patch.object(client, "_create_flow") as mock_create_flow:
            mock_flow = MagicMock()
            mock_flow.fetch_token.side_effect = Exception("Invalid authorization code")
            mock_create_flow.return_value = mock_flow

            with pytest.raises(OAuthError, match="OAuth callback failed"):
                await client.handle_oauth_callback(code="invalid-code")


class TestTokenManagement:
    """Tests for token storage and refresh."""

    def test_get_secret_name(self) -> None:
        """Test secret name generation."""
        client = CalendarClient(
            user_id="user-123",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        secret_name = client._get_secret_name()
        assert secret_name == "calendar-tokens-user-123"

    @pytest.mark.asyncio
    async def test_load_credentials_success(self) -> None:
        """Test loading credentials from Secrets Manager."""
        client = CalendarClient(
            user_id="user-123",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        token_data = {
            "token": "access-token-123",
            "refresh_token": "refresh-token-123",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "test-client-id",
            "client_secret": "test-secret",
            "scopes": client.scopes,
        }

        mock_response = {"SecretString": json.dumps(token_data)}

        with (
            patch.object(client.secrets_manager, "get_secret_value", return_value=mock_response),
            patch("exec_assistant.shared.calendar.Credentials", MockCredentials),
        ):
            credentials = await client._load_credentials()

            assert credentials is not None
            assert credentials.token == "access-token-123"
            assert credentials.refresh_token == "refresh-token-123"

    @pytest.mark.asyncio
    async def test_load_credentials_not_found(self) -> None:
        """Test loading credentials when secret doesn't exist."""
        client = CalendarClient(
            user_id="user-456",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        error = ClientError({"Error": {"Code": "ResourceNotFoundException"}}, "GetSecretValue")

        with patch.object(client.secrets_manager, "get_secret_value", side_effect=error):
            credentials = await client._load_credentials()
            assert credentials is None

    @pytest.mark.asyncio
    async def test_load_credentials_unexpected_error(self) -> None:
        """Test loading credentials with unexpected AWS error."""
        client = CalendarClient(
            user_id="user-789",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        error = ClientError({"Error": {"Code": "AccessDeniedException"}}, "GetSecretValue")

        with patch.object(client.secrets_manager, "get_secret_value", side_effect=error):
            with pytest.raises(ClientError):
                await client._load_credentials()

    @pytest.mark.asyncio
    async def test_save_credentials_create_new(self) -> None:
        """Test saving credentials (creating new secret)."""
        client = CalendarClient(
            user_id="user-123",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        mock_credentials = MagicMock(spec=Credentials)
        mock_credentials.token = "access-token"
        mock_credentials.refresh_token = "refresh-token"
        mock_credentials.token_uri = "https://oauth2.googleapis.com/token"
        mock_credentials.client_id = "test-client-id"
        mock_credentials.client_secret = "test-secret"
        mock_credentials.scopes = client.scopes

        with patch.object(client.secrets_manager, "create_secret") as mock_create:
            await client._save_credentials(mock_credentials)

            mock_create.assert_called_once()
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["Name"] == "calendar-tokens-user-123"
            token_data = json.loads(call_kwargs["SecretString"])
            assert token_data["token"] == "access-token"

    @pytest.mark.asyncio
    async def test_save_credentials_update_existing(self) -> None:
        """Test saving credentials (updating existing secret)."""
        client = CalendarClient(
            user_id="user-456",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        mock_credentials = MagicMock(spec=Credentials)
        mock_credentials.token = "new-access-token"
        mock_credentials.refresh_token = "new-refresh-token"
        mock_credentials.token_uri = "https://oauth2.googleapis.com/token"
        mock_credentials.client_id = "test-client-id"
        mock_credentials.client_secret = "test-secret"
        mock_credentials.scopes = client.scopes

        error = ClientError({"Error": {"Code": "ResourceExistsException"}}, "CreateSecret")

        with (
            patch.object(client.secrets_manager, "create_secret", side_effect=error) as mock_create,
            patch.object(client.secrets_manager, "update_secret") as mock_update,
        ):
            await client._save_credentials(mock_credentials)

            mock_create.assert_called_once()
            mock_update.assert_called_once()
            call_kwargs = mock_update.call_args[1]
            token_data = json.loads(call_kwargs["SecretString"])
            assert token_data["token"] == "new-access-token"


class TestCalendarAPI:
    """Tests for Google Calendar API interactions."""

    @pytest.mark.asyncio
    async def test_fetch_upcoming_meetings_no_credentials(self) -> None:
        """Test fetching meetings when user has no credentials."""
        client = CalendarClient(
            user_id="user-123",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        with patch.object(client, "_load_credentials", return_value=None):
            meetings = await client.fetch_upcoming_meetings()
            assert meetings == []

    @pytest.mark.asyncio
    async def test_fetch_upcoming_meetings_success(self) -> None:
        """Test successfully fetching upcoming meetings."""
        client = CalendarClient(
            user_id="user-123",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        mock_credentials = MagicMock(spec=Credentials)
        mock_credentials.expired = False
        mock_credentials.refresh_token = None

        # Mock calendar events
        mock_events = {
            "items": [
                {
                    "id": "event-123",
                    "summary": "Team Sync",
                    "start": {"dateTime": "2025-01-15T14:00:00+00:00"},
                    "end": {"dateTime": "2025-01-15T15:00:00+00:00"},
                    "attendees": [{"email": "user1@example.com"}],
                    "organizer": {"email": "organizer@example.com"},
                },
            ]
        }

        with (
            patch.object(client, "_load_credentials", return_value=mock_credentials),
            patch("exec_assistant.shared.calendar.build") as mock_build,
        ):
            mock_service = MagicMock()
            mock_events_api = MagicMock()
            mock_list = MagicMock()
            mock_list.execute.return_value = mock_events

            mock_events_api.list.return_value = mock_list
            mock_service.events.return_value = mock_events_api
            mock_build.return_value = mock_service

            meetings = await client.fetch_upcoming_meetings(days_ahead=7)

            assert len(meetings) == 1
            assert meetings[0].title == "Team Sync"
            assert meetings[0].meeting_id == "gcal-event-123"
            assert meetings[0].user_id == "user-123"
            assert meetings[0].source == "google_calendar"
            assert len(meetings[0].attendees) == 1

    @pytest.mark.asyncio
    async def test_fetch_upcoming_meetings_with_expired_token(self) -> None:
        """Test fetching meetings with expired token (auto-refresh)."""
        client = CalendarClient(
            user_id="user-123",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        mock_credentials = MockCredentials(
            token="access-token",
            refresh_token="refresh-token-123",
            token_uri="https://oauth2.googleapis.com/token",
            client_id="test-client-id",
            client_secret="test-secret",
            scopes=client.scopes,
        )
        mock_credentials.expired = True

        with (
            patch.object(client, "_load_credentials", return_value=mock_credentials),
            patch.object(client, "_save_credentials") as mock_save,
            patch("exec_assistant.shared.calendar.build") as mock_build,
            patch.object(mock_credentials, "refresh") as mock_refresh,
        ):
            mock_service = MagicMock()
            mock_events_api = MagicMock()
            mock_list = MagicMock()
            mock_list.execute.return_value = {"items": []}

            mock_events_api.list.return_value = mock_list
            mock_service.events.return_value = mock_events_api
            mock_build.return_value = mock_service

            await client.fetch_upcoming_meetings()

            # Verify token was refreshed
            mock_refresh.assert_called_once()
            mock_save.assert_called_once_with(mock_credentials)

    @pytest.mark.asyncio
    async def test_fetch_upcoming_meetings_refresh_failure(self) -> None:
        """Test handling token refresh failure."""
        client = CalendarClient(
            user_id="user-123",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        mock_credentials = MockCredentials(
            token="access-token",
            refresh_token="invalid-refresh-token",
            token_uri="https://oauth2.googleapis.com/token",
            client_id="test-client-id",
            client_secret="test-secret",
            scopes=client.scopes,
        )
        mock_credentials.expired = True

        with (
            patch.object(client, "_load_credentials", return_value=mock_credentials),
            patch.object(
                mock_credentials, "refresh", side_effect=Exception("Invalid refresh token")
            ),pytest.raises(APIError, match="Failed to refresh credentials")
        ):
            await client.fetch_upcoming_meetings()

    @pytest.mark.asyncio
    async def test_fetch_upcoming_meetings_api_error(self) -> None:
        """Test handling Calendar API errors."""
        client = CalendarClient(
            user_id="user-123",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        mock_credentials = MagicMock(spec=Credentials)
        mock_credentials.expired = False

        with (
            patch.object(client, "_load_credentials", return_value=mock_credentials),
            patch("exec_assistant.shared.calendar.build") as mock_build,
        ):
            mock_service = MagicMock()
            mock_response = MagicMock()
            mock_response.status = 403
            http_error = MockHttpError(resp=mock_response, content=b"Forbidden")

            mock_service.events.return_value.list.return_value.execute.side_effect = http_error
            mock_build.return_value = mock_service

            with pytest.raises(APIError, match="Calendar API request failed"):
                await client.fetch_upcoming_meetings()

    @pytest.mark.asyncio
    async def test_fetch_upcoming_meetings_with_parameters(self) -> None:
        """Test fetching meetings with custom parameters."""
        client = CalendarClient(
            user_id="user-123",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        mock_credentials = MagicMock(spec=Credentials)
        mock_credentials.expired = False

        with (
            patch.object(client, "_load_credentials", return_value=mock_credentials),
            patch("exec_assistant.shared.calendar.build") as mock_build,
        ):
            mock_service = MagicMock()
            mock_events_api = MagicMock()
            mock_list = MagicMock()
            mock_list.execute.return_value = {"items": []}

            mock_events_api.list.return_value = mock_list
            mock_service.events.return_value = mock_events_api
            mock_build.return_value = mock_service

            await client.fetch_upcoming_meetings(days_ahead=30, days_behind=7, max_results=50)

            # Verify parameters were used
            call_kwargs = mock_events_api.list.call_args[1]
            assert call_kwargs["maxResults"] == 50
            assert call_kwargs["singleEvents"] is True
            assert call_kwargs["orderBy"] == "startTime"

    @pytest.mark.asyncio
    async def test_get_meeting_details_success(self) -> None:
        """Test getting details for a specific meeting."""
        client = CalendarClient(
            user_id="user-123",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        mock_credentials = MagicMock(spec=Credentials)
        mock_credentials.expired = False

        mock_event = {
            "id": "event-456",
            "summary": "QBR Meeting",
            "start": {"dateTime": "2025-04-01T10:00:00+00:00"},
            "end": {"dateTime": "2025-04-01T12:00:00+00:00"},
        }

        with (
            patch.object(client, "_load_credentials", return_value=mock_credentials),
            patch("exec_assistant.shared.calendar.build") as mock_build,
        ):
            mock_service = MagicMock()
            mock_get = MagicMock()
            mock_get.execute.return_value = mock_event

            mock_service.events.return_value.get.return_value = mock_get
            mock_build.return_value = mock_service

            meeting = await client.get_meeting_details("event-456")

            assert meeting is not None
            assert meeting.title == "QBR Meeting"
            assert meeting.external_id == "event-456"

    @pytest.mark.asyncio
    async def test_get_meeting_details_not_found(self) -> None:
        """Test getting details for non-existent meeting."""
        client = CalendarClient(
            user_id="user-123",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        mock_credentials = MagicMock(spec=Credentials)
        mock_credentials.expired = False

        with (
            patch.object(client, "_load_credentials", return_value=mock_credentials),
            patch("exec_assistant.shared.calendar.build") as mock_build,
        ):
            mock_service = MagicMock()
            mock_response = MagicMock()
            mock_response.status = 404
            http_error = MockHttpError(resp=mock_response, content=b"Not Found")

            mock_service.events.return_value.get.return_value.execute.side_effect = http_error
            mock_build.return_value = mock_service

            meeting = await client.get_meeting_details("nonexistent")
            assert meeting is None


class TestDisconnect:
    """Tests for calendar disconnection."""

    @pytest.mark.asyncio
    async def test_disconnect_success(self) -> None:
        """Test successfully disconnecting calendar."""
        client = CalendarClient(
            user_id="user-123",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        with patch.object(client.secrets_manager, "delete_secret") as mock_delete:
            await client.disconnect()

            mock_delete.assert_called_once()
            call_kwargs = mock_delete.call_args[1]
            assert call_kwargs["SecretId"] == "calendar-tokens-user-123"
            assert call_kwargs["ForceDeleteWithoutRecovery"] is True

    @pytest.mark.asyncio
    async def test_disconnect_already_deleted(self) -> None:
        """Test disconnecting when tokens already deleted."""
        client = CalendarClient(
            user_id="user-123",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        error = ClientError({"Error": {"Code": "ResourceNotFoundException"}}, "DeleteSecret")

        with patch.object(client.secrets_manager, "delete_secret", side_effect=error):
            # Should not raise exception
            await client.disconnect()

    @pytest.mark.asyncio
    async def test_disconnect_aws_error(self) -> None:
        """Test disconnecting with AWS error."""
        client = CalendarClient(
            user_id="user-123",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        error = ClientError({"Error": {"Code": "AccessDeniedException"}}, "DeleteSecret")

        with patch.object(client.secrets_manager, "delete_secret", side_effect=error):
            with pytest.raises(ClientError):
                await client.disconnect()


class TestEventConversion:
    """Tests for converting Google Calendar events to Meeting objects."""

    def test_event_to_meeting_basic(self) -> None:
        """Test converting basic event to Meeting."""
        client = CalendarClient(
            user_id="user-123",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        event = {
            "id": "event-123",
            "summary": "Team Standup",
            "start": {"dateTime": "2025-01-15T09:00:00+00:00"},
            "end": {"dateTime": "2025-01-15T09:30:00+00:00"},
        }

        meeting = client._event_to_meeting(event)

        assert meeting is not None
        assert meeting.meeting_id == "gcal-event-123"
        assert meeting.external_id == "event-123"
        assert meeting.title == "Team Standup"
        assert meeting.user_id == "user-123"
        assert meeting.source == "google_calendar"

    def test_event_to_meeting_with_attendees(self) -> None:
        """Test converting event with attendees."""
        client = CalendarClient(
            user_id="user-123",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        event = {
            "id": "event-456",
            "summary": "Leadership Meeting",
            "start": {"dateTime": "2025-01-20T14:00:00+00:00"},
            "end": {"dateTime": "2025-01-20T15:00:00+00:00"},
            "attendees": [
                {"email": "leader1@example.com"},
                {"email": "leader2@example.com"},
            ],
            "organizer": {"email": "ceo@example.com"},
        }

        meeting = client._event_to_meeting(event)

        assert meeting is not None
        assert len(meeting.attendees) == 2
        assert "leader1@example.com" in meeting.attendees
        assert meeting.organizer == "ceo@example.com"

    def test_event_to_meeting_with_google_meet(self) -> None:
        """Test converting event with Google Meet link."""
        client = CalendarClient(
            user_id="user-123",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        event = {
            "id": "event-789",
            "summary": "Remote Meeting",
            "start": {"dateTime": "2025-01-25T16:00:00+00:00"},
            "end": {"dateTime": "2025-01-25T17:00:00+00:00"},
            "location": "Conference Room A",
            "hangoutLink": "https://meet.google.com/abc-defg-hij",
        }

        meeting = client._event_to_meeting(event)

        assert meeting is not None
        # Hangout link should override physical location
        assert meeting.location == "https://meet.google.com/abc-defg-hij"

    def test_event_to_meeting_all_day_event_skipped(self) -> None:
        """Test that all-day events are skipped."""
        client = CalendarClient(
            user_id="user-123",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        event = {
            "id": "event-all-day",
            "summary": "Company Holiday",
            "start": {"date": "2025-07-04"},  # All-day event has 'date' not 'dateTime'
            "end": {"date": "2025-07-05"},
        }

        meeting = client._event_to_meeting(event)
        assert meeting is None

    def test_event_to_meeting_missing_start_time(self) -> None:
        """Test handling event with missing start time."""
        client = CalendarClient(
            user_id="user-123",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        event = {
            "id": "event-invalid",
            "summary": "Invalid Event",
            "start": {},  # No dateTime
            "end": {"dateTime": "2025-01-15T10:00:00+00:00"},
        }

        meeting = client._event_to_meeting(event)
        assert meeting is None

    def test_event_to_meeting_invalid_datetime_format(self) -> None:
        """Test handling event with invalid datetime format."""
        client = CalendarClient(
            user_id="user-123",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        event = {
            "id": "event-bad-time",
            "summary": "Bad Time Event",
            "start": {"dateTime": "not-a-valid-datetime"},
            "end": {"dateTime": "2025-01-15T10:00:00+00:00"},
        }

        meeting = client._event_to_meeting(event)
        assert meeting is None

    def test_event_to_meeting_untitled(self) -> None:
        """Test converting event with no title."""
        client = CalendarClient(
            user_id="user-123",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        event = {
            "id": "event-untitled",
            "start": {"dateTime": "2025-01-15T10:00:00+00:00"},
            "end": {"dateTime": "2025-01-15T11:00:00+00:00"},
            # No 'summary' field
        }

        meeting = client._event_to_meeting(event)

        assert meeting is not None
        assert meeting.title == "Untitled Meeting"

    def test_event_to_meeting_with_description(self) -> None:
        """Test converting event with description."""
        client = CalendarClient(
            user_id="user-123",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        event = {
            "id": "event-with-desc",
            "summary": "Planning Session",
            "description": "Discuss Q2 initiatives and resource allocation",
            "start": {"dateTime": "2025-02-01T10:00:00+00:00"},
            "end": {"dateTime": "2025-02-01T11:00:00+00:00"},
        }

        meeting = client._event_to_meeting(event)

        assert meeting is not None
        assert meeting.description == "Discuss Q2 initiatives and resource allocation"


class TestHelperMethods:
    """Tests for internal helper methods."""

    def test_create_flow(self) -> None:
        """Test creating OAuth flow."""
        client = CalendarClient(
            user_id="user-123",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        flow = client._create_flow()

        assert flow is not None
        assert flow.redirect_uri == "https://example.com/callback"
        # Note: Can't easily verify client_config without inspecting private attributes


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_fetch_meetings_empty_response(self) -> None:
        """Test fetching meetings when calendar is empty."""
        client = CalendarClient(
            user_id="user-123",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        mock_credentials = MagicMock(spec=Credentials)
        mock_credentials.expired = False

        with (
            patch.object(client, "_load_credentials", return_value=mock_credentials),
            patch("exec_assistant.shared.calendar.build") as mock_build,
        ):
            mock_service = MagicMock()
            mock_events_api = MagicMock()
            mock_list = MagicMock()
            # Empty items list
            mock_list.execute.return_value = {"items": []}

            mock_events_api.list.return_value = mock_list
            mock_service.events.return_value = mock_events_api
            mock_build.return_value = mock_service

            meetings = await client.fetch_upcoming_meetings()
            assert meetings == []

    @pytest.mark.asyncio
    async def test_fetch_meetings_no_items_key(self) -> None:
        """Test handling response without 'items' key."""
        client = CalendarClient(
            user_id="user-123",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        mock_credentials = MagicMock(spec=Credentials)
        mock_credentials.expired = False

        with (
            patch.object(client, "_load_credentials", return_value=mock_credentials),
            patch("exec_assistant.shared.calendar.build") as mock_build,
        ):
            mock_service = MagicMock()
            mock_events_api = MagicMock()
            mock_list = MagicMock()
            # Response without 'items' key
            mock_list.execute.return_value = {}

            mock_events_api.list.return_value = mock_list
            mock_service.events.return_value = mock_events_api
            mock_build.return_value = mock_service

            meetings = await client.fetch_upcoming_meetings()
            assert meetings == []

    def test_event_to_meeting_with_missing_end_time(self) -> None:
        """Test converting event with missing end time (defaults to +1 hour)."""
        client = CalendarClient(
            user_id="user-123",
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://example.com/callback",
        )

        event = {
            "id": "event-no-end",
            "summary": "Open-ended Meeting",
            "start": {"dateTime": "2025-01-15T14:00:00+00:00"},
            "end": {},  # No end time
        }

        meeting = client._event_to_meeting(event)

        assert meeting is not None
        # Should default to 1 hour after start
        expected_end = datetime(2025, 1, 15, 15, 0, tzinfo=UTC)
        assert meeting.end_time == expected_end


class TestExceptionHierarchy:
    """Tests for custom exception classes."""

    def test_calendar_error_is_base(self) -> None:
        """Test CalendarError is base exception."""
        assert issubclass(OAuthError, CalendarError)
        assert issubclass(APIError, CalendarError)

    def test_raise_oauth_error(self) -> None:
        """Test raising OAuthError."""
        with pytest.raises(OAuthError):
            raise OAuthError("OAuth failed")

    def test_raise_api_error(self) -> None:
        """Test raising APIError."""
        with pytest.raises(APIError):
            raise APIError("API request failed")

    def test_catch_calendar_error(self) -> None:
        """Test catching base CalendarError."""
        try:
            raise OAuthError("Test error")
        except CalendarError:
            pass  # Should catch successfully
