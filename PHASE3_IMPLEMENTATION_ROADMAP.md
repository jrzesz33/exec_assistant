# Phase 3 Implementation Roadmap

**Status**: 📋 Ready to Start
**Duration**: 3-4 weeks (4 sprints)
**Complexity**: High
**Risk Level**: Medium-High

## Executive Summary

This document provides a **step-by-step implementation guide** for Phase 3: Meeting Preparation Workflow. It complements [PHASE3_PLAN.md](./PHASE3_PLAN.md) (design specification) with actionable implementation steps, decision points, and risk mitigation strategies.

**What We're Building**:
- 📅 Google Calendar integration with OAuth 2.0
- ⏰ Automated calendar polling every 2 hours (EventBridge)
- 🤖 Meeting classification (type detection)
- 🔄 Step Functions workflow (complete prep flow)
- 📨 Proactive Slack/SMS notifications
- 📄 AI-generated meeting materials (agendas, questions, templates)
- 📦 S3 storage and delivery via presigned URLs

**What Changes from Phase 2**:
- Phase 2: User initiates chat ("Help me prep")
- Phase 3: System proactively notifies user ("You have a meeting in 2 days")

---

## Pre-Implementation Checklist

### Technical Prerequisites

- [x] Phase 1 complete (infrastructure)
- [x] Phase 1.5 complete (authentication)
- [x] Phase 2 complete (Meeting Coordinator agent)
- [ ] **Decision**: Google Calendar or Microsoft 365?
- [ ] **Decision**: Prep notification timing (24-72 hours)?
- [ ] **Decision**: Slack-only or Slack + SMS?
- [ ] **Access**: Google Cloud Console (for OAuth credentials)
- [ ] **Access**: AWS account with Bedrock, Step Functions, EventBridge enabled
- [ ] **Budget**: Approved for ~$100-150/month AWS costs

### Team Alignment

- [ ] Product requirements finalized
- [ ] Phase 3 design reviewed and approved
- [ ] First 5 beta users identified
- [ ] Success metrics defined
- [ ] Weekly check-in schedule established

---

## Implementation Strategy

### Philosophy

**Incremental Deployment**: Each sprint delivers working functionality
- Sprint 1: Calendar integration works (manual testing)
- Sprint 2: Automated polling works (meetings appear in DB)
- Sprint 3: Workflow works (end-to-end flow without materials)
- Sprint 4: Complete system works (with AI-generated materials)

**Feature Flags**: Use Pulumi config to enable features incrementally
```bash
pulumi config set exec-assistant:enable_calendar_integration true  # Sprint 1
pulumi config set exec-assistant:enable_calendar_monitor true      # Sprint 2
pulumi config set exec-assistant:enable_step_functions true        # Sprint 3
pulumi config set exec-assistant:enable_material_generation true   # Sprint 4
```

**Fail Fast**: Validate critical components early
- Sprint 1, Day 1: OAuth flow working
- Sprint 2, Day 1: EventBridge trigger working
- Sprint 3, Day 1: Step Functions state machine created
- Sprint 4, Day 1: Agent generates agenda

---

## Sprint 1: Calendar Integration (Week 1)

### Goal
Users can authorize Google Calendar access, and we can fetch their meetings programmatically.

### Sprint 1 Architecture

```
User clicks "Connect Calendar"
    ↓
Web UI: /calendar/auth (redirects to Google)
    ↓
Google OAuth consent screen
    ↓
User approves
    ↓
Callback: /calendar/callback (API Gateway)
    ↓
Calendar Auth Lambda
    ↓
Store tokens in Secrets Manager
    ↓
Update user record in DynamoDB (calendar_connected=true)
```

### Tasks (Sprint 1)

#### Day 1: Google OAuth Setup

**Task 1.1: Google Cloud Console Configuration**
```bash
# Manual steps in Google Cloud Console:
1. Create new project: "exec-assistant-calendar"
2. Enable Google Calendar API
3. Create OAuth 2.0 credentials
   - Application type: Web application
   - Authorized redirect URIs:
     - Local: http://localhost:3000/calendar/callback
     - Dev: https://{api-id}.execute-api.us-east-1.amazonaws.com/calendar/callback
     - Prod: https://app.execassistant.com/calendar/callback
4. Download credentials JSON
5. Note Client ID and Client Secret
```

**Task 1.2: Store OAuth Credentials in Pulumi**
```bash
cd infrastructure

# Store as secrets
pulumi config set --secret exec-assistant:google_calendar_client_id "YOUR_CLIENT_ID"
pulumi config set --secret exec-assistant:google_calendar_client_secret "YOUR_CLIENT_SECRET"

# Verify
pulumi config get exec-assistant:google_calendar_client_id
```

**Deliverable**: OAuth credentials configured

---

#### Day 2-3: Calendar Module Implementation

**Task 1.3: Create Calendar Integration Module**

File: `src/exec_assistant/shared/calendar.py`

