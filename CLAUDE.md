# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an Executive Assistant multi-agent system for operations leadership. The system uses AI agents to manage organizational activities including budget tracking, strategic planning (Big Rocks), HR processes, incident management, meeting coordination, and decision tracking.

**Tech Stack:**
- **Agent Framework**: Strands Agent SDK (Python) - https://github.com/strands-agents/sdk-python
- **Infrastructure**: Pulumi (AWS: Bedrock, Lambda, DynamoDB, EventBridge, S3, SNS/SQS, Step Functions)
- **Communication**: Slack API (primary), Twilio (SMS), SendGrid/SES (email)


## Architecture

### Multi-Agent System Design

The system consists of 9 specialized agents coordinated by an orchestrator:
1. **Orchestrator** - Coordinates all specialized agents
2. **Budget Manager** - Budget tracking, forecasting, alerts
3. **Big Rocks Manager** - Strategic priority tracking
4. **HR Manager** - 1-1s, goal setting, performance reviews
5. **Meeting Coordinator** - **Critical**: Proactive meeting preparation with scheduled calendar monitoring
6. **Incident Manager** - Post-mortems, reliability tracking
7. **Staffing Manager** - Headcount, hiring pipeline
8. **Decision Tracker** - Decision logging and ADRs
9. **Routine Manager** - Daily/weekly/monthly task scheduling
10. **Document Manager** - Document organization and retrieval

### Critical Workflow: Meeting Preparation

The **Meeting Coordinator** agent implements a proactive meeting preparation system:
- **EventBridge** scheduled task checks calendar every 2 hours
- Triggers **24-48 hours before** meetings (configurable per meeting type)
- Sends **Slack/SMS notification** to start interactive prep session
- Agent asks **contextual questions** based on meeting type and attendees
- Generates **agenda, question bank, context packets, note templates**
- **Post-meeting**: Extracts action items and distributes notes
- Integrates with all other agents to gather relevant context

This is the most complex workflow involving:
- AWS Step Functions for orchestration
- Interactive chat sessions via Slack bot
- Calendar API integration (Google/Microsoft)
- Multi-agent coordination for context gathering

### Project Structure (Planned)

```
exec_assistant/
├── agents/              # Agent implementations using Strands SDK
├── interfaces/          # Slack bot, notification routing, chat sessions
├── workflows/           # Step Functions workflows (meeting prep, incident response)
├── infrastructure/      # Pulumi IaC for AWS resources
├── shared/              # Models, config, calendar integration, utilities
├── config/              # YAML configs for agents, meeting types, notifications
└── tests/               # Unit and integration tests
```

## Task Workflow

### Branch Code and Create PR After Changes Are Ready
**MAKE SURE YOU BRANCH OR ARE WITHIN A BRANCH BEFORE YOU MAKE ANY CHANGES**
**Create a Pull Request with insightful comments**

### Use Sub-Agents for Python Development and Infrastructure-as-Code
**Use the python-dev-expert agent when developing any python**
**Use the pulumi-infrastructure-manager agent when developing any changes within the ./infrastructure/ folder**


## Strands SDK Patterns (CRITICAL)

Key requirements:

### Agent Implementation
```python
from strands.agent import Agent
from strands.models import BedrockModel
from strands.tools import tool
from strands.session import S3SessionManager

# Use Bedrock for all agents
model = BedrockModel(
    model_id="anthropic.claude-3-sonnet-20240229-v1:0",
    region="us-east-1"
)

# Use S3 session manager for production
session_manager = S3SessionManager(
    bucket_name="exec-assistant-sessions",
    region="us-east-1"
)

# Define tools with @tool decorator
@tool
def get_budget_status(cost_center: str) -> dict:
    """Get current budget status for a cost center.

    Args:
        cost_center: Name of the cost center

    Returns:
        Dict with budget status including spend, allocation, variance
    """
    pass
```

### Multi-Agent Orchestration
Use **Graph-based orchestration** (`strands.multiagent.graph`) for Meeting Coordinator workflows:
- Structured, predictable flows
- Clear state transitions
- Integration with AWS Step Functions

