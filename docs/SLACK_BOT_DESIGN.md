# Slack Bot Interface - Technical Design

## Overview

The Slack bot provides the primary user interface for the Executive Assistant system. It handles interactive meeting preparation sessions, delivers notifications, accepts voice/text notes, and provides command-based interactions with all agents.

## Architecture

### Bot Configuration

**Slack App Setup:**
- **App Type**: Socket Mode (for development) → Events API (for production)
- **Bot Token Scopes**:
  - `chat:write` - Send messages as bot
  - `im:write` - Send DMs to users
  - `im:history` - Read DM history
  - `users:read` - Get user information
  - `files:read` - Read uploaded files (notes, documents)
  - `files:write` - Upload files (meeting materials)
- **User Token Scopes**:
  - `calendar:read` - Read user's calendar (if using Slack calendar)
- **Event Subscriptions**:
  - `message.im` - DMs sent to bot
  - `app_mention` - @bot mentions
- **Interactivity**: Enable for buttons, modals, shortcuts

### Component Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Slack Platform                        │
│  - User sends message                                        │
│  - User clicks button                                        │
│  - User submits modal                                        │
└────────────────────┬────────────────────────────────────────┘
                     │ HTTPS POST
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  API Gateway + Lambda: SlackWebhookHandler                  │
│  - Verify Slack signature                                   │
│  - Parse event type                                          │
│  - Route to appropriate handler                             │
└────────────────────┬────────────────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
        ▼            ▼            ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│   Message   │ │  Button     │ │   Modal     │
│   Handler   │ │  Handler    │ │   Handler   │
└──────┬──────┘ └──────┬──────┘ └──────┬──────┘
       │               │               │
       └───────────────┼───────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│            ChatSessionManager                                │
│  - Load session from DynamoDB                                │
│  - Update session state                                      │
│  - Invoke appropriate agent                                  │
│  - Generate response                                         │
│  - Save session state                                        │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│            Slack API Client                                  │
│  - Send response message                                     │
│  - Update original message                                   │
│  - Post ephemeral messages                                   │
└─────────────────────────────────────────────────────────────┘
```

## Interactive Chat Session Flow

### Session Lifecycle

```
1. User receives notification
   ↓
2. User clicks "Start Prep" button
   ↓
3. SlackWebhookHandler creates/loads ChatSession
   ↓
4. Agent asks first question
   ↓
5. User responds with text
   ↓
6. Agent acknowledges, asks next question
   ↓
7. Repeat until all questions answered
   ↓
8. Agent generates materials
   ↓
9. Agent sends completion message with materials link
   ↓
10. ChatSession marked as completed
    ↓
11. Step Function resumed with user responses
```

### Session State Machine

```python
from enum import Enum

class SessionState(Enum):
    """Chat session states."""

    CREATED = "created"           # Session created, waiting for user
    ACTIVE = "active"             # User engaged, answering questions
    WAITING = "waiting"           # Waiting for user response
    PROCESSING = "processing"     # Agent processing response
    COMPLETED = "completed"       # All questions answered
    EXPIRED = "expired"           # Timeout reached
    CANCELLED = "cancelled"       # User cancelled

# State transitions
VALID_TRANSITIONS = {
    SessionState.CREATED: [SessionState.ACTIVE, SessionState.EXPIRED],
    SessionState.ACTIVE: [SessionState.WAITING, SessionState.COMPLETED, SessionState.CANCELLED],
    SessionState.WAITING: [SessionState.PROCESSING, SessionState.EXPIRED, SessionState.CANCELLED],
    SessionState.PROCESSING: [SessionState.ACTIVE, SessionState.COMPLETED],
    SessionState.COMPLETED: [],  # Terminal state
    SessionState.EXPIRED: [],    # Terminal state
    SessionState.CANCELLED: [],  # Terminal state
}
```

## Request Handling

### Webhook Handler (Lambda)

```python
import json
import hmac
import hashlib
from datetime import datetime
from typing import Any