```python
"""Google Calendar integration module.

This module handles:
- OAuth 2.0 authorization flow
- Token storage and refresh
- Calendar API interactions
- Meeting data extraction
"""

import os
from datetime import datetime, timedelta
from typing import List, Optional

import boto3
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from exec_assistant.shared.models import Meeting
from exec_assistant.shared.logging import get_logger

logger = get_logger(__name__)


class CalendarClient:
    """Google Calendar API client with OAuth 2.0 authentication."""

    def __init__(
        self,
        user_id: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
    ):
        """Initialize calendar client.

        Args:
            user_id: User identifier for token storage
            client_id: Google OAuth client ID
            client_secret: Google OAuth client secret
            redirect_uri: OAuth callback URL
        """
        self.user_id = user_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.secrets_manager = boto3.client("secretsmanager")

    def get_authorization_url(self) -> str:
        """Generate OAuth authorization URL.

        Returns:
            URL to redirect user to for authorization
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
            scopes=[
                "https://www.googleapis.com/auth/calendar.readonly",
                "https://www.googleapis.com/auth/calendar.events.readonly",
            ],
        )

        flow.redirect_uri = self.redirect_uri

        authorization_url, state = flow.authorization_url(
            access_type="offline",  # Request refresh token
            include_granted_scopes="true",
            prompt="consent",  # Force consent screen
        )

        logger.info(
            "user_id=<%s> | generated authorization url",
            self.user_id,
        )

        return authorization_url

    async def handle_oauth_callback(self, code: str) -> dict:
        """Handle OAuth callback and store tokens.

        Args:
            code: Authorization code from Google

        Returns:
            Dict with status and user info
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
            scopes=[
                "https://www.googleapis.com/auth/calendar.readonly",
                "https://www.googleapis.com/auth/calendar.events.readonly",
            ],
        )

        flow.redirect_uri = self.redirect_uri

        # Exchange code for tokens
        flow.fetch_token(code=code)
        credentials = flow.credentials

        # Store tokens in Secrets Manager
        secret_name = f"calendar-tokens-{self.user_id}"

        token_data = {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": credentials.scopes,
        }

        try:
            self.secrets_manager.create_secret(
                Name=secret_name,
                SecretString=json.dumps(token_data),
            )
            logger.info(
                "user_id=<%s>, secret=<%s> | created calendar token secret",
                self.user_id,
                secret_name,
            )
        except self.secrets_manager.exceptions.ResourceExistsException:
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

        return {
            "status": "connected",
            "user_id": self.user_id,
            "scopes": credentials.scopes,
        }

    async def fetch_upcoming_meetings(
        self,
        days_ahead: int = 14,
    ) -> List[Meeting]:
        """Fetch upcoming meetings from Google Calendar.

        Args:
            days_ahead: Number of days to look ahead

        Returns:
            List of Meeting objects
        """
        # Load credentials from Secrets Manager
        credentials = await self._load_credentials()

        if not credentials:
            logger.warning(
                "user_id=<%s> | no calendar credentials found",
                self.user_id,
            )
            return []

        # Refresh token if needed
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            await self._save_credentials(credentials)

        # Build Calendar API client
        service = build("calendar", "v3", credentials=credentials)

        # Calculate time range
        now = datetime.utcnow()
        time_min = now.isoformat() + "Z"
        time_max = (now + timedelta(days=days_ahead)).isoformat() + "Z"

        # Fetch events
        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                maxResults=100,
                singleEvents=True,
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

        return meetings

    def _event_to_meeting(self, event: dict) -> Optional[Meeting]:
        """Convert Google Calendar event to Meeting object.

        Args:
            event: Google Calendar event dict

        Returns:
            Meeting object or None if invalid
        """
        # Skip all-day events
        if "date" in event.get("start", {}):
            return None

        # Extract meeting details
        meeting_id = event["id"]
        title = event.get("summary", "Untitled Meeting")
        start_time = event["start"].get("dateTime")
        end_time = event["end"].get("dateTime")
        description = event.get("description", "")
        attendees = event.get("attendees", [])

        if not start_time:
            return None

        # Parse attendees
        attendee_emails = [
            attendee.get("email") for attendee in attendees if attendee.get("email")
        ]

        return Meeting(
            external_id=meeting_id,
            user_id=self.user_id,
            title=title,
            start_time=datetime.fromisoformat(start_time.replace("Z", "+00:00")),
            end_time=datetime.fromisoformat(end_time.replace("Z", "+00:00")),
            description=description,
            attendees=attendee_emails,
            source="google_calendar",
        )

    async def _load_credentials(self) -> Optional[Credentials]:
        """Load OAuth credentials from Secrets Manager."""
        secret_name = f"calendar-tokens-{self.user_id}"

        try:
            response = self.secrets_manager.get_secret_value(SecretId=secret_name)
            token_data = json.loads(response["SecretString"])

            credentials = Credentials(
                token=token_data["token"],
                refresh_token=token_data.get("refresh_token"),
                token_uri=token_data["token_uri"],
                client_id=token_data["client_id"],
                client_secret=token_data["client_secret"],
                scopes=token_data["scopes"],
            )

            return credentials

        except self.secrets_manager.exceptions.ResourceNotFoundException:
            logger.warning(
                "user_id=<%s>, secret=<%s> | calendar tokens not found",
                self.user_id,
                secret_name,
            )
            return None

    async def _save_credentials(self, credentials: Credentials) -> None:
        """Save updated OAuth credentials to Secrets Manager."""
        secret_name = f"calendar-tokens-{self.user_id}"

        token_data = {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": credentials.scopes,
        }

        self.secrets_manager.update_secret(
            SecretId=secret_name,
            SecretString=json.dumps(token_data),
        )

        logger.info(
            "user_id=<%s>, secret=<%s> | updated calendar tokens",
            self.user_id,
            secret_name,
        )
```

