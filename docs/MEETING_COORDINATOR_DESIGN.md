# Meeting Coordinator Agent - Design Document

## Overview

The Meeting Coordinator is the most critical agent in the Executive Assistant system. It proactively prepares executives for meetings by monitoring their calendar, initiating interactive preparation sessions, gathering context from other agents, and generating comprehensive meeting materials.

## Core Responsibilities

### 1. Calendar Monitoring
- Poll calendar API every 2 hours via EventBridge scheduled rule
- Detect upcoming meetings within preparation window
- Classify meeting types based on title, description, and attendees
- Track which meetings have already been prepped

### 2. Proactive Preparation
- Trigger preparation workflow based on meeting type timing rules
- Send multi-channel notifications (Slack → SMS → Email fallback)
- Initiate interactive chat session for contextual questions
- Generate meeting materials (agenda, questions, context packets)

### 3. Context Gathering
- Query Budget Manager for financial data
- Query Big Rocks Manager for strategic initiative status
- Query Incident Manager for recent reliability issues
- Query Staffing Manager for headcount/hiring updates
- Query Decision Tracker for pending decisions
- Retrieve notes from previous similar meetings

### 4. Material Generation
- **Agenda**: Time-boxed topics with background context
- **Question Bank**: Questions to ask attendees based on meeting goals
- **Context Packets**: Relevant data, charts, metrics
- **Note Template**: Structured template for capturing meeting notes

### 5. Post-Meeting Processing
- Extract action items from notes
- Log decisions made during meeting
- Distribute meeting summary to attendees
- Update agent state (Big Rocks progress, budget concerns, etc.)
- Schedule follow-up items

## Meeting Type Classification

### Detection Rules

```yaml
meeting_types:
  leadership_meeting:
    keywords: ["leadership", "leadership team", "LT meeting", "staff"]
    min_attendees: 10
    prep_window_hours: 72

  one_on_one:
    keywords: ["1-1", "1:1", "one on one", "check-in", "catch up"]
    attendee_count: 2
    prep_window_hours: 24

  reliability_meeting:
    keywords: ["post-mortem", "incident review", "reliability", "RCA"]
    prep_window_hours: 2

  qbr:
    keywords: ["QBR", "quarterly business review", "quarterly review"]
    min_attendees: 15
    prep_window_hours: 336  # 2 weeks

  executive_meeting:
    keywords: ["CIO", "executive staff", "exec team"]
    min_attendees: 5
    prep_window_hours: 48

  default:
    prep_window_hours: 24
```

### Classification Logic

1. Extract meeting title, description, attendee list
2. Tokenize and normalize text (lowercase, remove punctuation)
3. Check keyword matches for each meeting type
4. Verify attendee count constraints
5. Select highest priority match (custom priority order)
6. Fall back to "default" if no matches

## Workflow Architecture

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────┐
│  EventBridge Scheduled Rule (every 2 hours)                 │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  Lambda: CalendarMonitor                                    │
│  - Fetch upcoming meetings (next 14 days)                   │
│  - Filter already-prepped meetings                          │
│  - Calculate prep trigger time for each                     │
│  - Meetings ready for prep → Trigger Step Function         │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  Step Function: MeetingPrepWorkflow                         │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ 1. ClassifyMeeting (Lambda)                             ││
│  │    - Determine meeting type                             ││
│  │    - Load prep question template                        ││
│  └─────────────────┬───────────────────────────────────────┘│
│                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ 2. SendPrepNotification (Lambda)                        ││
│  │    - Send Slack notification with prep link            ││
│  │    - Create chat session in DynamoDB                   ││
│  │    - Store session_id in workflow state                ││
│  └─────────────────┬───────────────────────────────────────┘│
│                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ 3. WaitForUserResponses (Task Token)                   ││
│  │    - Pause workflow until user completes chat          ││
│  │    - Timeout: 24 hours                                 ││
│  └─────────────────┬───────────────────────────────────────┘│
│                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ 4. GatherContext (Parallel Lambda invocations)         ││
│  │    - Budget Manager: Get spend/variance                ││
│  │    - Big Rocks Manager: Get initiative status          ││
│  │    - Incident Manager: Get recent incidents            ││
│  │    - Staffing Manager: Get headcount/pipeline          ││
│  │    - Decision Tracker: Get pending decisions           ││
│  └─────────────────┬───────────────────────────────────────┘│
│                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ 5. GenerateMaterials (Lambda + Bedrock)                ││
│  │    - Call Meeting Coordinator Agent                    ││
│  │    - Generate agenda, questions, context packets       ││
│  │    - Create note template                              ││
│  │    - Store in S3                                       ││
│  └─────────────────┬───────────────────────────────────────┘│
│                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ 6. SendPrepMaterials (Lambda)                          ││
│  │    - Send Slack message with materials link            ││
│  │    - Update meeting record as "prepped"                ││
│  └─────────────────┬───────────────────────────────────────┘│
│                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ 7. ScheduleFinalReminder (Lambda)                      ││
│  │    - Schedule EventBridge one-time rule                ││
│  │    - Trigger 2 hours before meeting                    ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

