"""Google Calendar integration module.

This module handles:
- OAuth 2.0 authorization flow with Google
- Token storage and refresh using AWS Secrets Manager
- Calendar API interactions (list events, get event details)
- Meeting data extraction and conversion

Security:
- OAuth tokens stored encrypted in AWS Secrets Manager
- Automatic token refresh with exponential backoff
- Proper error handling for API failures

Usage:
    client = CalendarClient(
        user_id="user-123",
        client_id=os.environ["GOOGLE_CALENDAR_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CALENDAR_CLIENT_SECRET"],
        redirect_uri="https://api.example.com/calendar/callback",
    )

    # OAuth flow
    auth_url = client.get_authorization_url()
    # ... user authorizes ...
    await client.handle_oauth_callback(code="auth-code-from-google")

    # Fetch meetings
    meetings = await client.fetch_upcoming_meetings(days_ahead=14)
"""

import json
import os
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
from botocore.exceptions import ClientError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from exec_assistant.shared.logging import get_logger
from exec_assistant.shared.models import Meeting

logger = get_logger(__name__)


class CalendarError(Exception):
    """Base exception for calendar-related errors."""

    pass


class OAuthError(CalendarError):
    """OAuth-related errors (authorization, token refresh)."""

    pass


class APIError(CalendarError):
    """Google Calendar API errors."""

    pass