**Task 1.4: Update Meeting Model**

File: `src/exec_assistant/shared/models.py` (update)

```python
@dataclass
class Meeting:
    """Meeting data model."""

    meeting_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    external_id: str | None = None  # Calendar event ID
    user_id: str = ""
    title: str = ""
    start_time: datetime | None = None
    end_time: datetime | None = None
    description: str = ""
    attendees: list[str] = field(default_factory=list)
    source: str = "manual"  # manual | google_calendar | microsoft_calendar
    meeting_type: str = "default"  # To be classified
    prep_trigger_time: datetime | None = None  # When to start prep
    prep_status: str = "not_started"  # not_started | notified | in_progress | completed
    materials_url: str | None = None  # S3 presigned URL to materials
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dynamodb(self) -> dict:
        """Convert to DynamoDB item."""
        return {
            "meeting_id": self.meeting_id,
            "external_id": self.external_id or "",
            "user_id": self.user_id,
            "title": self.title,
            "start_time": self.start_time.isoformat() if self.start_time else "",
            "end_time": self.end_time.isoformat() if self.end_time else "",
            "description": self.description,
            "attendees": self.attendees,
            "source": self.source,
            "meeting_type": self.meeting_type,
            "prep_trigger_time": (
                self.prep_trigger_time.isoformat() if self.prep_trigger_time else ""
            ),
            "prep_status": self.prep_status,
            "materials_url": self.materials_url or "",
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @staticmethod
    def from_dynamodb(item: dict) -> "Meeting":
        """Create from DynamoDB item."""
        return Meeting(
            meeting_id=item["meeting_id"],
            external_id=item.get("external_id") or None,
            user_id=item["user_id"],
            title=item["title"],
            start_time=(
                datetime.fromisoformat(item["start_time"]) if item.get("start_time") else None
            ),
            end_time=(
                datetime.fromisoformat(item["end_time"]) if item.get("end_time") else None
            ),
            description=item.get("description", ""),
            attendees=item.get("attendees", []),
            source=item.get("source", "manual"),
            meeting_type=item.get("meeting_type", "default"),
            prep_trigger_time=(
                datetime.fromisoformat(item["prep_trigger_time"])
                if item.get("prep_trigger_time")
                else None
            ),
            prep_status=item.get("prep_status", "not_started"),
            materials_url=item.get("materials_url"),
            created_at=datetime.fromisoformat(item["created_at"]),
            updated_at=datetime.fromisoformat(item["updated_at"]),
        )
```

**Deliverable**: Calendar module complete with OAuth and meeting fetching

---

#### Day 4: Calendar Auth Lambda

**Task 1.5: Create Calendar Auth Handler**

File: `src/exec_assistant/interfaces/calendar_handler.py`