### Post-Meeting Workflow

```
User uploads meeting notes/voice memo
         │
         ▼
┌─────────────────────────────────────┐
│ Lambda: PostMeetingProcessor        │
│ - Transcribe voice (if needed)      │
│ - Call Agent to extract:            │
│   * Decisions made                  │
│   * Action items with owners        │
│   * Follow-up topics                │
└─────────┬───────────────────────────┘
          │
          ▼
┌─────────────────────────────────────┐
│ Update Other Agents                 │
│ - Decision Tracker: Log decisions   │
│ - Routine Manager: Add action items │
│ - HR Manager: Update 1-1 agendas    │
│ - Document Manager: Store notes     │
└─────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────┐
│ Send Summary to Attendees           │
│ - Email summary with action items   │
│ - Slack DM to each owner            │
└─────────────────────────────────────┘
```

## Data Models

### Meeting

```python
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class MeetingType(Enum):
    LEADERSHIP = "leadership_meeting"
    ONE_ON_ONE = "one_on_one"
    RELIABILITY = "reliability_meeting"
    QBR = "qbr"
    EXECUTIVE = "executive_meeting"
    DEFAULT = "default"

class MeetingStatus(Enum):
    DISCOVERED = "discovered"
    PREP_TRIGGERED = "prep_triggered"
    PREP_IN_PROGRESS = "prep_in_progress"
    PREP_COMPLETED = "prep_completed"
    REMINDER_SENT = "reminder_sent"
    COMPLETED = "completed"

@dataclass
class Meeting:
    """Meeting entity."""

    meeting_id: str              # Calendar event ID
    calendar_id: str             # Which calendar
    title: str
    description: str | None
    start_time: datetime
    end_time: datetime
    attendees: list[str]         # Email addresses
    location: str | None

    # Classification
    meeting_type: MeetingType
    classification_confidence: float

    # Preparation
    status: MeetingStatus
    prep_triggered_at: datetime | None
    prep_completed_at: datetime | None
    chat_session_id: str | None

    # Materials
    agenda_s3_key: str | None
    questions_s3_key: str | None
    context_s3_key: str | None
    notes_template_s3_key: str | None

    # Post-meeting
    notes_s3_key: str | None
    decisions: list[str]
    action_items: list[ActionItem]

    created_at: datetime
    updated_at: datetime
```

### ChatSession

```python
@dataclass
class ChatMessage:
    """Single message in chat session."""

    message_id: str
    role: str  # "agent" or "user"
    content: str
    timestamp: datetime

@dataclass
class ChatSession:
    """Interactive preparation chat session."""

    session_id: str
    meeting_id: str
    user_id: str
    meeting_type: MeetingType

    # Session state
    status: str  # "active", "completed", "expired"
    current_question_index: int
    questions: list[str]

    # Conversation
    messages: list[ChatMessage]
    user_responses: dict[str, str]  # question_id -> response

    # Step Function integration
    task_token: str | None  # For resuming Step Function

    started_at: datetime
    completed_at: datetime | None
    expires_at: datetime
```

### ActionItem

```python
@dataclass
class ActionItem:
    """Action item from a meeting."""

    action_id: str
    meeting_id: str
    description: str
    owner: str  # Email or user ID
    due_date: datetime | None
    status: str  # "pending", "in_progress", "completed"
    priority: str  # "high", "medium", "low"

    created_at: datetime
    completed_at: datetime | None
```

### MeetingMaterials

```python
@dataclass
class AgendaItem:
    """Single agenda item."""

    topic: str
    duration_minutes: int
    description: str
    background_context: str | None
    presenter: str | None

@dataclass
class MeetingMaterials:
    """Generated meeting preparation materials."""

    meeting_id: str

    # Agenda
    agenda_items: list[AgendaItem]
    total_duration_minutes: int

    # Questions
    questions_for_attendees: dict[str, list[str]]  # attendee -> questions
    questions_to_ask: list[str]

    # Context
    budget_summary: dict | None
    big_rocks_status: dict | None
    incident_summary: dict | None
    staffing_summary: dict | None
    pending_decisions: list[str]

    # Previous meetings
    last_meeting_notes: str | None
    last_meeting_action_items: list[ActionItem]

    generated_at: datetime
```

## Agent Tools

The Meeting Coordinator agent has these tools available:

### Calendar Tools

```python
@tool
def get_upcoming_meetings(
    calendar_id: str,
    start_time: datetime,
    end_time: datetime
) -> list[Meeting]:
    """Fetch upcoming meetings from calendar API."""

@tool
def get_meeting_details(meeting_id: str) -> Meeting:
    """Get full details for a specific meeting."""
```