def verify_slack_signature(
    request_body: str,
    timestamp: str,
    signature: str,
    signing_secret: str
) -> bool:
    """Verify request is from Slack.

    Args:
        request_body: Raw request body
        timestamp: X-Slack-Request-Timestamp header
        signature: X-Slack-Signature header
        signing_secret: Slack signing secret

    Returns:
        True if signature is valid
    """
    # Prevent replay attacks (>5 min old)
    if abs(datetime.now().timestamp() - int(timestamp)) > 300:
        return False

    # Compute signature
    sig_basestring = f"v0:{timestamp}:{request_body}"
    computed_sig = "v0=" + hmac.new(
        signing_secret.encode(),
        sig_basestring.encode(),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(computed_sig, signature)


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Handle Slack webhook events.

    Args:
        event: API Gateway event
        context: Lambda context

    Returns:
        API Gateway response
    """
    # Verify signature
    body = event["body"]
    timestamp = event["headers"]["X-Slack-Request-Timestamp"]
    signature = event["headers"]["X-Slack-Signature"]

    if not verify_slack_signature(body, timestamp, signature, SIGNING_SECRET):
        return {"statusCode": 401, "body": "Invalid signature"}

    # Parse event
    payload = json.loads(body)

    # Handle URL verification challenge
    if payload.get("type") == "url_verification":
        return {
            "statusCode": 200,
            "body": json.dumps({"challenge": payload["challenge"]})
        }

    # Route to handler
    event_type = payload.get("type")

    if event_type == "event_callback":
        handle_event(payload["event"])
    elif event_type == "block_actions":
        handle_button_click(payload)
    elif event_type == "view_submission":
        handle_modal_submission(payload)

    # Acknowledge receipt
    return {"statusCode": 200, "body": ""}
```

### Message Handler

```python
from strands.agent import Agent
from strands.models import BedrockModel

def handle_message(event: dict[str, Any]) -> None:
    """Handle incoming message to bot.

    Args:
        event: Slack message event
    """
    user_id = event["user"]
    channel = event["channel"]  # DM channel ID
    text = event["text"]
    thread_ts = event.get("thread_ts") or event["ts"]

    # Load active session for this user
    session = get_active_session(user_id)

    if session is None:
        # No active session - check for commands
        if text.startswith("/"):
            handle_command(user_id, channel, text)
        else:
            # Helpful message
            send_message(
                channel,
                "Hi! I'm your Executive Assistant. Here are some things I can help with:\n"
                "• Meeting preparation (I'll notify you automatically)\n"
                "• `/meetings` - View upcoming meetings\n"
                "• `/big-rocks` - Check strategic initiative status\n"
                "• `/budget` - Get budget summary\n"
                "• `/incidents` - Recent incidents summary"
            )
        return

    # Active session - process response
    process_session_message(session, user_id, channel, text, thread_ts)


def process_session_message(
    session: ChatSession,
    user_id: str,
    channel: str,
    text: str,
    thread_ts: str
) -> None:
    """Process user message in active chat session.

    Args:
        session: Active chat session
        user_id: Slack user ID
        channel: DM channel ID
        text: User's message
        thread_ts: Thread timestamp for replies
    """
    # Update session
    session.state = SessionState.PROCESSING
    session.messages.append(ChatMessage(
        message_id=generate_id(),
        role="user",
        content=text,
        timestamp=datetime.now()
    ))
    save_session(session)

    # Get current question
    current_question = session.questions[session.current_question_index]

    # Store response
    session.user_responses[current_question["id"]] = text

    # Check if this was the last question
    if session.current_question_index >= len(session.questions) - 1:
        # All questions answered
        session.state = SessionState.COMPLETED
        session.completed_at = datetime.now()
        save_session(session)

        # Send completion message
        send_message(
            channel,
            "Perfect! I'm generating your meeting materials now... (this may take a minute)",
            thread_ts=thread_ts
        )

        # Resume Step Function with responses
        resume_step_function(session.task_token, session.user_responses)

    else:
        # Move to next question
        session.current_question_index += 1
        session.state = SessionState.WAITING
        save_session(session)

        # Send next question
        next_question = session.questions[session.current_question_index]
        send_message(
            channel,
            format_question(next_question, session.context),
            thread_ts=thread_ts
        )
```

### Button Click Handler

```python
def handle_button_click(payload: dict[str, Any]) -> None:
    """Handle interactive button clicks.

    Args:
        payload: Slack interaction payload
    """
    user_id = payload["user"]["id"]
    action = payload["actions"][0]
    action_id = action["action_id"]
    action_value = action["value"]

    if action_id == "start_prep":
        # Start meeting prep session
        session_id = action_value
        session = load_session(session_id)

        if session is None:
            send_ephemeral_message(
                payload["channel"]["id"],
                user_id,
                "Sorry, this prep session has expired."
            )
            return

        # Activate session
        session.state = SessionState.ACTIVE
        session.current_question_index = 0
        save_session(session)

        # Send first question
        first_question = session.questions[0]
        send_message(
            payload["channel"]["id"],
            format_question(first_question, session.context),
            thread_ts=payload["message"]["ts"]
        )

        # Update original message to show started
        update_message(
            payload["channel"]["id"],
            payload["message"]["ts"],
            "✅ Prep session started!"
        )

    elif action_id == "snooze_prep":
        # Snooze for 2 hours
        session_id = action_value
        reschedule_notification(session_id, hours=2)

        update_message(
            payload["channel"]["id"],
            payload["message"]["ts"],
            "⏰ I'll remind you again in 2 hours."
        )

    elif action_id == "view_materials":
        # Send materials link
        meeting_id = action_value
        materials_url = generate_materials_url(meeting_id)

        send_ephemeral_message(
            payload["channel"]["id"],
            user_id,
            f"Here are your meeting materials: {materials_url}"
        )
```

## Message Formatting

### Question Formatting

```python
def format_question(question: dict[str, Any], context: dict[str, Any]) -> str:
    """Format question with context interpolation.

    Args:
        question: Question definition
        context: Context data for interpolation

    Returns:
        Formatted question text
    """
    text = question["text"]

    # Interpolate context variables
    # Example: "Budget shows {variance_pct}% variance"
    for key, value in context.items():
        placeholder = f"{{{key}}}"
        if placeholder in text:
            text = text.replace(placeholder, str(value))

    # Add question type-specific formatting
    if question["type"] == "yes_no":
        return f"{text}\n\n*Reply with:* Yes or No"

    elif question["type"] == "multi_select":
        options = question.get("options", [])
        if isinstance(options, str) and options.startswith("{"):
            # Load from context
            options_key = options[1:-1]  # Remove {}
            options = context.get(options_key, [])

        options_text = "\n".join(f"{i+1}. {opt}" for i, opt in enumerate(options))
        return f"{text}\n\n{options_text}\n\n*Reply with numbers* (e.g., \"1, 3, 5\")"

    elif question["type"] == "text":
        return text

    return text


def format_materials_ready_message(
    meeting: Meeting,
    materials: MeetingMaterials
) -> dict[str, Any]:
    """Format Slack message for completed prep materials.

    Args:
        meeting: Meeting details
        materials: Generated materials

    Returns:
        Slack message payload
    """
    # Generate agenda summary
    agenda_summary = "\n".join(
        f"• {item.topic} ({item.duration_minutes} min)"
        for item in materials.agenda_items[:3]
    )
    if len(materials.agenda_items) > 3:
        agenda_summary += f"\n• ... and {len(materials.agenda_items) - 3} more"

    # Generate materials URL
    materials_url = generate_materials_url(meeting.meeting_id)

    return {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "✅ Your meeting prep is ready!"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{meeting.title}*\n{meeting.start_time.strftime('%A, %B %d at %I:%M %p')}"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*📋 Agenda Preview*\n{agenda_summary}"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*📊 Context Gathered*\n"
                           f"• {len(materials.questions_to_ask)} questions prepared\n"
                           f"• Budget, incidents, and Big Rocks status included\n"
                           f"• {len(materials.last_meeting_action_items)} action items from last meeting"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "View Full Materials"
                        },
                        "url": materials_url,
                        "style": "primary"
                    }
                ]
            }
        ]
    }
```

## Slash Commands

### Command Registration

```
/meetings - View upcoming meetings
/big-rocks - Check Big Rocks status
/budget - Get budget summary
/incidents - Recent incidents
/decisions - Pending decisions
/staffing - Headcount and hiring status
/prep <meeting_id> - Manually trigger meeting prep
```

### Command Handler

```python
def handle_command(user_id: str, channel: str, text: str) -> None:
    """Handle slash command.

    Args:
        user_id: User who invoked command
        channel: Channel where command was invoked
        text: Command text
    """
    parts = text.strip().split()
    command = parts[0].lower()
    args = parts[1:] if len(parts) > 1 else []

    if command == "/meetings":
        handle_meetings_command(user_id, channel, args)

    elif command == "/big-rocks":
        handle_big_rocks_command(user_id, channel)

    elif command == "/budget":
        handle_budget_command(user_id, channel)

    elif command == "/incidents":
        handle_incidents_command(user_id, channel, args)

    elif command == "/decisions":
        handle_decisions_command(user_id, channel)

    elif command == "/staffing":
        handle_staffing_command(user_id, channel)

    elif command == "/prep":
        if not args:
            send_message(channel, "Usage: `/prep <meeting_id>`")
            return
        handle_prep_command(user_id, channel, args[0])

    else:
        send_message(channel, f"Unknown command: {command}")


def handle_meetings_command(
    user_id: str,
    channel: str,
    args: list[str]
) -> None:
    """Handle /meetings command.

    Args:
        user_id: User ID
        channel: Channel ID
        args: Command arguments
    """
    # Get upcoming meetings
    meetings = get_upcoming_meetings_for_user(user_id, days=7)

    if not meetings:
        send_message(channel, "You have no upcoming meetings in the next 7 days.")
        return

    # Format meetings
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "📅 Your Upcoming Meetings"
            }
        }
    ]

    for meeting in meetings[:10]:  # Limit to 10
        status_emoji = {
            MeetingStatus.PREP_COMPLETED: "✅",
            MeetingStatus.PREP_IN_PROGRESS: "⏳",
            MeetingStatus.DISCOVERED: "📋"
        }.get(meeting.status, "📋")

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{status_emoji} *{meeting.title}*\n"
                        f"{meeting.start_time.strftime('%A, %B %d at %I:%M %p')}\n"
                        f"{len(meeting.attendees)} attendees"
            },
            "accessory": {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "Prep Now"
                },
                "action_id": "start_prep",
                "value": meeting.meeting_id
            }
        })

    send_message(channel, blocks=blocks)
```

## File Upload Handling

### Meeting Notes Upload

```python
def handle_file_shared(event: dict[str, Any]) -> None:
    """Handle file upload (meeting notes).

    Args:
        event: Slack file_shared event
    """
    file_id = event["file_id"]
    user_id = event["user_id"]

    # Download file
    file_info = slack_client.files_info(file=file_id)
    file_content = download_file(file_info["url_private"])

    # Check if this is meeting notes
    # User should mention meeting ID in message or we detect from context
    channel = event.get("channel_id")

    # Ask user which meeting these notes are for
    recent_meetings = get_recent_meetings_for_user(user_id, days=1)

    if len(recent_meetings) == 1:
        # Only one recent meeting - assume these notes are for it
        process_meeting_notes(recent_meetings[0].meeting_id, file_content)
        send_message(
            channel,
            f"✅ Got your notes for *{recent_meetings[0].title}*. Processing now..."
        )

    else:
        # Ask which meeting
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "Which meeting are these notes for?"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": meeting.title
                        },
                        "action_id": "notes_for_meeting",
                        "value": f"{meeting.meeting_id}|{file_id}"
                    }
                    for meeting in recent_meetings[:5]
                ]
            }
        ]
        send_message(channel, blocks=blocks)
```

## Agent Integration

### Invoking Agents from Slack

```python
from strands.agent import Agent
from strands.models import BedrockModel
from strands.session import S3SessionManager

def invoke_agent_from_slack(
    agent_name: str,
    user_id: str,
    prompt: str,
    session_id: str | None = None
) -> str:
    """Invoke agent and return response.

    Args:
        agent_name: Which agent to invoke
        user_id: Slack user ID (for session)
        prompt: User's prompt/question
        session_id: Optional session ID to continue conversation

    Returns:
        Agent response text
    """
    # Load agent
    model = BedrockModel(
        model_id="anthropic.claude-3-sonnet-20240229-v1:0",
        region="us-east-1"
    )

    session_manager = S3SessionManager(
        bucket_name="exec-assistant-sessions",
        region="us-east-1"
    )

    agent = load_agent(agent_name, model, session_manager)

    # Create session ID if needed
    if session_id is None:
        session_id = f"slack-{user_id}-{generate_id()}"

    # Invoke agent
    result = agent.invoke_async(
        prompt=prompt,
        session_id=session_id,
        user_id=user_id
    )

    return result.content
```

## Error Handling

### Slack API Errors

```python
from slack_sdk.errors import SlackApiError

def send_message_with_retry(
    channel: str,
    text: str | None = None,
    blocks: list[dict] | None = None,
    thread_ts: str | None = None,
    max_retries: int = 3
) -> None:
    """Send Slack message with retry logic.

    Args:
        channel: Channel ID
        text: Plain text message
        blocks: Rich blocks message
        thread_ts: Thread to reply to
        max_retries: Max retry attempts
    """
    for attempt in range(max_retries):
        try:
            slack_client.chat_postMessage(
                channel=channel,
                text=text,
                blocks=blocks,
                thread_ts=thread_ts
            )
            return

        except SlackApiError as e:
            if e.response["error"] == "rate_limited":
                # Rate limited - wait and retry
                retry_after = int(e.response.headers.get("Retry-After", 1))
                time.sleep(retry_after)
                continue

            elif e.response["error"] == "channel_not_found":
                # Channel doesn't exist - don't retry
                logger.error("channel=<%s> | slack channel not found", channel)
                return

            elif attempt < max_retries - 1:
                # Transient error - retry with backoff
                time.sleep(2 ** attempt)
                continue

            else:
                # Max retries exceeded
                logger.error(
                    "channel=<%s>, error=<%s> | failed to send slack message",
                    channel,
                    e.response["error"]
                )
                raise
```

### Session State Errors

```python
def recover_session_state(session_id: str) -> ChatSession | None:
    """Attempt to recover corrupted session state.

    Args:
        session_id: Session ID

    Returns:
        Recovered session or None if unrecoverable
    """
    try:
        session = load_session(session_id)
        return session

    except Exception as e:
        logger.error(
            "session_id=<%s>, error=<%s> | failed to load session",
            session_id,
            str(e)
        )

        # Attempt recovery from Step Function state
        try:
            sf_state = get_step_function_state(session_id)
            if sf_state:
                session = reconstruct_session_from_sf_state(sf_state)
                save_session(session)
                return session

        except Exception as sf_error:
            logger.error(
                "session_id=<%s>, error=<%s> | failed to recover from step function",
                session_id,
                str(sf_error)
            )

        return None
```

## Testing Strategy

### Unit Tests

```python
import pytest
from unittest.mock import Mock, patch

def test_verify_slack_signature():
    """Test Slack signature verification."""
    signing_secret = "test_secret"
    timestamp = "1234567890"
    body = '{"type":"event_callback"}'

    # Compute valid signature
    sig = compute_signature(body, timestamp, signing_secret)

    assert verify_slack_signature(body, timestamp, sig, signing_secret) is True
    assert verify_slack_signature(body, timestamp, "invalid", signing_secret) is False


def test_format_question_with_context():
    """Test question formatting with context interpolation."""
    question = {
        "text": "Budget shows {variance_pct}% variance",
        "type": "yes_no"
    }
    context = {"variance_pct": 15}

    result = format_question(question, context)

    assert "15%" in result
    assert "Yes or No" in result


@patch("slack_sdk.WebClient.chat_postMessage")
def test_send_message(mock_post):
    """Test sending Slack message."""
    send_message("C12345", "Test message")

    mock_post.assert_called_once_with(
        channel="C12345",
        text="Test message",
        blocks=None,
        thread_ts=None
    )
```

### Integration Tests

```python
def test_full_prep_session_flow(slack_client, dynamodb):
    """Test complete meeting prep session flow."""
    # Setup
    user_id = "U12345"
    meeting_id = "meeting_123"

    # Create session
    session_id = create_prep_session(meeting_id, user_id)

    # Simulate button click to start
    handle_button_click({
        "user": {"id": user_id},
        "actions": [{"action_id": "start_prep", "value": session_id}],
        "channel": {"id": "D12345"}
    })

    # Verify first question sent
    session = load_session(session_id)
    assert session.state == SessionState.WAITING
    assert session.current_question_index == 0

    # Simulate user responses
    for i, question in enumerate(session.questions):
        handle_message({
            "user": user_id,
            "channel": "D12345",
            "text": f"Answer to question {i+1}"
        })

    # Verify session completed
    final_session = load_session(session_id)
    assert final_session.state == SessionState.COMPLETED
    assert len(final_session.user_responses) == len(session.questions)
```

## Performance Optimization

### Message Batching
- Queue multiple messages and send in batch
- Reduces API calls and rate limit issues
- Use SQS for queuing outbound messages

### Caching
- Cache user info (name, timezone) for 1 hour
- Cache channel IDs for DMs
- Cache formatted templates

### Async Processing
- Process file uploads asynchronously
- Don't block webhook response on long operations
- Use SNS to trigger background processing

## Monitoring

### CloudWatch Metrics
- `SlackMessagesReceived` (count)
- `SlackMessagesSent` (count)
- `SlackAPIErrors` (count by error type)
- `ChatSessionsCreated` (count)
- `ChatSessionsCompleted` (count)
- `ChatSessionCompletionRate` (percent)
- `ChatSessionDuration` (seconds)

### CloudWatch Alarms
- Slack API error rate >5%
- Session completion rate <75%
- Webhook response time >3 seconds

### Logging
- Log all incoming events (sanitized)
- Log all API calls to Slack
- Log session state transitions
- Include session_id, user_id, meeting_id in all logs

## Security

### Signature Verification
- Always verify Slack signature before processing
- Reject requests older than 5 minutes (replay attack prevention)
- Use constant-time comparison for signature check

### Data Protection
- Don't log full message content (may contain PHI)
- Encrypt session data at rest in DynamoDB
- Use VPC endpoints for Slack API calls (if possible)
- Store Slack tokens in Secrets Manager

### Rate Limiting
- Respect Slack rate limits (1 message/second per channel)
- Implement exponential backoff
- Queue messages if rate limited

## Deployment

### Infrastructure (Pulumi)
```python
# Lambda for webhook handler
webhook_lambda = aws.lambda_.Function(
    "slack-webhook-handler",
    runtime="python3.11",
    handler="slack_bot.webhook_handler.lambda_handler",
    code=pulumi.AssetArchive({
        ".": pulumi.FileArchive("../dist/slack_bot.zip")
    }),
    environment={
        "variables": {
            "SLACK_SIGNING_SECRET": slack_signing_secret,
            "SLACK_BOT_TOKEN": slack_bot_token,
            "SESSIONS_TABLE": sessions_table.name
        }
    },
    timeout=30
)

# API Gateway for Slack webhook
api = aws.apigatewayv2.Api(
    "slack-webhook-api",
    protocol_type="HTTP",
    route_key="POST /slack/events"
)
```

### Slack App Manifest
```yaml
display_information:
  name: Executive Assistant
  description: AI-powered executive assistant
  background_color: "#2c2d30"

features:
  bot_user:
    display_name: Executive Assistant
    always_online: true

oauth_config:
  scopes:
    bot:
      - chat:write
      - im:write
      - im:history
      - users:read
      - files:read
      - files:write

settings:
  event_subscriptions:
    request_url: https://api.example.com/slack/events
    bot_events:
      - message.im
      - app_mention
      - file_shared

  interactivity:
    is_enabled: true
    request_url: https://api.example.com/slack/interactions

  org_deploy_enabled: false
  socket_mode_enabled: false
```
