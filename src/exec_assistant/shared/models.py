"""Data models for Executive Assistant system.

All models use Pydantic for validation and serialization.
Models are designed to work with DynamoDB and S3 storage.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class MeetingType(str, Enum):
    """Meeting type classification."""

    LEADERSHIP_TEAM = "leadership_team"
    ONE_ON_ONE = "one_on_one"
    RELIABILITY_REVIEW = "reliability_review"
    QUARTERLY_BUSINESS_REVIEW = "qbr"
    EXECUTIVE_STAFF = "executive_staff"
    INTERVIEW_DEBRIEF = "interview_debrief"
    VENDOR_MEETING = "vendor_meeting"
    UNKNOWN = "unknown"


class MeetingStatus(str, Enum):
    """Meeting preparation status."""

    DISCOVERED = "discovered"  # Found in calendar, not yet classified
    CLASSIFIED = "classified"  # Type determined, prep not started
    PREP_SCHEDULED = "prep_scheduled"  # Notification scheduled
    PREP_IN_PROGRESS = "prep_in_progress"  # User is prepping
    PREP_COMPLETED = "prep_completed"  # Materials generated
    COMPLETED = "completed"  # Meeting occurred
    CANCELLED = "cancelled"  # Meeting cancelled


class ChatSessionState(str, Enum):
    """Chat session state machine states."""

    CREATED = "created"  # Session created, not started
    ACTIVE = "active"  # Interactive Q&A in progress
    GENERATING = "generating"  # Agent generating materials
    COMPLETED = "completed"  # Materials delivered
    TIMED_OUT = "timed_out"  # Session expired
    CANCELLED = "cancelled"  # User cancelled


class NotificationChannel(str, Enum):
    """Available notification channels."""

    SLACK = "slack"
    SMS = "sms"
    EMAIL = "email"


class Meeting(BaseModel):
    """Meeting representation from calendar."""

    # Primary identifiers
    meeting_id: str = Field(
        ..., description="Unique identifier (from calendar provider or generated)"
    )
    external_id: str | None = Field(
        None, description="Calendar provider's event ID (for sync deduplication)"
    )
    user_id: str = Field(..., description="Slack user ID of meeting owner")
    source: str = Field(
        default="manual",
        description="Source of meeting: 'google_calendar', 'microsoft_calendar', or 'manual'",
    )

    # Calendar details
    title: str = Field(..., description="Meeting title/subject")
    description: str | None = Field(None, description="Meeting description/body")
    start_time: datetime = Field(..., description="Meeting start time (timezone-aware)")
    end_time: datetime = Field(..., description="Meeting end time (timezone-aware)")
    location: str | None = Field(None, description="Meeting location or video link")
    attendees: list[str] = Field(default_factory=list, description="Email addresses of attendees")
    organizer: str | None = Field(None, description="Email of meeting organizer")

    # Classification
    meeting_type: MeetingType = Field(
        default=MeetingType.UNKNOWN, description="Classified meeting type"
    )
    status: MeetingStatus = Field(
        default=MeetingStatus.DISCOVERED, description="Preparation status"
    )

    # Prep timing
    prep_trigger_time: datetime | None = Field(
        None, description="When to send prep notification (calculated based on meeting type)"
    )
    prep_hours_before: int | None = Field(None, description="Hours before meeting to trigger prep")

    # References
    chat_session_id: str | None = Field(None, description="Associated chat session for prep")
    materials_s3_key: str | None = Field(None, description="S3 key for generated materials")

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_synced_at: datetime | None = Field(None, description="Last time synced from calendar")

    @field_validator("start_time", "end_time", "created_at", "updated_at")
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        """Ensure datetime is timezone-aware (UTC)."""
        if v.tzinfo is None:
            msg = "Datetime must be timezone-aware"
            raise ValueError(msg)
        return v

    def to_dynamodb(self) -> dict[str, Any]:
        """Convert to DynamoDB item format."""
        data = self.model_dump()
        # Convert datetime objects to ISO format strings
        for field in [
            "start_time",
            "end_time",
            "created_at",
            "updated_at",
            "last_synced_at",
            "prep_trigger_time",
        ]:
            if data.get(field):
                data[field] = data[field].isoformat()
        return data

    @classmethod
    def from_dynamodb(cls, item: dict[str, Any]) -> "Meeting":
        """Create Meeting from DynamoDB item."""
        # Convert ISO strings back to datetime
        for field in [
            "start_time",
            "end_time",
            "created_at",
            "updated_at",
            "last_synced_at",
            "prep_trigger_time",
        ]:
            if item.get(field):
                item[field] = datetime.fromisoformat(item[field])
        return cls(**item)


class ChatMessage(BaseModel):
    """Single message in a chat session."""

    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        """Validate role is user or assistant."""
        if v not in {"user", "assistant", "system"}:
            msg = f"Role must be 'user', 'assistant', or 'system', got '{v}'"
            raise ValueError(msg)
        return v


class ChatSession(BaseModel):
    """Interactive chat session for meeting prep."""

    # Identifiers
    session_id: str = Field(..., description="Unique session identifier")
    user_id: str = Field(..., description="Slack user ID")
    meeting_id: str | None = Field(
        None, description="Associated meeting ID (None for general chat)"
    )

    # State
    state: ChatSessionState = Field(
        default=ChatSessionState.CREATED, description="Current session state"
    )

    # Conversation history
    messages: list[ChatMessage] = Field(default_factory=list, description="Conversation history")

    # Context gathered for this meeting
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Context from other agents (budget, incidents, etc.)",
    )

    # User responses to prep questions
    prep_responses: dict[str, str] = Field(
        default_factory=dict,
        description="User answers to prep questions",
    )

    # Workflow integration
    step_function_task_token: str | None = Field(
        None, description="Step Functions task token for callback"
    )

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = Field(None, description="Session expiration time")

    def add_message(self, role: str, content: str) -> None:
        """Add a message to the conversation history."""
        message = ChatMessage(role=role, content=content)
        self.messages.append(message)
        self.updated_at = datetime.now(UTC)

    def to_dynamodb(self) -> dict[str, Any]:
        """Convert to DynamoDB item format.

        Note: DynamoDB does not allow empty strings in index keys.
        Fields used in global secondary indexes (meeting_id) are only
        included if they have non-empty values.
        """
        data = self.model_dump()
        # Convert datetime objects to ISO format strings
        for field in ["created_at", "updated_at", "expires_at"]:
            if data.get(field):
                data[field] = data[field].isoformat()
        # Convert messages to list of dicts
        data["messages"] = [
            {
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.timestamp.isoformat(),
            }
            for msg in self.messages
        ]
        # Remove meeting_id if empty (DynamoDB index constraint)
        # The MeetingIndex GSI uses meeting_id as hash key and cannot have empty strings
        if not data.get("meeting_id"):
            data.pop("meeting_id", None)
        return data

    @classmethod
    def from_dynamodb(cls, item: dict[str, Any]) -> "ChatSession":
        """Create ChatSession from DynamoDB item."""
        # Convert ISO strings back to datetime
        for field in ["created_at", "updated_at", "expires_at"]:
            if item.get(field):
                item[field] = datetime.fromisoformat(item[field])
        # Convert message dicts to ChatMessage objects
        if "messages" in item:
            item["messages"] = [
                ChatMessage(
                    role=msg["role"],
                    content=msg["content"],
                    timestamp=datetime.fromisoformat(msg["timestamp"]),
                )
                for msg in item["messages"]
            ]
        return cls(**item)


class MeetingMaterials(BaseModel):
    """Generated meeting preparation materials."""

    # Identifiers
    meeting_id: str = Field(..., description="Associated meeting ID")
    session_id: str = Field(..., description="Chat session that generated these materials")

    # Generated content
    agenda: str = Field(..., description="Generated meeting agenda")
    question_bank: list[str] = Field(
        default_factory=list,
        description="Questions to ask during the meeting",
    )
    context_summary: str | None = Field(
        None, description="Summary of relevant context (budget, incidents, decisions)"
    )
    note_template: str = Field(..., description="Template for taking meeting notes")
    action_items_template: str | None = Field(
        None, description="Template for tracking action items"
    )

    # References to context used
    context_sources: dict[str, Any] = Field(
        default_factory=dict,
        description="References to context data used (budget variance, incidents, etc.)",
    )

    # Metadata
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    s3_key: str | None = Field(None, description="S3 key where materials are stored")
    presigned_url: str | None = Field(None, description="Presigned URL for accessing materials")

    def to_html(self) -> str:
        """Render materials as HTML for web viewing."""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Meeting Prep Materials</title>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 40px; }}
                h1, h2 {{ color: #2c3e50; }}
                .agenda {{ background-color: #f8f9fa; padding: 20px; border-radius: 8px; }}
                .question {{ margin: 10px 0; padding: 10px; background-color: #e8f4f8; border-left: 4px solid #3498db; }}
                .context {{ background-color: #fff3cd; padding: 15px; border-radius: 8px; margin: 20px 0; }}
                .template {{ background-color: #f1f1f1; padding: 15px; border-radius: 8px; font-family: monospace; white-space: pre-wrap; }}
            </style>
        </head>
        <body>
            <h1>Meeting Preparation Materials</h1>
            <p>Generated at: {self.generated_at.strftime("%Y-%m-%d %H:%M UTC")}</p>

            <h2>Agenda</h2>
            <div class="agenda">{self.agenda}</div>

            <h2>Questions to Ask</h2>
            <div class="questions">
                {"".join(f'<div class="question">{q}</div>' for q in self.question_bank)}
            </div>

            {f'<h2>Context Summary</h2><div class="context">{self.context_summary}</div>' if self.context_summary else ""}

            <h2>Note Template</h2>
            <div class="template">{self.note_template}</div>
        </body>
        </html>
        """
        return html

    def to_markdown(self) -> str:
        """Render materials as Markdown."""
        md = f"""# Meeting Preparation Materials

**Generated**: {self.generated_at.strftime("%Y-%m-%d %H:%M UTC")}

## Agenda

{self.agenda}

## Questions to Ask

{chr(10).join(f"- {q}" for q in self.question_bank)}

"""
        if self.context_summary:
            md += f"""## Context Summary

{self.context_summary}

"""
        md += f"""## Note Template

```
{self.note_template}
```
"""
        return md


