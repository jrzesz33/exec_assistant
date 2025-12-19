# Executive Assistant Multi-Agent System

An intelligent multi-agent system designed to help executives manage their organization effectively through automated workflows, intelligent reminders, and decision support.

## Project Status

**Current Phase**: Ready for Phase 3 - Meeting Preparation Workflow 🚀

| Phase | Status | Description |
|-------|--------|-------------|
| **Phase 1** | ✅ Complete | Foundation: DynamoDB, S3, KMS, data models, configuration |
| **Phase 1.5** | ✅ Complete | Authentication: Google OAuth, JWT, web chat UI, API Gateway |
| **Phase 2** | ✅ Complete | First Agent: Meeting Coordinator with AWS Nova, Strands SDK, chat handler |
| **Phase 3** | 📋 Planning | Meeting Prep Workflow: Calendar integration, Step Functions, proactive notifications |
| **Phase 4+** | ⏳ Future | Post-meeting processing, real context agents, advanced features |

**What's Working Now**:
- ✅ User authentication (Google OAuth 2.0)
- ✅ Web-based chat interface
- ✅ Interactive chat with Meeting Coordinator agent
- ✅ Session persistence (S3 + DynamoDB)
- ✅ JWT-secured API endpoints
- ✅ Comprehensive testing framework

**Coming in Phase 3**:
- 📅 Google Calendar / Microsoft 365 integration
- ⏰ Automated calendar monitoring (every 2 hours)
- 🔔 Proactive meeting prep notifications (24-72 hours before)
- 📋 Meeting materials generation (agendas, questions, note templates)
- 🔄 Complete Step Functions orchestration workflow

**Documentation**:
- 📖 [Phase 1 Summary](PHASE1_SUMMARY.md) - Foundation implementation
- 📖 [Phase 1.5 Deployment](PHASE_1_5_DEPLOYMENT.md) - Authentication setup
- 📖 [Phase 2 Summary](PHASE2_SUMMARY.md) - Agent implementation
- 📖 [Phase 3 Plan](PHASE3_PLAN.md) - Detailed Phase 3 design with sequence diagrams
- 📖 [Testing Guide](TESTING_GUIDE.md) - How to test locally and in AWS
- 📖 [Cost Estimate](COST_ESTIMATE.md) - AWS cost breakdown

## Overview

This system leverages AI agents to handle the complex operational requirements of running an organization, including budget management, strategic planning (Big Rocks), HR activities, incident management, and decision tracking.

## Technology Stack