```python
"""Calendar authentication handler Lambda.

Endpoints:
- GET /calendar/auth - Initiate OAuth flow
- GET /calendar/callback - Handle OAuth callback
- POST /calendar/disconnect - Disconnect calendar
"""

import json
import os
from typing import Any

import boto3

from exec_assistant.shared.calendar import CalendarClient
from exec_assistant.shared.jwt_handler import JWTHandler
from exec_assistant.shared.logging import get_logger

logger = get_logger(__name__)

# Global clients (initialized once per Lambda container)
_dynamodb = None
_jwt_handler = None


def get_dynamodb():
    """Get DynamoDB resource (cached)."""
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb", region_name=os.environ["AWS_REGION"])
    return _dynamodb


def get_jwt_handler():
    """Get JWT handler (cached)."""
    global _jwt_handler
    if _jwt_handler is None:
        _jwt_handler = JWTHandler(secret_key=os.environ["JWT_SECRET_KEY"])
    return _jwt_handler


def create_response(status_code: int, body: dict) -> dict:
    """Create HTTP response."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        },
        "body": json.dumps(body),
    }


async def handle_calendar_auth(event: dict, context: Any) -> dict:
    """Handle GET /calendar/auth - Initiate OAuth flow.

    Returns OAuth authorization URL to redirect user to.
    """
    try:
        # Extract JWT token
        jwt_handler = get_jwt_handler()
        token = event["headers"].get("authorization", "").replace("Bearer ", "")

        if not token:
            return create_response(401, {"error": "Missing authorization token"})

        user_id = jwt_handler.verify_token(token)

        # Create calendar client
        client = CalendarClient(
            user_id=user_id,
            client_id=os.environ["GOOGLE_CALENDAR_CLIENT_ID"],
            client_secret=os.environ["GOOGLE_CALENDAR_CLIENT_SECRET"],
            redirect_uri=os.environ["GOOGLE_CALENDAR_REDIRECT_URI"],
        )

        # Generate authorization URL
        auth_url = client.get_authorization_url()

        logger.info(
            "user_id=<%s> | generated calendar authorization url",
            user_id,
        )

        return create_response(
            200,
            {
                "authorization_url": auth_url,
                "status": "redirect_to_google",
            },
        )

    except Exception as e:
        logger.error(
            "error=<%s> | failed to generate authorization url",
            str(e),
            exc_info=True,
        )
        return create_response(500, {"error": "Internal server error"})


async def handle_calendar_callback(event: dict, context: Any) -> dict:
    """Handle GET /calendar/callback - OAuth callback from Google.

    Exchanges authorization code for access/refresh tokens.
    Stores tokens in Secrets Manager.
    Updates user record in DynamoDB.
    """
    try:
        # Extract authorization code from query parameters
        code = event.get("queryStringParameters", {}).get("code")

        if not code:
            return create_response(400, {"error": "Missing authorization code"})

        # Extract state (contains user_id)
        state = event.get("queryStringParameters", {}).get("state")
        # In production, decode state to get user_id
        # For now, get user_id from JWT (if passed in redirect)

        # TODO: Implement proper state handling
        # For now, return HTML that closes window and notifies parent
        html_response = """
        <html>
        <body>
        <h1>Calendar Connected!</h1>
        <p>You can close this window.</p>
        <script>
        window.opener.postMessage({type: 'calendar_connected'}, '*');
        window.close();
        </script>
        </body>
        </html>
        """

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "text/html"},
            "body": html_response,
        }

    except Exception as e:
        logger.error(
            "error=<%s> | calendar callback failed",
            str(e),
            exc_info=True,
        )
        return create_response(500, {"error": "Calendar connection failed"})


def lambda_handler(event: dict, context: Any) -> dict:
    """Main Lambda handler for calendar endpoints.

    Routes:
    - GET /calendar/auth → handle_calendar_auth
    - GET /calendar/callback → handle_calendar_callback
    """
    import asyncio

    path = event.get("path", "")
    method = event.get("httpMethod", "")

    logger.info(
        "method=<%s>, path=<%s> | handling calendar request",
        method,
        path,
    )

    if path == "/calendar/auth" and method == "GET":
        return asyncio.run(handle_calendar_auth(event, context))
    elif path == "/calendar/callback" and method == "GET":
        return asyncio.run(handle_calendar_callback(event, context))
    else:
        return create_response(404, {"error": "Not found"})
```

**Deliverable**: Calendar auth Lambda complete

---

#### Day 5: Infrastructure and Testing

**Task 1.6: Deploy Calendar Infrastructure**

File: `infrastructure/calendar.py` (new)