### Context Gathering Tools

```python
@tool
def get_budget_status(cost_centers: list[str] | None = None) -> dict:
    """Get current budget status from Budget Manager agent."""

@tool
def get_big_rocks_status(rock_ids: list[str] | None = None) -> dict:
    """Get strategic initiative status from Big Rocks Manager."""

@tool
def get_recent_incidents(
    severity: str | None = None,
    days: int = 7
) -> list[dict]:
    """Get recent incidents from Incident Manager."""

@tool
def get_staffing_summary() -> dict:
    """Get headcount and hiring pipeline from Staffing Manager."""

@tool
def get_pending_decisions() -> list[dict]:
    """Get pending decisions from Decision Tracker."""
```

### Material Generation Tools

```python
@tool
def generate_agenda(
    meeting: Meeting,
    user_priorities: list[str],
    context: dict
) -> list[AgendaItem]:
    """Generate time-boxed agenda based on priorities and context."""

@tool
def generate_questions(
    meeting: Meeting,
    agenda: list[AgendaItem],
    context: dict
) -> dict[str, list[str]]:
    """Generate questions to ask during meeting."""

@tool
def create_note_template(
    meeting: Meeting,
    agenda: list[AgendaItem]
) -> str:
    """Create structured note-taking template."""
```

### Meeting Tools

```python
@tool
def get_previous_meeting_notes(
    meeting_type: MeetingType,
    attendees: list[str],
    limit: int = 1
) -> list[str]:
    """Retrieve notes from previous similar meetings."""

@tool
def extract_action_items(notes: str) -> list[ActionItem]:
    """Extract action items from meeting notes."""

@tool
def extract_decisions(notes: str) -> list[str]:
    """Extract decisions made during meeting."""
```

## Preparation Question Templates

### Leadership Team Meeting

```yaml
questions:
  - id: "priorities"
    text: "What are your top 3 priorities to discuss in this leadership meeting?"
    type: "text"
    required: true

  - id: "incidents"
    text: "I see we had {incident_count} incidents this week. Any specific concerns?"
    type: "text"
    required: false
    context_required: ["incident_summary"]

  - id: "budget"
    text: "Budget shows {variance_pct}% variance. Should we discuss this?"
    type: "yes_no"
    required: false
    context_required: ["budget_summary"]

  - id: "decisions"
    text: "Which of these pending decisions need to be finalized today?"
    type: "multi_select"
    options: "{pending_decisions}"
    required: false
    context_required: ["pending_decisions"]

  - id: "other"
    text: "Anything else on your mind for this meeting?"
    type: "text"
    required: false
```

### 1-1 Meeting

```yaml
questions:
  - id: "previous_actions"
    text: "Last 1-1 with {attendee_name} had {action_count} action items. Ready to review?"
    type: "yes_no"
    required: true
    context_required: ["previous_meeting"]

  - id: "feedback"
    text: "Any feedback you want to give {attendee_name}?"
    type: "text"
    required: false

  - id: "concerns"
    text: "Any concerns about {attendee_name} or their team?"
    type: "text"
    required: false

  - id: "goals"
    text: "{attendee_name} is at {goal_completion}% of annual goals. Discuss progress?"
    type: "yes_no"
    required: false
    context_required: ["hr_summary"]

  - id: "topics"
    text: "What topics do you want to cover today?"
    type: "text"
    required: true
```

## Storage Schema

### DynamoDB Tables

#### `exec-assistant-meetings`

```
Partition Key: meeting_id (String)
Sort Key: calendar_id (String)

Attributes:
- meeting_id
- calendar_id
- title
- start_time (ISO 8601)
- end_time
- attendees (List)
- meeting_type
- status
- prep_triggered_at
- prep_completed_at
- chat_session_id
- agenda_s3_key
- questions_s3_key
- context_s3_key
- notes_s3_key
- created_at
- updated_at

GSI: status-start_time-index
- Partition Key: status
- Sort Key: start_time
- Purpose: Query meetings by status in time order
```

#### `exec-assistant-chat-sessions`

```
Partition Key: session_id (String)

Attributes:
- session_id
- meeting_id
- user_id
- meeting_type
- status
- current_question_index
- questions (List)
- messages (List of Maps)
- user_responses (Map)
- task_token
- started_at
- completed_at
- expires_at

TTL: expires_at (auto-delete after 7 days)
```

### S3 Bucket Structure

```
s3://exec-assistant-documents/
├── meetings/
│   ├── {meeting_id}/
│   │   ├── agenda.json
│   │   ├── questions.json
│   │   ├── context.json
│   │   ├── notes_template.md
│   │   └── notes.md
│   └── ...
├── sessions/
│   └── {session_id}.json
└── ...
```