class ActionItem(BaseModel):
    """Action item extracted from meeting notes."""

    # Identifiers
    action_id: str = Field(..., description="Unique action item ID")
    meeting_id: str = Field(..., description="Source meeting ID")

    # Content
    description: str = Field(..., description="What needs to be done")
    owner: str | None = Field(None, description="Who is responsible (email or Slack user ID)")
    due_date: datetime | None = Field(None, description="When it's due")

    # Status
    completed: bool = Field(default=False, description="Whether action is completed")
    completed_at: datetime | None = Field(None, description="When action was completed")

    # Context
    notes: str | None = Field(None, description="Additional notes or context")

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def to_dynamodb(self) -> dict[str, Any]:
        """Convert to DynamoDB item format.

        Note: DynamoDB does not allow empty strings or null values in index keys.
        Fields used in global secondary indexes (owner) are only included
        if they have non-empty values.
        """
        data = self.model_dump()
        # Convert datetime objects to ISO format strings
        for field in ["due_date", "completed_at", "created_at", "updated_at"]:
            if data.get(field):
                data[field] = data[field].isoformat()
        # Remove owner if None or empty (OwnerIndex GSI constraint)
        # The OwnerIndex GSI uses owner as hash key and cannot have empty strings or null
        if not data.get("owner"):
            data.pop("owner", None)
        return data

    @classmethod
    def from_dynamodb(cls, item: dict[str, Any]) -> "ActionItem":
        """Create ActionItem from DynamoDB item."""
        # Convert ISO strings back to datetime
        for field in ["due_date", "completed_at", "created_at", "updated_at"]:
            if item.get(field):
                item[field] = datetime.fromisoformat(item[field])
        return cls(**item)