- **Agent Framework**: [Strands Agent SDK (Python)](https://github.com/strands-agents/sdk-python)
- **Infrastructure as Code**: Pulumi
- **Cloud Provider**: AWS
  - Amazon Bedrock (AI/ML)
  - AWS Lambda (Serverless compute)
  - Amazon DynamoDB (State management)
  - Amazon EventBridge (Scheduling & event-driven workflows)
  - Amazon S3 (Document storage)
  - AWS Secrets Manager (Credentials)
  - Amazon SNS/SQS (Notification routing)
  - AWS Step Functions (Complex workflow orchestration)
- **Communication Services**:
  - Slack API (Primary notification channel)
  - Twilio (SMS notifications)
  - SendGrid/AWS SES (Email)

## Architecture

### Multi-Agent System Design

The system consists of specialized agents that work together to manage different aspects of organizational leadership:

```
┌─────────────────────────────────────────────────────────┐
│          Executive Assistant Orchestrator               │
│         (Coordinates all specialized agents)            │
└───────────────────┬─────────────────────────────────────┘
                    │
    ┌───────────────┼───────────────┐
    │               │               │
    ▼               ▼               ▼
┌────────┐    ┌──────────┐    ┌──────────┐
│Budget  │    │Big Rocks │    │   HR     │
│Manager │    │Manager   │    │ Manager  │
└────────┘    └──────────┘    └──────────┘
    │               │               │
    ▼               ▼               ▼
┌────────┐    ┌──────────┐    ┌──────────┐
│Meeting │    │Incident  │    │Staffing  │
│Coord.  │    │Manager   │    │ Manager  │
└────────┘    └──────────┘    └──────────┘
    │               │               │
    ▼               ▼               ▼
┌────────┐    ┌──────────┐    ┌──────────┐
│Decision│    │Routine   │    │Document  │
│Tracker │    │Manager   │    │ Manager  │
└────────┘    └──────────┘    └──────────┘
```

## Agent Capabilities

### 1. Budget Manager Agent
**Purpose**: Manage departmental budget, track spending, forecast, and provide alerts

**Example Activities**:
- Track monthly AWS infrastructure spending against $2.3M annual budget
- Alert when any cost center exceeds 85% of quarterly allocation
- Generate weekly spend reports comparing actual vs. planned
- Forecast year-end budget position based on current burn rate
- Flag unusual spending patterns (e.g., 30% increase in specific service)
- Prepare quarterly budget reviews with variance analysis

**Sample Routine**:
```yaml
- Weekly: Generate spending summary every Monday 9 AM
- Monthly: Full budget review on last Friday of month
- Quarterly: Prepare board-level budget presentation
- Ad-hoc: Alert on spending anomalies within 24 hours
```

### 2. Big Rocks Manager Agent
**Purpose**: Track strategic priorities and ensure progress on organizational goals

**Example Big Rocks**:
- **Q1 2025**: Migrate 40% of legacy workloads to cloud-native architecture
- **Q2 2025**: Achieve 99.99% uptime for critical systems
- **H1 2025**: Reduce mean time to recovery (MTTR) by 50%
- **2025**: Complete security compliance certifications
- **2025**: Implement zero-trust security architecture

**Activities**:
- Weekly progress check-ins on each Big Rock
- Identify blockers and escalate when needed
- Quarterly Big Rock review and reprioritization
- Generate status reports for executive leadership
- Alert when Big Rock is at risk (red/yellow status)

### 3. HR Manager Agent
**Purpose**: Manage all people-related activities and ensure compliance with HR processes

**Example Activities**:

**1-1 Meetings**:
- Schedule bi-weekly 1-1s with 12 direct reports
- Send preparation prompts 24 hours before meeting
- Track action items from previous 1-1s
- Suggest discussion topics based on recent incidents, projects, or goals

**Goal Setting**:
- Coordinate annual goal-setting process (January)
- Ensure SMART goals aligned with Big Rocks
- Track goal completion percentage throughout year
- Send quarterly reminders to update goal progress

**Performance Reviews**:
- Mid-year reviews (June): Schedule, send templates, track completions
- End-of-year reviews (December): Coordinate calibration sessions
- Track review completion rates across organization
- Generate summary reports on team performance trends

**Staff Meetings**:
- Schedule monthly all-hands staff meeting
- Collect agenda items from leadership team
- Prepare presentation materials
- Distribute meeting notes and action items
- Track action item completion

### 4. Meeting Coordinator Agent
**Purpose**: Manage various meeting types, ensure productive outcomes, and proactively prepare you for every meeting

**Core Capabilities**:

**Proactive Meeting Preparation** (Critical Feature):
- **Scheduled Monitoring**: EventBridge scheduled task checks calendar every 2 hours for upcoming meetings
- **Smart Notifications**: Sends notification 24-48 hours before meeting (configurable per meeting type)
- **Interactive Pre-Meeting Chat**:
  - Asks contextual questions based on meeting type and attendees
  - "What are your top 3 priorities for tomorrow's leadership meeting?"
  - "Any specific concerns about the Cloud Migration project to discuss?"
  - "What decisions need to be made in the QBR?"
- **Intelligent Agenda Generation**: Creates structured agenda from your responses and agent data
- **Question Bank**: Compiles questions that need answers during the meeting
- **Context Gathering**: Pulls relevant data from other agents (budget, Big Rocks, incidents, etc.)
- **Note Templates**: Provides structured note-taking templates
- **Post-Meeting Follow-up**: Generates action items and distributes meeting notes

**Meeting Preparation Workflow**:
```
48 hours before meeting
  ↓
EventBridge triggers Meeting Prep Lambda
  ↓
Meeting Coordinator analyzes meeting type & participants
  ↓
Sends Slack/SMS notification: "Let's prep for Monday's Leadership Meeting"
  ↓
User clicks notification → Opens interactive chat session
  ↓
Agent asks contextual questions:
  - "What went well this week?"
  - "Any blockers to discuss?"
  - "Which Big Rock needs attention?"
  - "Budget concerns for the team?"
  ↓
User responds via chat (async, can respond over hours)
  ↓
Agent generates:
  ✓ Structured agenda with time allocations
  ✓ Background context for each topic
  ✓ Questions to ask attendees
  ✓ Decisions that need to be made
  ✓ Note-taking template
  ↓
2 hours before meeting: Final reminder with prep materials
  ↓
During meeting: Real-time note-taking support (optional)
  ↓
After meeting: Agent extracts action items & sends summary
```

**Example Meetings**:

**Weekly Leadership Team Meeting**:
- Every Monday 10-11:30 AM
- Agenda: Big Rocks status, incidents, budget, staffing updates
- Attendees: Director-level and above (15 people)
- **Prep Trigger**: Friday 2 PM (3 days before)
- **Prep Questions**:
  - "What are the top 3 things the team needs to know?"
  - "Any incidents or reliability concerns from this week?"
  - "Budget variances to address?"
  - "Staffing updates or concerns?"
  - "Decisions needed from the group?"

**1-1 with Direct Report (Sarah - Cloud Engineering Lead)**:
- Bi-weekly, Tuesday 2-3 PM
- **Prep Trigger**: Monday 4 PM (day before)
- **Prep Questions**:
  - "How is Sarah doing on the cloud migration Big Rock?"
  - "Any action items from last 1-1 we need to follow up on?"
  - "Career development topics to discuss?"
  - "Any feedback you want to give Sarah?"
  - "Concerns about her team's workload?"
- **Context Provided**:
  - Last 1-1 notes and action items
  - Sarah's goal progress
  - Her team's recent incidents
  - Cloud migration Big Rock status

**Reliability Meeting** (Post-Incident Review):
- Triggered within 48 hours of major incident
- Agenda: Timeline, root cause, action items, preventive measures
- Attendees: Incident responders + leadership
- **Prep Trigger**: Immediately upon scheduling
- **Prep Questions**:
  - "What's your initial understanding of the incident?"
  - "Questions you need answered in the post-mortem?"
  - "Specific preventive measures to evaluate?"
- **Context Provided**:
  - Incident timeline and metrics
  - Similar past incidents
  - Affected systems and customer impact

**Quarterly Business Review (QBR)**:
- End of each quarter
- Agenda: Budget, Big Rocks, metrics, team health, next quarter planning
- Attendees: Full organization + stakeholders
- Deliverables: QBR deck, strategy updates
- **Prep Trigger**: 2 weeks before (phased preparation)
- **Prep Questions** (Week 1):
  - "What are your key messages for the quarter?"
  - "Wins to celebrate?"
  - "Challenges to acknowledge?"
  - "Top 3 priorities for next quarter?"
- **Prep Questions** (Week 2):
  - "Review the draft deck - any changes needed?"
  - "Tough questions you might get asked?"
  - "Announcements or decisions to communicate?"

**Executive Staff Meeting with CIO**:
- Monthly, last Wednesday
- **Prep Trigger**: 2 days before
- **Prep Questions**:
  - "Hot topics from your org this month?"
  - "Budget concerns or requests?"
  - "Strategic initiatives to highlight?"
  - "Help needed from other departments?"
  - "Risks to escalate?"
- **Context Provided**:
  - Month's incident summary
  - Budget variance report
  - Big Rocks progress
  - Staffing changes

### 5. Incident & Reliability Manager Agent
**Purpose**: Track incidents, manage post-mortems, and drive reliability improvements

**Example Activities**:
- Monitor incident tracking system (PagerDuty, ServiceNow)
- Classify incidents by severity (SEV0-SEV3)
- Trigger post-incident review process for SEV0/SEV1
- Track MTTR and MTTD metrics
- Generate monthly reliability reports
- Identify recurring incident patterns
- Schedule and run weekly reliability meetings
- Track completion of incident action items

**Sample Incident Workflow**:
```
SEV0 Incident Detected
  ↓
Alert leadership immediately
  ↓
Track incident duration and resolution
  ↓
Schedule post-incident review (within 48hrs)
  ↓
Generate post-mortem document
  ↓
Assign action items with owners and due dates
  ↓
Track action item completion
  ↓
Report in weekly reliability meeting
```

### 6. Staffing Manager Agent
**Purpose**: Manage headcount, hiring pipeline, and resource allocation

**Example Activities**:
- Track current headcount vs. approved headcount (e.g., 142/150 FTE)
- Monitor open positions and hiring pipeline
- Alert when key positions are open >90 days
- Track contractor vs. FTE ratio
- Plan for attrition (historical rate: 8% annually)
- Forecast hiring needs based on Big Rocks
- Generate org chart updates
- Track team utilization and capacity

**Staffing Scenarios**:
- "We have 5 open SRE positions, average time-to-hire is 87 days, risk to Q2 Big Rock"
- "Cloud Engineering team at 110% capacity, recommend 2 additional hires"
- "3 contractors converting to FTE next quarter, need budget approval"

### 7. Decision Tracker Agent
**Purpose**: Track major decisions, ensure follow-through, and maintain decision log

**Example Major Decisions**:
- **Multi-cloud strategy**: Approved AWS primary + Azure DR (March 2025)
- **Observability platform**: Selected Datadog over New Relic (Jan 2025)
- **On-call rotation**: Moved to follow-the-sun model (Dec 2024)
- **Vendor selection**: Terraform Cloud for IaC management (Q4 2024)

**Activities**:
- Log all major decisions with context, date, stakeholders, rationale
- Track decision implementation status
- Send reminders for decisions requiring follow-up
- Generate decision registry reports
- Alert when decisions conflict with each other
- Maintain ADR (Architecture Decision Records)

### 8. Routine Manager Agent
**Purpose**: Ensure regular activities happen on schedule and send intelligent reminders

**Example Routines**:

**Daily**:
- 8:00 AM: Review overnight incidents and on-call activity
- 8:30 AM: Check budget alerts and cost anomalies
- 5:00 PM: Review action items due today

**Weekly**:
- Monday 9 AM: Prepare for leadership team meeting
- Wednesday: Review Big Rocks progress
- Friday 4 PM: Weekly reflection and planning for next week

**Monthly**:
- 1st Monday: Staff meeting preparation
- 15th: Budget review with finance
- Last Friday: Monthly metrics review

**Quarterly**:
- Week 12: QBR preparation begins
- Week 13: QBR delivery and planning for next quarter

**Annually**:
- January: Goal setting and annual planning
- June: Mid-year performance reviews
- December: Year-end performance reviews and next year planning

### 9. Document Manager Agent
**Purpose**: Organize, version, and retrieve important documents

**Example Document Types**:
- Budget spreadsheets and forecasts
- Big Rocks trackers and status reports
- Performance review templates and completed reviews
- Post-incident review documents
- Meeting notes and action items
- Decision logs and ADRs
- Org charts and staffing plans
- Compliance documentation (HITRUST, HIPAA)

## Example Use Cases

### Use Case 1: Big Rock at Risk
```
Scenario: "Cloud Migration" Big Rock is at 35% complete but we're 50% through Q1

Agent Actions:
1. Big Rocks Manager: Detects deviation from plan
2. Meeting Coordinator: Schedules emergency sync with cloud team
3. Decision Tracker: Logs decision to add contractors for 6 weeks
4. Staffing Manager: Initiates contractor requisition
5. Budget Manager: Alerts about contractor impact on budget
6. Routine Manager: Adds weekly cloud migration check-ins
```

### Use Case 2: Major Incident (SEV0)
```
Scenario: Patient portal down for 90 minutes

Agent Actions:
1. Incident Manager: Logs incident, starts timer, alerts leadership
2. Meeting Coordinator: Schedules post-incident review for tomorrow
3. Routine Manager: Adds incident follow-up to next leadership meeting
4. Document Manager: Creates post-mortem template
5. Decision Tracker: Logs decision to implement circuit breaker pattern
6. Budget Manager: Flags budget for new monitoring tools if needed
```

### Use Case 3: Quarterly Business Review Prep
```
Scenario: QBR is in 2 weeks

Agent Actions:
1. Routine Manager: Triggers QBR preparation workflow
2. Budget Manager: Generates quarterly spend analysis
3. Big Rocks Manager: Compiles progress on all strategic initiatives
4. HR Manager: Prepares team health metrics (attrition, satisfaction, headcount)
5. Incident Manager: Summarizes reliability metrics and major incidents
6. Staffing Manager: Updates org chart and hiring pipeline status
7. Document Manager: Compiles all reports into QBR deck
8. Meeting Coordinator: Schedules QBR and sends calendar invites
```

### Use Case 4: Performance Review Season
```
Scenario: Mid-year reviews due in June

Agent Actions:
1. HR Manager: Sends calendar invites for all 1-1 review meetings
2. Document Manager: Distributes review templates to all managers
3. Routine Manager: Sends weekly reminders about completion deadlines
4. HR Manager: Tracks completion rate (e.g., "8/12 reviews completed")
5. Meeting Coordinator: Schedules calibration session with leadership
6. Document Manager: Collects and organizes all completed reviews
```

### Use Case 5: Proactive Meeting Preparation (Critical Workflow)
```
Scenario: Monday Leadership Team Meeting at 10 AM

Timeline:

FRIDAY 2:00 PM (3 days before):
├─ EventBridge scheduled rule triggers Meeting Prep Lambda
├─ Meeting Coordinator Agent activates
├─ Queries calendar API: "Leadership Meeting - Monday 10 AM"
├─ Identifies meeting type: "Weekly Leadership Team"
├─ Gathers context from agents:
│  ├─ Budget Manager: "Overspent $45K in compute this week"
│  ├─ Big Rocks Manager: "Cloud Migration 38% complete (on track)"
│  ├─ Incident Manager: "1 SEV1 incident - database timeout Thursday"
│  ├─ Staffing Manager: "2 new SRE candidates in final round"
│  └─ Decision Tracker: "Observability platform decision pending"
├─ Sends Slack notification:
│  "👋 Let's prepare for Monday's Leadership Meeting
│   Click here to start prep session (takes 5-10 min)"
└─ User clicks → Opens chat interface

FRIDAY 2:30 PM (Interactive Chat Session):
Agent: "Hi! Let's prep for Monday's leadership meeting. I've gathered
       some context from the week. Let me ask you a few questions:

       1️⃣ What are your top 3 priorities to discuss?"

User: "1. The database incident and our reliability posture
       2. Budget overage - need to understand why
       3. Hiring pipeline update"

Agent: "Got it. I see we had a SEV1 database timeout on Thursday.

       2️⃣ What specific questions do you have about this incident?"

User: "Why did it happen? Is this a pattern? What's our remediation plan?"

Agent: "Perfect. I'll add those to your question bank.

       3️⃣ The budget shows $45K overage in compute. Do you want to:
       a) Dig into the root cause during the meeting?
       b) Have budget team investigate first?
       c) Just acknowledge and track?"

User: "B - have them investigate first, but I want a report by Wednesday"

Agent: "I'll create an action item for the budget team.

       4️⃣ Any decisions that need to be made by the group?"

User: "Yes, need to finalize the observability platform - Datadog vs New Relic"

Agent: "I see that decision has been pending since last week.

       5️⃣ Anything else on your mind for Monday?"

User: "That's it"

Agent: "Perfect! I'm generating your meeting materials now..."

FRIDAY 2:45 PM (Agent Processing):
├─ Creates structured agenda:
│  ├─ 10:00-10:10: Week in review & wins
│  ├─ 10:10-10:25: SEV1 Incident Deep Dive
│  ├─ 10:25-10:40: Budget Overage Discussion
│  ├─ 10:40-10:55: Observability Platform Decision
│  ├─ 10:55-11:10: Staffing & Hiring Update
│  └─ 11:10-11:30: Big Rocks Status & Next Week Preview
│
├─ Generates question bank:
│  ├─ For Incident Manager: "Root cause? Is this a pattern?"
│  ├─ For Budget Manager: "What drove the $45K overage?"
│  ├─ For Staffing: "Timeline on SRE hires?"
│  └─ For team: "Datadog vs New Relic - final decision?"
│
├─ Compiles context packets:
│  ├─ Incident timeline and metrics
│  ├─ Budget variance chart
│  ├─ Cloud migration dashboard
│  └─ Hiring pipeline status
│
├─ Creates note-taking template with sections for each agenda item
│
└─ Sends Slack message:
   "✅ Your meeting prep is ready! Here's what I created:

   📋 Agenda (6 topics, 90 min)
   ❓ Question Bank (8 questions)
   📊 Context Packets (4 documents)
   📝 Note Template

   View materials: [link]"

MONDAY 8:00 AM (Final Reminder):
├─ Meeting Coordinator sends reminder:
│  "⏰ Leadership Meeting in 2 hours
│
│   Quick recap:
│   ✓ SEV1 incident debrief
│   ✓ Budget overage (team investigating)
│   ✓ Observability platform decision ← NEEDS DECISION
│   ✓ Staffing updates
│
│   Action required: None - you're all set!
│
│   [View full prep materials]"
└─ Materials include talking points and anticipated questions

MONDAY 10:00-11:30 AM (During Meeting):
├─ Optional: Real-time note-taking assist via mobile/laptop
└─ Captures decisions and action items as discussed

MONDAY 11:45 AM (Post-Meeting):
├─ Agent prompts: "How'd the meeting go? I can help with notes."
├─ User uploads notes or voice memo
├─ Agent processes and generates:
│  ├─ Meeting summary
│  ├─ Decisions made:
│  │  └─ "Selected Datadog for observability platform"
│  ├─ Action items:
│  │  ├─ Budget team: Investigate compute overage by Wed
│  │  ├─ Incident team: Implement connection pooling by Fri
│  │  └─ Staffing: Make offer to SRE candidates by Thu
│  └─ Follow-up items for next week
│
├─ Decision Tracker: Logs "Datadog selected over New Relic"
├─ Document Manager: Stores meeting notes
├─ Routine Manager: Adds action items to weekly tracking
├─ HR Manager: Updates 1-1 agendas with relevant items
│
└─ Sends summary to all attendees:
   "📧 Leadership Meeting Notes - Dec 16, 2025

   Decisions: 1 | Action Items: 3 | Next Meeting: Dec 23

   [Full notes and action items]"

TUESDAY-FRIDAY (Follow-up):
└─ Routine Manager tracks action item completion and sends reminders
```

**Key Benefits of This Workflow**:
- **Never walk into a meeting unprepared**: Automated prep triggers ensure you're ready
- **Contextual preparation**: Agent gathers data from all other agents automatically
- **Asynchronous & efficient**: Answer questions on your schedule (not a 30-min meeting to prep for a meeting)
- **Structured outcomes**: Clear agendas, questions, and follow-up tracking
- **Institutional memory**: All decisions and action items automatically logged and tracked
- **Delegation support**: Creates clear action items with owners and deadlines

## Project Structure

```
exec_assistant/
├── README.md
├── agents/
│   ├── __init__.py
│   ├── orchestrator.py          # Main orchestrator agent
│   ├── budget_manager.py
│   ├── big_rocks_manager.py
│   ├── hr_manager.py
│   ├── meeting_coordinator.py
│   ├── incident_manager.py
│   ├── staffing_manager.py
│   ├── decision_tracker.py
│   ├── routine_manager.py
│   └── document_manager.py
├── interfaces/
│   ├── __init__.py
│   ├── slack_bot.py             # Slack bot for interactive chats
│   ├── notification_handler.py  # Multi-channel notification router
│   ├── chat_session.py          # Conversational session management
│   └── webhooks.py              # Inbound webhook handlers
├── workflows/
│   ├── __init__.py
│   ├── meeting_prep.py          # Meeting preparation workflow
│   ├── incident_response.py     # Incident response workflow
│   └── review_cycle.py          # Performance review workflow
├── infrastructure/
│   ├── __main__.py              # Pulumi main
│   ├── Pulumi.yaml
│   ├── Pulumi.dev.yaml
│   ├── Pulumi.prod.yaml
│   ├── network.py               # VPC, subnets, etc.
│   ├── compute.py               # Lambda functions
│   ├── storage.py               # DynamoDB, S3
│   ├── ai.py                    # Bedrock configuration
│   ├── messaging.py             # SNS, SQS, EventBridge
│   ├── step_functions.py        # Workflow orchestration
│   └── monitoring.py            # CloudWatch, alarms
├── shared/
│   ├── __init__.py
│   ├── models.py                # Data models
│   ├── config.py                # Configuration
│   ├── calendar.py              # Calendar integration
│   └── utils.py                 # Shared utilities
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── config/
│   ├── agents.yaml              # Agent configuration
│   ├── meeting_types.yaml       # Meeting type definitions
│   └── notification_rules.yaml  # Notification preferences
├── requirements.txt
└── pyproject.toml
```

## Getting Started

### Prerequisites

- Python 3.11+
- AWS Account with Bedrock access
- Pulumi CLI installed
- AWS CLI configured

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd exec_assistant

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Strands SDK
pip install strands-sdk
```

### Infrastructure Deployment

```bash
# Navigate to infrastructure directory
cd infrastructure

# Configure Pulumi stack
pulumi stack init dev

# Set AWS region
pulumi config set aws:region us-east-1

# Deploy infrastructure
pulumi up
```

### Running Agents Locally

```bash
# Set environment variables
export AWS_REGION=us-east-1
export BEDROCK_MODEL=anthropic.claude-3-sonnet-20240229-v1:0

# Run the orchestrator
python -m agents.orchestrator
```

## Configuration

### Environment Variables

```bash
# AWS Configuration
AWS_REGION=us-east-1
BEDROCK_MODEL=anthropic.claude-3-sonnet-20240229-v1:0
DYNAMODB_TABLE_NAME=exec-assistant-state
S3_BUCKET_NAME=exec-assistant-documents

# Calendar Integration
CALENDAR_API_ENDPOINT=https://...
CALENDAR_API_TYPE=google  # or 'microsoft'
CALENDAR_OAUTH_CLIENT_ID=...
CALENDAR_OAUTH_CLIENT_SECRET=...

# Notification Services
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
SLACK_SIGNING_SECRET=...
SLACK_USER_ID=U123456789  # Your Slack user ID for DMs

TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_PHONE_NUMBER=+1234567890
USER_PHONE_NUMBER=+1234567890

SENDGRID_API_KEY=...
USER_EMAIL=executive@company.com

# Chat Session Management
CHAT_SESSION_TIMEOUT=3600  # 1 hour session timeout
REDIS_URL=redis://...  # For session state (optional)
```

### Agent Configuration

Each agent can be configured via `config/agents.yaml`:

```yaml
budget_manager:
  alert_threshold: 0.85  # Alert at 85% of budget
  report_schedule: "cron(0 9 ? * MON *)"  # Every Monday 9 AM

big_rocks_manager:
  review_frequency: "weekly"
  risk_threshold: 0.75  # Flag if <75% progress at midpoint

hr_manager:
  one_on_one_frequency: "bi-weekly"
  review_reminder_days: [30, 14, 7, 1]  # Days before deadline

meeting_coordinator:
  calendar_check_schedule: "cron(0 */2 * * ? *)"  # Check calendar every 2 hours

  # Meeting preparation timing (hours before meeting)
  prep_timing:
    leadership_meeting: 72      # 3 days
    one_on_one: 24             # 1 day
    staff_meeting: 48          # 2 days
    qbr: 336                   # 2 weeks
    incident_review: 2          # ASAP
    executive_meeting: 48       # 2 days
    default: 24                # 1 day for unknown types

  # Final reminder timing (hours before meeting)
  reminder_timing:
    default: 2                 # 2 hours before
    qbr: 24                    # 1 day before for major presentations

  # Notification channels (priority order)
  notification_channels:
    - slack
    - sms
    - email

  # Meeting type detection (keywords in meeting title/description)
  meeting_types:
    leadership_meeting:
      keywords: ["leadership", "leadership team", "leadership meeting", "LT meeting"]
      required_attendee_count: 10

    one_on_one:
      keywords: ["1-1", "1:1", "one on one", "check-in"]
      attendee_count: 2

    staff_meeting:
      keywords: ["staff meeting", "all hands", "team meeting"]
      required_attendee_count: 15
```

## Integration Points

### Calendar Integration
- Google Calendar API or Microsoft Graph API
- Automated meeting scheduling and updates

### Incident Management
- PagerDuty API
- ServiceNow API
- Incident detection and tracking

### Financial Systems
- AWS Cost Explorer API
- Internal finance systems

### Communication
- **Slack API**:
  - Interactive notifications for meeting prep
  - Slack bot for conversational interface
  - Action items and reminders via DM
  - Meeting summaries to team channels
- **SMS**: Twilio for critical alerts and mobile notifications
- **Email**: SendGrid or AWS SES for formal communications and summaries
- **Push Notifications**: Mobile app integration (future enhancement)

### Document Storage
- Google Drive API or SharePoint
- S3 for long-term storage

## Security & Compliance

### Security Considerations
- Data encryption at rest and in transit
- Audit logging for all agent actions
- Role-based access control (RBAC)
- Secure credential management
- Compliance with organizational security policies

### AWS Security
- All Lambda functions in private subnets
- Secrets Manager for credentials
- KMS encryption for data
- CloudTrail logging enabled
- VPC endpoints for AWS services

## Monitoring & Observability

- CloudWatch Logs for all agent activities
- CloudWatch Metrics for agent performance
- CloudWatch Alarms for failures
- X-Ray tracing for distributed operations
- Custom dashboards for leadership visibility

## Future Enhancements

- Natural language interface (Slack bot, CLI chat)
- Predictive analytics (budget forecasting, attrition prediction)
- Integration with JIRA/Linear for project management
- Automated report generation with data visualization
- Mobile notifications for critical alerts
- Voice interface for quick updates
- ML-based decision recommendations
- Automated goal progress tracking via Git/JIRA activity

## Contributing

[To be added: Contribution guidelines]

## License

[To be added: License information]

## Contact

[To be added: Contact information]

---

**Note**: This system handles sensitive organizational data. Ensure all security best practices are followed and compliance requirements are met before deployment in a production environment.