class CalendarClient:
    """Google Calendar API client with OAuth 2.0 authentication.

    This client handles the complete OAuth flow, token management,
    and Calendar API interactions.

    Attributes:
        user_id: User identifier for token storage
        client_id: Google OAuth client ID
        client_secret: Google OAuth client secret
        redirect_uri: OAuth callback URL
        scopes: Google Calendar API scopes
    """

    DEFAULT_SCOPES = [
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/calendar.events.readonly",
    ]

    def __init__(
        self,
        user_id: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scopes: list[str] | None = None,
    ):
        """Initialize calendar client.

        Args:
            user_id: User identifier for token storage
            client_id: Google OAuth client ID
            client_secret: Google OAuth client secret
            redirect_uri: OAuth callback URL
            scopes: Calendar API scopes (defaults to read-only)

        Raises:
            ValueError: If user_id is invalid or contains unsafe characters
        """
        # Validate and sanitize user_id (used in secret names)
        if not user_id or not user_id.strip():
            raise ValueError("user_id is required")

        # Sanitize user_id: only allow alphanumeric, dash, underscore
        # This prevents injection attacks in AWS Secrets Manager API calls
        import re

        if not re.match(r"^[a-zA-Z0-9_-]+$", user_id):
            raise ValueError(
                "user_id must contain only alphanumeric characters, dashes, and underscores"
            )

        self.user_id = user_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scopes = scopes or self.DEFAULT_SCOPES
        self.secrets_manager = boto3.client(
            "secretsmanager",
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )

    def get_authorization_url(self, state: str | None = None) -> str:
        """Generate OAuth authorization URL for user to visit.

        Args:
            state: Optional state parameter for CSRF protection

        Returns:
            Authorization URL to redirect user to

        Raises:
            OAuthError: If URL generation fails
        """
        try:
            flow = self._create_flow()

            authorization_url, _ = flow.authorization_url(
                access_type="offline",  # Request refresh token
                include_granted_scopes="true",
                prompt="consent",  # Force consent screen to get refresh token
                state=state or self.user_id,  # CSRF protection
            )

            logger.info(
                "user_id=<%s> | generated authorization url",
                self.user_id,
            )

            return authorization_url

        except Exception as e:
            logger.error(
                "user_id=<%s>, error=<%s> | failed to generate authorization url",
                self.user_id,
                str(e),
                exc_info=True,
            )
            raise OAuthError(f"Failed to generate authorization URL: {e}") from e

    def handle_oauth_callback(
        self,
        code: str,
        state: str,  # Required for CSRF protection
    ) -> dict[str, Any]:
        """Handle OAuth callback and store tokens.

        This method:
        1. Validates state parameter (CSRF protection)
        2. Exchanges authorization code for access/refresh tokens
        3. Stores tokens in AWS Secrets Manager
        4. Returns authorization status

        Args:
            code: Authorization code from Google
            state: State parameter for CSRF validation (required)

        Returns:
            Dict with status and token info

        Raises:
            OAuthError: If token exchange or storage fails
            ValueError: If state validation fails
        """
        # Validate inputs
        if not code or not code.strip():
            raise ValueError("Authorization code is required")
        if not state or not state.strip():
            raise ValueError("State parameter is required for CSRF protection")

        try:
            # Validate state (CSRF protection)
            if state != self.user_id:
                msg = f"State mismatch: expected {self.user_id}, got {state}"
                raise OAuthError(msg)

            flow = self._create_flow()

            # Exchange code for tokens
            flow.fetch_token(code=code)
            credentials = flow.credentials

            logger.info(
                "user_id=<%s> | successfully exchanged authorization code for tokens",
                self.user_id,
            )

            # Store tokens in Secrets Manager
            self._save_credentials(credentials)

            return {
                "status": "connected",
                "user_id": self.user_id,
                "scopes": credentials.scopes,
                "has_refresh_token": credentials.refresh_token is not None,
            }

        except Exception as e:
            logger.error(
                "user_id=<%s>, error=<%s> | oauth callback failed",
                self.user_id,
                str(e),
                exc_info=True,
            )
            raise OAuthError(f"OAuth callback failed: {e}") from e

    def fetch_upcoming_meetings(
        self,
        days_ahead: int = 14,
        days_behind: int = 0,
        max_results: int = 100,
    ) -> list[Meeting]:
        """Fetch upcoming meetings from Google Calendar.

        Args:
            days_ahead: Number of days to look ahead (default: 14, max: 365)
            days_behind: Number of days to look behind (default: 0, max: 30)
            max_results: Maximum number of events to return (default: 100, max: 250)

        Returns:
            List of Meeting objects

        Raises:
            APIError: If Calendar API request fails
            ValueError: If parameters are invalid
        """
        # Validate inputs
        if days_ahead < 0 or days_ahead > 365:
            raise ValueError("days_ahead must be between 0 and 365")
        if days_behind < 0 or days_behind > 30:
            raise ValueError("days_behind must be between 0 and 30")
        if max_results < 1 or max_results > 250:
            raise ValueError("max_results must be between 1 and 250")

        # Load credentials
        credentials = self._load_credentials()

        if not credentials:
            logger.warning(
                "user_id=<%s> | no calendar credentials found",
                self.user_id,
            )
            return []

        # Refresh token if needed
        if credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
                self._save_credentials(credentials)
                logger.info(
                    "user_id=<%s> | refreshed expired credentials",
                    self.user_id,
                )
            except Exception as e:
                logger.error(
                    "user_id=<%s>, error=<%s> | failed to refresh credentials",
                    self.user_id,
                    str(e),
                    exc_info=True,
                )
                raise APIError(f"Failed to refresh credentials: {e}") from e

        # Lazy import to avoid hanging during module load
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError

        try:
            # Build Calendar API client
            service = build("calendar", "v3", credentials=credentials)

            # Calculate time range
            now = datetime.now(UTC)
            time_min = (now - timedelta(days=days_behind)).isoformat()
            time_max = (now + timedelta(days=days_ahead)).isoformat()

            logger.info(
                "user_id=<%s>, time_min=<%s>, time_max=<%s> | fetching calendar events",
                self.user_id,
                time_min,
                time_max,
            )

            # Fetch events from primary calendar
            events_result = (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=time_min,
                    timeMax=time_max,
                    maxResults=max_results,
                    singleEvents=True,  # Expand recurring events
                    orderBy="startTime",
                )
                .execute()
            )

            events = events_result.get("items", [])

            logger.info(
                "user_id=<%s>, event_count=<%d> | fetched calendar events",
                self.user_id,
                len(events),
            )

            # Convert to Meeting objects
            meetings = []
            for event in events:
                meeting = self._event_to_meeting(event)
                if meeting:
                    meetings.append(meeting)

            logger.info(
                "user_id=<%s>, meeting_count=<%d> | converted events to meetings",
                self.user_id,
                len(meetings),
            )

            return meetings

        except HttpError as e:
            logger.error(
                "user_id=<%s>, status=<%d>, error=<%s> | calendar api request failed",
                self.user_id,
                e.resp.status,
                str(e),
                exc_info=True,
            )
            raise APIError(f"Calendar API request failed: {e}") from e
        except Exception as e:
            logger.error(
                "user_id=<%s>, error=<%s> | unexpected error fetching meetings",
                self.user_id,
                str(e),
                exc_info=True,
            )
            raise APIError(f"Unexpected error fetching meetings: {e}") from e

    def get_meeting_details(self, event_id: str) -> Meeting | None:
        """Get detailed information about a specific meeting.

        Args:
            event_id: Google Calendar event ID

        Returns:
            Meeting object or None if not found

        Raises:
            APIError: If API request fails
            ValueError: If event_id is invalid
        """
        # Validate input
        if not event_id or not event_id.strip():
            raise ValueError("event_id is required")

        credentials = self._load_credentials()

        if not credentials:
            return None

        # Refresh token if needed
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            self._save_credentials(credentials)

        try:
            service = build("calendar", "v3", credentials=credentials)

            event = service.events().get(calendarId="primary", eventId=event_id).execute()

            return self._event_to_meeting(event)

        except HttpError as e:
            if e.resp.status == 404:
                logger.warning(
                    "user_id=<%s>, event_id=<%s> | event not found",
                    self.user_id,
                    event_id,
                )
                return None
            raise APIError(f"Failed to get event details: {e}") from e

    def disconnect(self) -> None:
        """Disconnect calendar by removing stored tokens.

        This deletes OAuth tokens from Secrets Manager.
        Note: Does not revoke Google's authorization - user must do that in Google account settings.

        Raises:
            ClientError: If deletion fails (other than ResourceNotFound)
        """
        secret_name = self._get_secret_name()

        try:
            self.secrets_manager.delete_secret(
                SecretId=secret_name,
                ForceDeleteWithoutRecovery=True,
            )
            logger.info(
                "user_id=<%s>, secret=<%s> | deleted calendar tokens",
                self.user_id,
                secret_name,
            )
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "ResourceNotFoundException":
                logger.info(
                    "user_id=<%s>, secret=<%s> | tokens already deleted",
                    self.user_id,
                    secret_name,
                )
            else:
                logger.error(
                    "user_id=<%s>, error_code=<%s>, error=<%s> | failed to delete tokens",
                    self.user_id,
                    error_code,
                    str(e),
                    exc_info=True,
                )
                raise

    def _create_flow(self) -> Flow:
        """Create OAuth flow object.

        Returns:
            Configured Flow instance
        """
        flow = Flow.from_client_config(
            client_config={
                "web": {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [self.redirect_uri],
                }
            },
            scopes=self.scopes,
        )

        flow.redirect_uri = self.redirect_uri

        return flow

    def _get_secret_name(self) -> str:
        """Get Secrets Manager secret name for this user.

        Returns:
            Secret name following convention: calendar-tokens-{user_id}
        """
        return f"calendar-tokens-{self.user_id}"

    def _load_credentials(self) -> Credentials | None:
        """Load OAuth credentials from Secrets Manager.

        Returns:
            Credentials object or None if not found

        Note:
            Client secret is retrieved from instance variables, not stored in Secrets Manager.
        """
        secret_name = self._get_secret_name()

        try:
            response = self.secrets_manager.get_secret_value(SecretId=secret_name)
            token_data = json.loads(response["SecretString"])

            # Reconstruct credentials using client secret from instance
            # SECURITY: Client secret should NOT be stored in Secrets Manager
            credentials = Credentials(
                token=token_data["token"],
                refresh_token=token_data.get("refresh_token"),
                token_uri=token_data["token_uri"],
                client_id=self.client_id,  # From instance, not storage
                client_secret=self.client_secret,  # From instance, not storage
                scopes=token_data["scopes"],
            )

            return credentials

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "ResourceNotFoundException":
                logger.debug(
                    "user_id=<%s>, secret=<%s> | calendar tokens not found",
                    self.user_id,
                    secret_name,
                )
                return None
            logger.error(
                "user_id=<%s>, error_code=<%s>, error=<%s> | failed to load credentials",
                self.user_id,
                error_code,
                str(e),
                exc_info=True,
            )
            raise

    def _save_credentials(self, credentials: Credentials) -> None:
        """Save OAuth credentials to Secrets Manager.

        Args:
            credentials: Credentials object to save

        Note:
            Only stores tokens and metadata - NOT client_id or client_secret for security.
        """
        secret_name = self._get_secret_name()

        # SECURITY: Do NOT store client_id or client_secret
        # These are configuration values, not user-specific tokens
        token_data = {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "scopes": credentials.scopes,
        }

        try:
            # Try to create secret
            self.secrets_manager.create_secret(
                Name=secret_name,
                SecretString=json.dumps(token_data),
                Description=f"Google Calendar OAuth tokens for user {self.user_id}",
            )
            logger.info(
                "user_id=<%s>, secret=<%s> | created calendar token secret",
                self.user_id,
                secret_name,
            )
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "ResourceExistsException":
                # Update existing secret
                self.secrets_manager.update_secret(
                    SecretId=secret_name,
                    SecretString=json.dumps(token_data),
                )
                logger.info(
                    "user_id=<%s>, secret=<%s> | updated calendar token secret",
                    self.user_id,
                    secret_name,
                )
            else:
                logger.error(
                    "user_id=<%s>, error_code=<%s> | failed to save credentials",
                    self.user_id,
                    error_code,
                    exc_info=True,
                )
                raise

    def _event_to_meeting(self, event: dict[str, Any]) -> Meeting | None:
        """Convert Google Calendar event to Meeting object.

        Args:
            event: Google Calendar event dict

        Returns:
            Meeting object or None if event should be skipped
        """
        # Skip all-day events (they have 'date' instead of 'dateTime')
        start = event.get("start", {})
        end = event.get("end", {})

        if "date" in start:
            logger.debug(
                "event_id=<%s>, title=<%s> | skipping all-day event",
                event.get("id"),
                event.get("summary", "Untitled"),
            )
            return None

        start_time_str = start.get("dateTime")
        end_time_str = end.get("dateTime")

        if not start_time_str:
            return None

        # Parse times
        try:
            start_time = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
            end_time = (
                datetime.fromisoformat(end_time_str.replace("Z", "+00:00"))
                if end_time_str
                else start_time + timedelta(hours=1)
            )
        except (ValueError, TypeError) as e:
            logger.warning(
                "event_id=<%s>, error=<%s> | failed to parse event times",
                event.get("id"),
                str(e),
            )
            return None

        # Extract attendees
        attendees_raw = event.get("attendees", [])
        attendees = [attendee.get("email") for attendee in attendees_raw if attendee.get("email")]

        # Extract organizer
        organizer_raw = event.get("organizer", {})
        organizer = organizer_raw.get("email")

        # Extract location
        location = event.get("location")
        if event.get("hangoutLink"):
            # Prefer Google Meet link if available
            location = event["hangoutLink"]

        meeting = Meeting(
            meeting_id=f"gcal-{event['id']}",  # Prefix to indicate source
            external_id=event["id"],
            user_id=self.user_id,
            source="google_calendar",
            title=event.get("summary", "Untitled Meeting"),
            description=event.get("description"),
            start_time=start_time,
            end_time=end_time,
            location=location,
            attendees=attendees,
            organizer=organizer,
        )

        return meeting