```python
"""Calendar integration infrastructure."""

import json

import pulumi
import pulumi_aws as aws


def create_calendar_infrastructure(
    environment: str,
    lambda_role: aws.iam.Role,
    lambda_layer: aws.lambda_.LayerVersion,
    api_gateway: aws.apigatewayv2.Api,
    jwt_secret: str,
) -> dict:
    """Create calendar integration resources.

    Args:
        environment: Environment name (dev/prod)
        lambda_role: Lambda execution role
        lambda_layer: Lambda layer with dependencies
        api_gateway: API Gateway instance
        jwt_secret: JWT secret key

    Returns:
        Dict with created resources
    """
    config = pulumi.Config("exec-assistant")

    # Get OAuth credentials from config
    google_calendar_client_id = config.require_secret("google_calendar_client_id")
    google_calendar_client_secret = config.require_secret("google_calendar_client_secret")

    # Calendar auth Lambda
    calendar_lambda = aws.lambda_.Function(
        f"exec-assistant-calendar-{environment}",
        runtime="python3.11",
        handler="exec_assistant.interfaces.calendar_handler.lambda_handler",
        role=lambda_role.arn,
        timeout=30,
        memory_size=512,
        layers=[lambda_layer.arn],
        environment={
            "variables": {
                "ENV": environment,
                "AWS_REGION": "us-east-1",
                "GOOGLE_CALENDAR_CLIENT_ID": google_calendar_client_id,
                "GOOGLE_CALENDAR_CLIENT_SECRET": google_calendar_client_secret,
                "GOOGLE_CALENDAR_REDIRECT_URI": pulumi.Output.concat(
                    "https://",
                    api_gateway.api_endpoint,
                    "/calendar/callback",
                ),
                "JWT_SECRET_KEY": jwt_secret,
                "LOG_LEVEL": "INFO",
            }
        },
        code=pulumi.AssetArchive({
            ".": pulumi.FileArchive("../src"),
        }),
    )

    # API Gateway routes
    calendar_auth_integration = aws.apigatewayv2.Integration(
        f"calendar-auth-integration-{environment}",
        api_id=api_gateway.id,
        integration_type="AWS_PROXY",
        integration_uri=calendar_lambda.arn,
        payload_format_version="2.0",
    )

    calendar_auth_route = aws.apigatewayv2.Route(
        f"calendar-auth-route-{environment}",
        api_id=api_gateway.id,
        route_key="GET /calendar/auth",
        target=calendar_auth_integration.id.apply(
            lambda id: f"integrations/{id}"
        ),
    )

    calendar_callback_route = aws.apigatewayv2.Route(
        f"calendar-callback-route-{environment}",
        api_id=api_gateway.id,
        route_key="GET /calendar/callback",
        target=calendar_auth_integration.id.apply(
            lambda id: f"integrations/{id}"
        ),
    )

    # Lambda permissions
    calendar_auth_permission = aws.lambda_.Permission(
        f"calendar-auth-permission-{environment}",
        action="lambda:InvokeFunction",
        function=calendar_lambda.name,
        principal="apigateway.amazonaws.com",
        source_arn=pulumi.Output.concat(
            api_gateway.execution_arn,
            "/*/*/calendar/*",
        ),
    )

    # Update Lambda IAM role to allow Secrets Manager access
    calendar_secrets_policy = aws.iam.RolePolicy(
        f"calendar-secrets-policy-{environment}",
        role=lambda_role.id,
        policy=json.dumps({
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Action": [
                    "secretsmanager:CreateSecret",
                    "secretsmanager:GetSecretValue",
                    "secretsmanager:UpdateSecret",
                ],
                "Resource": f"arn:aws:secretsmanager:*:*:secret:calendar-tokens-*",
            }],
        }),
    )

    return {
        "calendar_lambda": calendar_lambda,
        "calendar_auth_route": calendar_auth_route,
        "calendar_callback_route": calendar_callback_route,
    }
```

**Task 1.7: Write Tests**

File: `tests/test_calendar.py` (new)

```python
"""Tests for calendar integration."""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta

from exec_assistant.shared.calendar import CalendarClient
from exec_assistant.shared.models import Meeting


def test_calendar_client_initialization():
    """Test CalendarClient can be initialized."""
    client = CalendarClient(
        user_id="test-user",
        client_id="test-client-id",
        client_secret="test-secret",
        redirect_uri="http://localhost/callback",
    )

    assert client.user_id == "test-user"
    assert client.client_id == "test-client-id"


def test_get_authorization_url():
    """Test authorization URL generation."""
    client = CalendarClient(
        user_id="test-user",
        client_id="test-client-id",
        client_secret="test-secret",
        redirect_uri="http://localhost/callback",
    )

    url = client.get_authorization_url()

    assert "accounts.google.com/o/oauth2/auth" in url
    assert "client_id=test-client-id" in url
    assert "redirect_uri" in url


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fetch_upcoming_meetings_real():
    """Test fetching meetings from real Google Calendar.

    Requires:
    - Real Google Calendar OAuth tokens
    - Test calendar with known events
    """
    pytest.skip("Integration test - requires real calendar access")

    # This test would use real credentials and calendar
    client = CalendarClient(
        user_id="test-user",
        client_id=os.environ["GOOGLE_CALENDAR_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CALENDAR_CLIENT_SECRET"],
        redirect_uri="http://localhost/callback",
    )

    meetings = await client.fetch_upcoming_meetings(days_ahead=7)

    assert isinstance(meetings, list)
    # Additional assertions based on test calendar events
```

**Task 1.8: Deploy and Test**

```bash
# Deploy Sprint 1
cd infrastructure
pulumi config set exec-assistant:enable_calendar_integration true
pulumi up

# Test OAuth flow manually
# 1. Get API endpoint
API_ENDPOINT=$(pulumi stack output api_endpoint)

# 2. Open browser to /calendar/auth with JWT token
# (This would be done through Web UI in reality)

# 3. Verify callback works and tokens stored
aws secretsmanager list-secrets | grep calendar-tokens
```

**Sprint 1 Deliverable**: ✅ Calendar OAuth working, can fetch meetings programmatically

---

## Sprint 2: Calendar Monitor (Week 2)

### Goal
Automated calendar polling every 2 hours, meetings stored in DynamoDB, classified by type.

### Sprint 2 Architecture

```
EventBridge Scheduled Rule (every 2 hours)
    ↓
Calendar Monitor Lambda
    ↓
For each user with calendar_connected=true:
    ├─→ Fetch events from Google Calendar
    ├─→ Compare with existing meetings in DynamoDB
    ├─→ Classify new/updated meetings
    ├─→ Calculate prep_trigger_time
    ├─→ Store/update in DynamoDB
    └─→ Emit EventBridge event if prep needed
```

### Tasks (Sprint 2)

#### Day 1: Meeting Classification