Use **Swarm pattern** (`strands.multiagent.swarm`) for dynamic agent collaboration when needed.

### Code Quality Requirements

**Logging** (structured format):
```python
logger.debug("user_id=<%s>, meeting_id=<%s> | preparing meeting materials", user_id, meeting_id)
```
- Field-value pairs first: `field=<value>`
- Human message after pipe: `| message`
- Use `%s` interpolation (NOT f-strings)
- Lowercase, no punctuation

**Type Annotations** (mandatory):
```python
def process_meeting(meeting_id: str, prep_hours: int | None = None) -> MeetingPrepResult:
    ...
```

**Docstrings** (Google style):
```python
def schedule_prep_notification(meeting_id: str, prep_hours: int) -> None:
    """Schedule a meeting preparation notification.

    Args:
        meeting_id: Unique identifier for the meeting
        prep_hours: Hours before meeting to send notification

    Raises:
        ValueError: If prep_hours is negative
    """
```

**Import Order** (auto-formatted by ruff):
1. Standard library
2. Third-party
3. Local application

## Configuration Files

### `config/agents.yaml`
Agent-specific configuration including:
- `meeting_coordinator.calendar_check_schedule`: EventBridge cron for calendar monitoring
- `meeting_coordinator.prep_timing`: Hours before meeting to trigger prep (by meeting type)
- `meeting_coordinator.notification_channels`: Priority order (slack, sms, email)
- `meeting_coordinator.meeting_types`: Keywords and rules for detecting meeting types

### `config/meeting_types.yaml`
Meeting type definitions with prep questions, context requirements, and timing rules.

### `config/notification_rules.yaml`
User notification preferences and routing rules.

## Environment Variables

Required environment variables (see README.md for complete list):
```bash
# AWS
AWS_REGION=us-east-1
BEDROCK_MODEL=anthropic.claude-3-sonnet-20240229-v1:0

# Calendar (Google or Microsoft)
CALENDAR_API_TYPE=google
CALENDAR_OAUTH_CLIENT_ID=...
CALENDAR_OAUTH_CLIENT_SECRET=...

# Slack (primary notification channel)
SLACK_BOT_TOKEN=xoxb-...
SLACK_USER_ID=U123456789

# Optional: Twilio (SMS), SendGrid (email)
```

## Organization Context

This system is designed for **operations and infrastructure leadership**. Context matters:

**Big Rocks Examples:**
- "Migrate 40% of legacy workloads to cloud-native architecture"
- "Achieve 99.99% uptime for critical systems"
- "Complete security compliance certifications for all production environments"

**Meeting Types:**
- Leadership Team Meetings (weekly)
- 1-1s with direct reports (bi-weekly)
- Reliability Meetings (post-incident reviews)
- Quarterly Business Reviews (QBRs)
- Executive Staff Meetings with CIO

**Security & Compliance:**
- Data encryption at rest/transit
- Audit logging for all agent actions
- Secure credential management
- Role-based access control

## Integration Points

- **Calendar API**: Google Calendar or Microsoft Graph
- **Incident Management**: PagerDuty, ServiceNow
- **Financial Systems**: AWS Cost Explorer
- **Communication**: Slack API, Twilio, SendGrid/SES
- **Document Storage**: Google Drive/SharePoint, S3

## Development Workflow

When implementing agents or workflows:

1. **Follow Strands SDK patterns** [from](https://github.com/strands-agents/sdk-python)
2. **Start with data models** in `shared/models.py` (Meeting, BigRock, Incident, etc.)
3. **Implement agents** with proper `@tool` decorators
4. **Use S3SessionManager** for production, FileSessionManager for local dev
5. **Write tests** mirroring source structure (unit tests in `tests/`, integration in `tests_integ/`)
6. **Add Pulumi infrastructure** after agent logic is working locally
7. **Configure EventBridge** for scheduled tasks (calendar checks, routine reminders)
8. **Test end-to-end** with real Slack/calendar integrations

## Key Design Decisions

1. **EventBridge for scheduling**: All time-based triggers use EventBridge scheduled rules
2. **Step Functions for complex workflows**: Meeting prep uses Step Functions for reliability
3. **Slack as primary UX**: Interactive prep sessions happen in Slack DMs
4. **Graph-based agent orchestration**: Predictable workflows use graph pattern
5. **S3 for session persistence**: Agent sessions stored in S3 for Lambda compatibility
6. **DynamoDB for state**: Meeting state, action items, decisions stored in DynamoDB
7. **Bedrock for all LLM calls**: Consistent model provider across all agents

## Testing Strategy

### Overview
- **Unit tests**: Mock AWS services (moto), use Strands fixtures
- **Integration tests**: Real Bedrock calls, require AWS credentials
- **End-to-end tests**: Full workflow tests with calendar/Slack mocks
- **Test data**: Use realistic infrastructure scenarios (incidents, budgets, org structure)

### Local Development Testing (CRITICAL)

**Environment Setup:**
The project uses environment-based session management to enable efficient local testing:
- **Local development** (`ENV=local`): Uses `FileSessionManager` with `.sessions/` directory
- **Production** (`ENV=prod`): Uses `S3SessionManager` with S3 bucket
- Session manager is created per-request with the specific `session_id`

**Testing Workflow:**

1. **Quick Mock Testing** (no AWS credentials needed):
   ```bash
   source .venv/bin/activate
   export ENV=local
   pytest tests/test_meeting_coordinator.py -v
   ```

2. **Integration Testing with Real Bedrock** (requires AWS credentials):
   ```bash
   source .venv/bin/activate
   export ENV=local
   export AWS_BEDROCK_ENABLED=1
   # Ensure AWS credentials are configured (aws configure or env vars)
   pytest tests/test_meeting_coordinator.py -v -m integration
   ```

3. **Interactive Local Testing** (best for development iteration):
   ```bash
   source .venv/bin/activate
   export ENV=local
   # Optional: export AWS_BEDROCK_ENABLED=1 for real Bedrock calls
   python scripts/test_agent_local.py
   ```
   This launches an interactive chat session where you can test the agent conversationally.

4. **Quick Example Test** (non-interactive):
   ```bash
   python scripts/test_agent_local.py --example
   ```

**Important Notes:**
- Session files are stored in `.sessions/` for local testing (gitignored)
- Always set `ENV=local` for local testing to avoid S3 dependencies
- The `test_utils.py` module provides fixtures and helpers for agent testing
- Mock AWS services using `moto` for DynamoDB tables in tests
- Use `@pytest.mark.integration` for tests requiring real AWS API calls

**Session Manager Pattern:**
```python
# CORRECT: Create session manager with session_id
def create_session_manager(session_id: str):
    if ENV == "local":
        return FileSessionManager(
            session_id=session_id,
            directory=".sessions",
        )
    else:
        return S3SessionManager(
            session_id=session_id,
            bucket=SESSIONS_BUCKET_NAME,
            region_name=AWS_REGION,
        )

# CORRECT: Create agent per-request
agent = create_agent(session_id)
response = await agent.run(user_message=message)
```

**Common Testing Issues:**
1. **S3SessionManager initialization error**: Ensure you're using `ENV=local` for local testing
2. **Missing AWS credentials**: Set `AWS_BEDROCK_ENABLED=0` (default) for mock testing
3. **Session persistence**: Check `.sessions/` directory for session files
4. **Import errors**: Ensure virtual environment is activated

## Common Pitfalls to Avoid

1. **Don't violate Strands patterns**: No f-strings in logging, always use type annotations
2. **Don't forget async context**: Bedrock calls are async, Lambda handlers need proper async/await
3. **Don't hardcode timings**: All prep timings, schedules configurable via `config/agents.yaml`
4. **Don't skip session management**: All agents need proper session persistence
5. **Don't ignore meeting type detection**: Robust keyword matching + attendee count rules
6. **Don't over-engineer**: Start with simple implementations, iterate based on user feedback
7. **Remember security requirements**: Audit logs, encryption, secure data handling

## Reference Documentation

- **README.md**: Complete system overview, use cases, architecture diagrams
- **AGENTS.md**: Strands SDK patterns, coding standards, development workflow
- Strands Agents Docs: https://strandsagents.com/