class User(BaseModel):
    """User account linked to Google identity.

    Users authenticate via Google OAuth and can connect their Google Calendar
    for meeting synchronization.
    """

    # Identity
    user_id: str = Field(..., description="Unique user identifier (UUID)")
    google_id: str = Field(..., description="Google's unique identifier for this user")
    email: str = Field(..., description="User's email address from Google")
    name: str = Field(..., description="User's display name")
    picture_url: str | None = Field(None, description="URL to user's profile picture")

    # Calendar integration
    calendar_connected: bool = Field(
        default=False,
        description="Whether Google Calendar is connected",
    )
    calendar_refresh_token: str | None = Field(
        None,
        description="Encrypted refresh token for Google Calendar API access",
    )
    calendar_last_sync: datetime | None = Field(
        None,
        description="Last time calendar was synced",
    )

    # User preferences
    timezone: str = Field(
        default="America/New_York",
        description="User's timezone for scheduling",
    )
    notification_preferences: dict[str, bool] = Field(
        default_factory=lambda: {
            "prep_reminders": True,
            "meeting_updates": True,
            "daily_summary": False,
        },
        description="User notification preferences",
    )

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_login_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Basic email validation."""
        if "@" not in v or "." not in v.split("@")[1]:
            msg = f"Invalid email format: {v}"
            raise ValueError(msg)
        return v.lower()

    def update_last_login(self) -> None:
        """Update last login timestamp."""
        self.last_login_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)

    def connect_calendar(self, refresh_token: str) -> None:
        """Connect Google Calendar with refresh token.

        Args:
            refresh_token: Encrypted refresh token from OAuth flow
        """
        self.calendar_connected = True
        self.calendar_refresh_token = refresh_token
        self.calendar_last_sync = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)

    def disconnect_calendar(self) -> None:
        """Disconnect Google Calendar."""
        self.calendar_connected = False
        self.calendar_refresh_token = None
        self.calendar_last_sync = None
        self.updated_at = datetime.now(UTC)

    def to_dynamodb(self) -> dict[str, Any]:
        """Convert to DynamoDB item format."""
        data = self.model_dump()
        # Convert datetime objects to ISO format strings
        for field in ["created_at", "last_login_at", "updated_at", "calendar_last_sync"]:
            if data.get(field):
                data[field] = data[field].isoformat()
        return data

    @classmethod
    def from_dynamodb(cls, item: dict[str, Any]) -> "User":
        """Create User from DynamoDB item."""
        # Convert ISO strings back to datetime
        for field in ["created_at", "last_login_at", "updated_at", "calendar_last_sync"]:
            if item.get(field):
                item[field] = datetime.fromisoformat(item[field])
        return cls(**item)

    def to_api_response(self) -> dict[str, Any]:
        """Convert to API response format (excludes sensitive fields).

        Returns:
            User data safe to send to frontend
        """
        return {
            "user_id": self.user_id,
            "email": self.email,
            "name": self.name,
            "picture_url": self.picture_url,
            "calendar_connected": self.calendar_connected,
            "timezone": self.timezone,
            "notification_preferences": self.notification_preferences,
            "created_at": self.created_at.isoformat(),
            "last_login_at": self.last_login_at.isoformat(),
        }