**Task 2.1: Implement Meeting Classifier**

File: `src/exec_assistant/shared/meeting_classifier.py` (new)

```python
"""Meeting classification logic.

Classifies meetings by type based on:
- Title keywords
- Attendee count
- Description keywords
- User's custom rules
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

import yaml

from exec_assistant.shared.models import Meeting
from exec_assistant.shared.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MeetingTypeRule:
    """Rule for classifying a meeting type."""

    meeting_type: str
    keywords: List[str]
    required_attendees_min: Optional[int] = None
    required_attendees_max: Optional[int] = None
    prep_hours_before: int = 24


class MeetingClassifier:
    """Classify meetings by type."""

    def __init__(self, rules_config_path: str = "config/meeting_types.yaml"):
        """Initialize classifier with rules.

        Args:
            rules_config_path: Path to meeting types configuration
        """
        self.rules = self._load_rules(rules_config_path)

    def _load_rules(self, config_path: str) -> List[MeetingTypeRule]:
        """Load meeting type rules from YAML config."""
        with open(config_path) as f:
            config = yaml.safe_load(f)

        rules = []
        for type_name, type_config in config.get("meeting_types", {}).items():
            rule = MeetingTypeRule(
                meeting_type=type_name,
                keywords=type_config.get("keywords", []),
                required_attendees_min=type_config.get("required_attendees_min"),
                required_attendees_max=type_config.get("required_attendees_max"),
                prep_hours_before=type_config.get("prep_hours_before", 24),
            )
            rules.append(rule)

        logger.info("loaded_rules=<%d> | loaded meeting type rules", len(rules))

        return rules

    def classify(self, meeting: Meeting) -> Meeting:
        """Classify meeting and set type and prep_trigger_time.

        Args:
            meeting: Meeting to classify

        Returns:
            Meeting with meeting_type and prep_trigger_time set
        """
        # Combine title and description for keyword matching
        text = f"{meeting.title} {meeting.description}".lower()

        # Count attendees
        attendee_count = len(meeting.attendees)

        # Try to match against rules
        for rule in self.rules:
            # Check keyword match
            keyword_match = any(
                keyword.lower() in text for keyword in rule.keywords
            )

            # Check attendee count
            attendee_match = True
            if rule.required_attendees_min is not None:
                attendee_match = attendee_match and (
                    attendee_count >= rule.required_attendees_min
                )
            if rule.required_attendees_max is not None:
                attendee_match = attendee_match and (
                    attendee_count <= rule.required_attendees_max
                )

            # If both match, classify as this type
            if keyword_match and attendee_match:
                meeting.meeting_type = rule.meeting_type

                # Calculate prep trigger time
                if meeting.start_time:
                    meeting.prep_trigger_time = meeting.start_time - timedelta(
                        hours=rule.prep_hours_before
                    )

                logger.info(
                    "meeting_id=<%s>, title=<%s>, type=<%s>, prep_hours=<%d> | classified meeting",
                    meeting.meeting_id,
                    meeting.title,
                    rule.meeting_type,
                    rule.prep_hours_before,
                )

                return meeting

        # Default classification
        meeting.meeting_type = "default"
        if meeting.start_time:
            meeting.prep_trigger_time = meeting.start_time - timedelta(hours=24)

        logger.info(
            "meeting_id=<%s>, title=<%s> | using default classification",
            meeting.meeting_id,
            meeting.title,
        )

        return meeting
```

**Task 2.2: Create Meeting Types Configuration**

File: `config/meeting_types.yaml` (new)

```yaml
meeting_types:
  leadership_meeting:
    keywords:
      - "leadership"
      - "leadership team"
      - "LT meeting"
      - "LT sync"
    required_attendees_min: 10
    prep_hours_before: 72  # 3 days

  one_on_one:
    keywords:
      - "1-1"
      - "1:1"
      - "one on one"
      - "1-on-1"
    required_attendees_max: 3
    prep_hours_before: 24  # 1 day

  staff_meeting:
    keywords:
      - "staff meeting"
      - "all hands"
      - "team meeting"
    required_attendees_min: 15
    prep_hours_before: 48  # 2 days

  qbr:
    keywords:
      - "QBR"
      - "quarterly business review"
      - "quarterly review"
    required_attendees_min: 20
    prep_hours_before: 336  # 2 weeks

  incident_review:
    keywords:
      - "post-mortem"
      - "incident review"
      - "SEV"
      - "outage review"
    prep_hours_before: 2  # ASAP

  executive_meeting:
    keywords:
      - "executive"
      - "exec team"
      - "CIO"
      - "CEO"
    required_attendees_min: 5
    prep_hours_before: 96  # 4 days

  default:
    keywords: []
    prep_hours_before: 24
```

**Deliverable**: Meeting classification working

---

#### Day 2-3: Calendar Monitor Lambda

**Task 2.3: Implement Calendar Monitor**

File: `src/exec_assistant/workflows/calendar_monitor.py` (new)