## Notification Templates

### Initial Prep Notification (Slack)

```json
{
  "blocks": [
    {
      "type": "header",
      "text": {
        "type": "plain_text",
        "text": "👋 Time to prep for your meeting"
      }
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*{meeting_title}*\n{meeting_time} ({time_until})\n{attendee_count} attendees"
      }
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "Let's prepare together. This will take about 5-10 minutes."
      }
    },
    {
      "type": "actions",
      "elements": [
        {
          "type": "button",
          "text": {
            "type": "plain_text",
            "text": "Start Prep"
          },
          "style": "primary",
          "action_id": "start_prep",
          "value": "{session_id}"
        },
        {
          "type": "button",
          "text": {
            "type": "plain_text",
            "text": "Remind me later"
          },
          "action_id": "snooze_prep",
          "value": "{session_id}"
        }
      ]
    }
  ]
}
```

### Final Reminder (2 hours before)

```json
{
  "blocks": [
    {
      "type": "header",
      "text": {
        "type": "plain_text",
        "text": "⏰ Meeting in 2 hours"
      }
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*{meeting_title}*\n{meeting_time}\n\n*Quick recap:*\n{agenda_summary}"
      }
    },
    {
      "type": "actions",
      "elements": [
        {
          "type": "button",
          "text": {
            "type": "plain_text",
            "text": "View Full Prep Materials"
          },
          "url": "{materials_url}",
          "style": "primary"
        }
      ]
    }
  ]
}
```

## Error Handling

### Calendar API Failures
- Retry with exponential backoff (3 attempts)
- Fall back to cached calendar data if available
- Alert user via Slack if calendar unavailable for >1 hour
- Continue with other meetings if one fails

### Chat Session Timeout
- If user doesn't complete chat within 24 hours:
  - Generate materials with default priorities
  - Send notification: "I went ahead and prepared materials based on context"
  - Mark session as expired

### Agent Context Failures
- Each context gathering call has 30s timeout
- If agent fails, continue with available context
- Log failure for monitoring
- Include note in materials: "Budget data unavailable"

### Step Function Failures
- Dead letter queue for failed executions
- Retry transient failures (3 attempts)
- Alert on repeated failures for same meeting
- Manual retry option via Slack command

## Performance Considerations

### Calendar Polling
- Batch API calls (fetch all meetings in single request)
- Cache meeting list for 2 hours
- Only process meetings that changed since last poll
- Limit to next 14 days of meetings

### Context Gathering
- Parallel Lambda invocations for all agents
- 30s timeout per agent
- Cache agent responses for 1 hour
- Don't block on slow agents

### Material Generation
- Bedrock streaming for faster perceived performance
- Cache templates by meeting type
- Pre-generate common sections (agenda format, note template)
- Store generated materials in S3 immediately

### Cost Optimization
- Use Bedrock on-demand (not provisioned throughput) initially
- Step Functions Express workflows for high volume
- Lambda reserved concurrency for calendar monitor
- DynamoDB on-demand capacity initially

## Security & Compliance

### Data Protection
- All calendar data encrypted in transit (TLS) and at rest (KMS)
- Meeting notes may contain PHI - use dedicated KMS key
- S3 bucket versioning enabled for audit trail
- CloudTrail logging for all API calls

### Access Control
- IAM roles with least privilege
- Lambda functions in private subnets
- No internet access except through VPC endpoints
- Calendar API credentials in Secrets Manager

### Audit Logging
- Log all meeting preparations (who, what, when)
- Log all context gathering calls
- Log all material generations
- Retention: 7 years (compliance requirement)

## Monitoring & Observability

### CloudWatch Metrics
- `MeetingsDiscovered` (count)
- `MeetingsPrepared` (count)
- `PrepDuration` (milliseconds)
- `ChatSessionCompletionRate` (percent)
- `ContextGatheringFailures` (count by agent)
- `CalendarAPILatency` (milliseconds)

### CloudWatch Alarms
- Calendar API failure rate >10%
- Prep completion rate <80%
- Step Function execution failures >5/hour
- Context gathering timeout rate >20%

### OpenTelemetry Traces
- End-to-end trace for each meeting prep
- Spans for each agent context call
- Spans for Bedrock API calls
- Custom attributes: meeting_type, user_id, session_id

## Future Enhancements

1. **Voice-based prep**: Accept voice responses via phone call
2. **Mobile app**: Dedicated prep interface
3. **Smart scheduling**: Suggest prep time based on user patterns
4. **Auto-generated slides**: Create presentation from context
5. **Real-time collaboration**: Multiple users prep together
6. **ML-based prioritization**: Learn what topics matter most
7. **Integration with meeting recording**: Auto-transcribe and extract notes
8. **Predictive questions**: Anticipate what user will be asked