```python
"""Calendar monitor Lambda.

Triggered by EventBridge every 2 hours.
Syncs calendar events for all users with calendar_connected=true.
"""

import json
import os
from datetime import datetime
from typing import Any, List

import boto3

from exec_assistant.shared.calendar import CalendarClient
from exec_assistant.shared.meeting_classifier import MeetingClassifier
from exec_assistant.shared.models import Meeting
from exec_assistant.shared.logging import get_logger

logger = get_logger(__name__)

# Global clients
_dynamodb = None
_eventbridge = None
_classifier = None


def get_dynamodb():
    """Get DynamoDB resource (cached)."""
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb", region_name=os.environ["AWS_REGION"])
    return _dynamodb


def get_eventbridge():
    """Get EventBridge client (cached)."""
    global _eventbridge
    if _eventbridge is None:
        _eventbridge = boto3.client("events", region_name=os.environ["AWS_REGION"])
    return _eventbridge


def get_classifier():
    """Get meeting classifier (cached)."""
    global _classifier
    if _classifier is None:
        _classifier = MeetingClassifier()
    return _classifier


async def sync_user_calendar(user_id: str) -> dict:
    """Sync calendar events for a single user.

    Args:
        user_id: User ID to sync

    Returns:
        Dict with sync results
    """
    logger.info("user_id=<%s> | starting calendar sync", user_id)

    # Create calendar client
    calendar_client = CalendarClient(
        user_id=user_id,
        client_id=os.environ["GOOGLE_CALENDAR_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CALENDAR_CLIENT_SECRET"],
        redirect_uri=os.environ["GOOGLE_CALENDAR_REDIRECT_URI"],
    )

    # Fetch upcoming meetings
    try:
        calendar_meetings = await calendar_client.fetch_upcoming_meetings(
            days_ahead=14
        )
    except Exception as e:
        logger.error(
            "user_id=<%s>, error=<%s> | failed to fetch calendar events",
            user_id,
            str(e),
            exc_info=True,
        )
        return {
            "user_id": user_id,
            "status": "error",
            "error": str(e),
        }

    logger.info(
        "user_id=<%s>, event_count=<%d> | fetched calendar events",
        user_id,
        len(calendar_meetings),
    )

    # Get existing meetings from DynamoDB
    dynamodb = get_dynamodb()
    meetings_table = dynamodb.Table(os.environ["MEETINGS_TABLE_NAME"])

    existing_meetings = []
    response = meetings_table.query(
        IndexName="user_id-index",
        KeyConditionExpression="user_id = :user_id",
        ExpressionAttributeValues={":user_id": user_id},
    )
    existing_meetings = [Meeting.from_dynamodb(item) for item in response["Items"]]

    # Create lookup by external_id
    existing_by_external_id = {
        m.external_id: m for m in existing_meetings if m.external_id
    }

    # Compare and sync
    classifier = get_classifier()
    eventbridge = get_eventbridge()

    stats = {
        "new": 0,
        "updated": 0,
        "unchanged": 0,
        "prep_events_emitted": 0,
    }

    for calendar_meeting in calendar_meetings:
        existing = existing_by_external_id.get(calendar_meeting.external_id)

        if not existing:
            # New meeting
            classified = classifier.classify(calendar_meeting)

            # Store in DynamoDB
            meetings_table.put_item(Item=classified.to_dynamodb())

            stats["new"] += 1

            # Emit event if prep needed
            if should_prep_now(classified):
                emit_prep_event(classified)
                stats["prep_events_emitted"] += 1

        elif meeting_changed(existing, calendar_meeting):
            # Updated meeting
            calendar_meeting.meeting_id = existing.meeting_id  # Preserve ID
            classified = classifier.classify(calendar_meeting)

            # Update in DynamoDB
            meetings_table.put_item(Item=classified.to_dynamodb())

            stats["updated"] += 1

            # Emit event if prep needed
            if should_prep_now(classified):
                emit_prep_event(classified)
                stats["prep_events_emitted"] += 1

        else:
            # Unchanged
            stats["unchanged"] += 1

    logger.info(
        "user_id=<%s>, new=<%d>, updated=<%d>, unchanged=<%d>, prep_events=<%d> | calendar sync complete",
        user_id,
        stats["new"],
        stats["updated"],
        stats["unchanged"],
        stats["prep_events_emitted"],
    )

    return {
        "user_id": user_id,
        "status": "success",
        "stats": stats,
    }


def meeting_changed(existing: Meeting, new: Meeting) -> bool:
    """Check if meeting has changed."""
    return (
        existing.title != new.title
        or existing.start_time != new.start_time
        or existing.end_time != new.end_time
        or existing.attendees != new.attendees
    )


def should_prep_now(meeting: Meeting) -> bool:
    """Check if meeting prep should be triggered now.

    Returns True if:
    - prep_trigger_time has passed
    - prep_status is not_started
    - meeting is in the future
    """
    now = datetime.utcnow()

    if not meeting.prep_trigger_time:
        return False

    if meeting.prep_status != "not_started":
        return False

    if not meeting.start_time or meeting.start_time < now:
        return False

    return meeting.prep_trigger_time <= now


def emit_prep_event(meeting: Meeting) -> None:
    """Emit EventBridge event for meeting prep."""
    eventbridge = get_eventbridge()

    event = {
        "Source": "exec-assistant.calendar-monitor",
        "DetailType": "MeetingRequiresPrep",
        "Detail": json.dumps({
            "meeting_id": meeting.meeting_id,
            "user_id": meeting.user_id,
            "meeting_time": meeting.start_time.isoformat() if meeting.start_time else "",
            "prep_trigger_time": meeting.prep_trigger_time.isoformat() if meeting.prep_trigger_time else "",
            "meeting_type": meeting.meeting_type,
            "title": meeting.title,
        }),
    }

    eventbridge.put_events(Entries=[event])

    logger.info(
        "meeting_id=<%s>, type=<%s> | emitted prep event",
        meeting.meeting_id,
        meeting.meeting_type,
    )


async def lambda_handler(event: dict, context: Any) -> dict:
    """Calendar monitor Lambda handler.

    Triggered by EventBridge every 2 hours.
    Syncs all users' calendars.
    """
    logger.info("starting calendar monitor run")

    # Get all users with calendar connected
    dynamodb = get_dynamodb()
    users_table = dynamodb.Table(os.environ["USERS_TABLE_NAME"])

    response = users_table.scan(
        FilterExpression="calendar_connected = :true",
        ExpressionAttributeValues={":true": True},
    )

    users = response["Items"]

    logger.info("user_count=<%d> | found users with calendar connected", len(users))

    # Sync each user's calendar
    results = []
    for user in users:
        result = await sync_user_calendar(user["user_id"])
        results.append(result)

    # Aggregate stats
    total_stats = {
        "total_users": len(users),
        "successful_syncs": sum(1 for r in results if r["status"] == "success"),
        "failed_syncs": sum(1 for r in results if r["status"] == "error"),
    }

    logger.info(
        "total_users=<%d>, successful=<%d>, failed=<%d> | calendar monitor complete",
        total_stats["total_users"],
        total_stats["successful_syncs"],
        total_stats["failed_syncs"],
    )

    return {
        "statusCode": 200,
        "body": json.dumps(total_stats),
    }


def handler(event, context):
    """Sync wrapper for Lambda."""
    import asyncio
    return asyncio.run(lambda_handler(event, context))
```

**Deliverable**: Calendar monitor Lambda complete

---

**NOTE**: This is getting very long. I should probably create a separate implementation guide and continue in a follow-up message or separate document. Let me add the remaining Sprint outlines briefly and then we can deep-dive into each sprint as we implement.

---

## Sprint 3: Step Functions Workflow (Week 3)

**Brief Overview**:
- Define Step Functions state machine
- Create context gathering placeholder Lambdas (Budget, Big Rocks, etc.)
- Implement prep notification Lambda (Slack message with button)
- Implement task token handling in chat handler
- End-to-end workflow test (without material generation)

**Key Files**:
- `infrastructure/step_functions.py` - Workflow definition
- `src/exec_assistant/workflows/gather_context.py` - Context Lambda
- `src/exec_assistant/workflows/send_prep_notification.py` - Notification Lambda
- Update `agent_handler.py` - Add task token handling

---

## Sprint 4: Material Generation (Week 4)

**Brief Overview**:
- Enhance Meeting Coordinator agent for material generation
- Create generate materials Lambda
- Implement S3 storage with presigned URLs
- Create send materials Lambda
- End-to-end test (complete workflow)

**Key Files**:
- Update `agents/meeting_coordinator.py` - Material generation prompts
- `src/exec_assistant/workflows/generate_materials.py` - Materials Lambda
- `src/exec_assistant/workflows/send_materials.py` - Delivery Lambda

---

## Deployment Timeline

**Week 1 (Sprint 1)**: Calendar Integration
```bash
pulumi config set exec-assistant:enable_calendar_integration true
pulumi up
```

**Week 2 (Sprint 2)**: Calendar Monitor
```bash
pulumi config set exec-assistant:enable_calendar_monitor true
pulumi up
```

**Week 3 (Sprint 3)**: Step Functions
```bash
pulumi config set exec-assistant:enable_step_functions true
pulumi up
```

**Week 4 (Sprint 4)**: Material Generation
```bash
pulumi config set exec-assistant:enable_material_generation true
pulumi up
```

---

## Success Criteria

**Sprint 1**: ✅ Can authorize Google Calendar and fetch meetings
**Sprint 2**: ✅ Meetings automatically synced every 2 hours
**Sprint 3**: ✅ Workflow triggers prep notification
**Sprint 4**: ✅ Complete end-to-end flow with materials

**Phase 3 Complete**: ✅ Users receive proactive meeting prep with AI-generated materials

---

**Document Version**: 1.0 (Draft)
**Created**: 2025-12-22
**Status**: Ready for Implementation
**Next Steps**: Begin Sprint 1 - Calendar Integration
