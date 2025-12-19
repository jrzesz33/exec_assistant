# Implementation Plan

**STATUS UPDATE**: Phases 1, 1.5, and 2 are COMPLETE ✅

This document outlines the original phased implementation plan for the Executive Assistant system. **For detailed Phase 3 implementation details, see [PHASE3_PLAN.md](../PHASE3_PLAN.md)**.

## Completed Phases

| Phase | Status | Documentation |
|-------|--------|---------------|
| **Phase 1: Foundation** | ✅ Complete | [PHASE1_SUMMARY.md](../PHASE1_SUMMARY.md) |
| **Phase 1.5: Authentication** | ✅ Complete | [PHASE_1_5_DEPLOYMENT.md](../PHASE_1_5_DEPLOYMENT.md) |
| **Phase 2: First Agent** | ✅ Complete | [PHASE2_SUMMARY.md](../PHASE2_SUMMARY.md) |
| **Phase 3: Meeting Prep Workflow** | 📋 In Planning | [PHASE3_PLAN.md](../PHASE3_PLAN.md) |

## Overview

This document outlines the phased implementation plan for the Executive Assistant system, starting with the Meeting Coordinator agent and Slack bot interface.

## Implementation Philosophy

**Approach**: Build incrementally, deploy early, iterate based on real usage

- Start with **Meeting Coordinator** (highest value, most complex)
- Build **Slack bot** as primary interface (reusable for all agents)
- Deploy **minimal viable infrastructure** first
- Add context gathering agents incrementally
- Iterate based on user feedback

## Phase 1: Foundation (Weeks 1-2) ✅ COMPLETE

**See**: [PHASE1_SUMMARY.md](../PHASE1_SUMMARY.md) for detailed completion summary

### Goals
- Set up development environment
- Create base infrastructure
- Implement basic Slack bot
- Deploy to AWS dev environment

### Tasks (All Complete)

#### 1.1 Project Setup
- [x] Initialize Python project structure
  - `pyproject.toml` with dependencies
  - `src/exec_assistant/` directory structure
  - `tests/` and `tests_integ/` directories
  - Pre-commit hooks (ruff, mypy)
- [ ] Install Strands SDK and dependencies
  ```bash
  pip install strands-sdk boto3 slack-sdk google-api-python-client
  ```
- [ ] Create `.env.example` with required variables
- [ ] Set up local DynamoDB (for development)
  ```bash
  docker run -p 8000:8000 amazon/dynamodb-local
  ```

#### 1.2 Data Models (`shared/models.py`)
- [ ] Define `Meeting` dataclass
- [ ] Define `ChatSession` dataclass
- [ ] Define `ChatMessage` dataclass
- [ ] Define `MeetingMaterials` dataclass
- [ ] Define `ActionItem` dataclass
- [ ] Write unit tests for models
- [ ] Add serialization/deserialization methods

#### 1.3 Base Infrastructure (Pulumi)
- [ ] Create `infrastructure/` directory
- [ ] Initialize Pulumi project (`pulumi new aws-python`)
- [ ] Create VPC with public/private subnets (`infrastructure/network.py`)
- [ ] Create DynamoDB tables (`infrastructure/storage.py`)
  - `exec-assistant-meetings-dev`
  - `exec-assistant-chat-sessions-dev`
- [ ] Create S3 buckets (`infrastructure/storage.py`)
  - `exec-assistant-documents-dev`
  - `exec-assistant-sessions-dev`
- [ ] Create KMS key for encryption
- [ ] Deploy to dev: `pulumi up`

#### 1.4 Slack Bot Basics (`interfaces/slack_bot.py`)
- [ ] Create Slack app in Slack workspace
- [ ] Implement signature verification
- [ ] Create webhook handler Lambda skeleton
- [ ] Implement message routing (DM vs command)
- [ ] Add basic command: `/meetings`
- [ ] Test webhook locally (ngrok or AWS SAM)
- [ ] Write unit tests for webhook handler

#### 1.5 Configuration
- [ ] Create `config/agents.yaml`
- [ ] Create `config/meeting_types.yaml`
- [ ] Load configuration in `shared/config.py`
- [ ] Write tests for config loading

**Deliverable**: Working Slack bot that responds to `/meetings` command

**Success Criteria**:
- Bot responds to DMs
- `/meetings` command returns "No meetings found" (no calendar yet)
- Infrastructure deployed to AWS dev
- All tests passing

---

**NOTE**: The sections below represent the original plan. Actual implementation differed:
- Phase 1.5 added authentication (Google OAuth, JWT, web UI)
- Phase 2 implemented the Meeting Coordinator agent with chat handler
- Calendar integration moved to Phase 3

---

## Phase 2: Calendar Integration (Week 3) [ORIGINAL PLAN - See Phase 3 for Updated Plan]

### Goals
- Connect to calendar API (Google or Microsoft)
- Poll calendar for meetings
- Store meetings in DynamoDB
- Display meetings via Slack command

### Tasks

#### 2.1 Calendar Integration (`shared/calendar.py`)
- [ ] Implement Google Calendar OAuth flow
  - Store credentials in Secrets Manager
  - Handle token refresh
- [ ] Implement `fetch_upcoming_meetings()`
  - Query next 14 days
  - Parse meeting details
  - Map to `Meeting` model
- [ ] Implement `get_meeting_details(meeting_id)`
- [ ] Write integration tests (requires test calendar)
- [ ] Add error handling and retry logic

#### 2.2 Calendar Monitor Lambda
- [ ] Create `agents/calendar_monitor.py`
- [ ] Implement Lambda handler
  ```python
  def lambda_handler(event, context):
      # Fetch meetings from calendar
      # Store new/updated meetings in DynamoDB
      # Emit events for meetings needing prep
  ```
- [ ] Add EventBridge scheduled rule (every 2 hours)
- [ ] Implement deduplication logic
- [ ] Add CloudWatch logging
- [ ] Write unit tests
- [ ] Deploy to dev

#### 2.3 Meeting Classification
- [ ] Implement `classify_meeting()` in `shared/utils.py`
- [ ] Load meeting type rules from `config/meeting_types.yaml`
- [ ] Write classification tests for each meeting type
- [ ] Calculate prep trigger time based on meeting type

#### 2.4 Update Slack `/meetings` Command
- [ ] Query DynamoDB for user's meetings
- [ ] Format meetings as Slack blocks
- [ ] Add "Prep Now" button for each meeting
- [ ] Handle pagination (>10 meetings)
- [ ] Add filters (today, this week, etc.)

**Deliverable**: Calendar integration working, meetings visible in Slack

**Success Criteria**:
- Calendar polled every 2 hours
- Meetings stored in DynamoDB with correct classification
- `/meetings` shows actual upcoming meetings
- Meeting prep trigger time calculated correctly

## Phase 3: Meeting Prep Workflow (Weeks 4-5) [ORIGINAL PLAN]

**UPDATED PLAN**: See [PHASE3_PLAN.md](../PHASE3_PLAN.md) for the comprehensive Phase 3 design with:
- Detailed architecture diagrams
- 5 Mermaid sequence diagrams
- Sprint-by-sprint task breakdown
- Infrastructure requirements
- Testing strategy
- Risk assessment

**Original Plan (for reference)**:

### Goals
- Implement interactive chat session
- Create Step Functions workflow
- Generate basic meeting materials
- End-to-end meeting prep working

### Tasks

#### 3.1 Chat Session Manager (`interfaces/chat_session.py`)
- [ ] Implement `create_session()`
- [ ] Implement `load_session(session_id)`
- [ ] Implement `update_session()`
- [ ] Implement state machine logic
- [ ] Add session expiration handling
- [ ] Write unit tests for session lifecycle

#### 3.2 Interactive Chat (`interfaces/slack_bot.py`)
- [ ] Implement prep notification formatting
- [ ] Handle "Start Prep" button click
- [ ] Implement question/answer flow
  - Send question
  - Wait for user response
  - Acknowledge and send next question
- [ ] Handle session timeout
- [ ] Handle "Remind me later" button
- [ ] Write integration tests for full chat flow

#### 3.3 Meeting Coordinator Agent (`agents/meeting_coordinator.py`)
- [ ] Create agent using Strands SDK
  ```python
  from strands.agent import Agent
  from strands.models import BedrockModel

  model = BedrockModel(model_id="anthropic.claude-3-5-sonnet-...")
  agent = Agent(model=model, system_prompt=..., tools=[...])
  ```
- [ ] Define agent system prompt
- [ ] Implement tools:
  - `get_meeting_details()`
  - `generate_agenda()`
  - `generate_questions()`
  - `create_note_template()`
- [ ] Configure S3 session manager
- [ ] Write unit tests (with mocked Bedrock)
- [ ] Write integration tests (with real Bedrock)

#### 3.4 Step Functions Workflow (`infrastructure/step_functions.py`)
- [ ] Create workflow definition JSON
- [ ] Implement Lambda: ClassifyMeeting
- [ ] Implement Lambda: SendPrepNotification
- [ ] Implement Lambda: ChatSessionManager (with task token)
- [ ] Implement Lambda: GenerateMaterials
  - Invoke Meeting Coordinator agent
  - Generate agenda, questions, template
  - Store in S3
- [ ] Implement Lambda: SendPrepMaterials
- [ ] Add error handling and retries
- [ ] Deploy workflow to dev
- [ ] Test end-to-end with sample meeting

#### 3.5 Material Storage and Retrieval
- [ ] Implement S3 storage functions
  - `store_materials(meeting_id, materials)`
  - `retrieve_materials(meeting_id)`
- [ ] Generate presigned URLs for material access
- [ ] Implement materials viewer (CloudFront + S3)
- [ ] Format materials as HTML/Markdown

**Deliverable**: End-to-end meeting prep working

**Success Criteria**:
- User receives prep notification 24-48 hours before meeting
- Interactive chat session works smoothly
- Agent generates useful agenda and questions
- Materials accessible via link in Slack
- Workflow completes successfully

## Phase 4: Context Gathering (Week 6)

### Goals
- Implement placeholder context agents
- Integrate context into meeting prep
- Enrich generated materials with relevant data

### Tasks

#### 4.1 Placeholder Agents
Create simple placeholder agents that return mock data:
- [ ] Budget Manager (`agents/budget_manager.py`)
  - Returns mock budget variance data
- [ ] Big Rocks Manager (`agents/big_rocks_manager.py`)
  - Returns mock initiative status
- [ ] Incident Manager (`agents/incident_manager.py`)
  - Returns mock recent incidents
- [ ] Staffing Manager (`agents/staffing_manager.py`)
  - Returns mock headcount data
- [ ] Decision Tracker (`agents/decision_tracker.py`)
  - Returns mock pending decisions

Each agent:
```python
@tool
def get_status() -> dict:
    """Get current status (placeholder)."""
    return {
        "status": "ok",
        "data": {...}  # Mock data
    }
```

#### 4.2 Context Gathering Lambda
- [ ] Create Lambda: GatherContext
- [ ] Invoke all context agents in parallel
- [ ] Handle agent failures gracefully (continue with partial context)
- [ ] Add timeout handling (30s per agent)
- [ ] Aggregate context into structured dict
- [ ] Write unit tests

#### 4.3 Update Step Functions Workflow
- [ ] Add GatherContext step (parallel execution)
- [ ] Pass context to GenerateMaterials step
- [ ] Update Meeting Coordinator agent to use context
  - Interpolate context into prep questions
  - Include context in agenda generation
- [ ] Test with mock context data

#### 4.4 Update Prep Questions
- [ ] Create question templates with context variables
  - `"Budget shows {variance_pct}% variance"`
  - `"We had {incident_count} incidents this week"`
- [ ] Implement context interpolation
- [ ] Test question rendering with various context

**Deliverable**: Meeting prep includes relevant context

**Success Criteria**:
- Context gathered from all placeholder agents
- Questions include dynamic data from context
- Materials show budget/incidents/decisions
- Graceful handling of missing context

## Phase 5: Post-Meeting Processing (Week 7)

### Goals
- Handle meeting notes upload
- Extract action items and decisions
- Distribute meeting summary
- Close the loop on meeting lifecycle

### Tasks

#### 5.1 Notes Upload Handler
- [ ] Implement file upload handler in Slack bot
- [ ] Support text notes and voice memos
- [ ] Transcribe voice memos (AWS Transcribe or Bedrock)
- [ ] Associate notes with meeting
- [ ] Store in S3

#### 5.2 Post-Meeting Agent
- [ ] Create `agents/post_meeting_processor.py`
- [ ] Implement tools:
  - `extract_action_items(notes)`
  - `extract_decisions(notes)`
  - `identify_follow_up_topics(notes)`
- [ ] Invoke agent with meeting notes
- [ ] Parse structured output
- [ ] Write unit tests

#### 5.3 Action Item Management
- [ ] Store action items in DynamoDB
- [ ] Update Decision Tracker with decisions
- [ ] Update Routine Manager with follow-up tasks
- [ ] Send Slack DMs to action item owners

#### 5.4 Meeting Summary
- [ ] Generate summary from notes and materials
- [ ] Format as Slack message
- [ ] Send to all attendees
- [ ] Include action items with owners and due dates

**Deliverable**: Complete meeting lifecycle

**Success Criteria**:
- Notes uploaded via Slack
- Action items extracted accurately
- Decisions logged
- Summary sent to attendees
- Follow-up items tracked

## Phase 6: Production Hardening (Week 8)

### Goals
- Improve error handling
- Add comprehensive monitoring
- Performance optimization
- Security hardening
- Prepare for production deployment

### Tasks

#### 6.1 Error Handling
- [ ] Add try/except blocks with specific error handling
- [ ] Implement dead letter queues for failed workflows
- [ ] Add retry logic with exponential backoff
- [ ] User-friendly error messages in Slack
- [ ] Automatic error reporting to SNS

#### 6.2 Monitoring & Observability
- [ ] Create CloudWatch dashboard
- [ ] Set up CloudWatch alarms
  - High error rate
  - Long execution time
  - API failures
- [ ] Enable X-Ray tracing for all Lambdas
- [ ] Add custom metrics
  - Meetings prepared
  - Chat completion rate
  - Materials generation time
- [ ] Set up SNS alerts for critical failures

#### 6.3 Performance Optimization
- [ ] Profile Lambda execution times
- [ ] Optimize memory allocations
- [ ] Implement caching where appropriate
  - Calendar data (2 hours)
  - User info (1 hour)
  - Question templates
- [ ] Reduce cold start times
  - Use Lambda layers
  - Minimize dependencies
- [ ] Parallel processing where possible

#### 6.4 Security Hardening
- [ ] Security audit of IAM policies (least privilege)
- [ ] Enable VPC Flow Logs
- [ ] Implement rate limiting on API Gateway
- [ ] Add input validation everywhere
- [ ] Sanitize logs (remove PHI)
- [ ] Enable AWS WAF on API Gateway

#### 6.5 Testing
- [ ] Increase unit test coverage to >80%
- [ ] End-to-end integration tests
- [ ] Load testing (simulate 100 concurrent preps)
- [ ] Failure scenario testing
  - Calendar API down
  - Bedrock throttling
  - DynamoDB unavailable
- [ ] User acceptance testing

**Deliverable**: Production-ready system

**Success Criteria**:
- All error paths handled gracefully
- Comprehensive monitoring in place
- Performance targets met (< 5s response time)
- Security best practices implemented
- Test coverage >80%

## Phase 7: Production Deployment (Week 9)

### Goals
- Deploy to production environment
- Gradual rollout to users
- Monitor and iterate

### Tasks

#### 7.1 Production Infrastructure
- [ ] Create production Pulumi stack
- [ ] Deploy production VPC with Multi-AZ
- [ ] Deploy production DynamoDB tables
  - Enable point-in-time recovery
  - Configure on-demand capacity
- [ ] Deploy production S3 buckets
  - Enable versioning
  - Configure lifecycle policies
- [ ] Create production KMS keys
- [ ] Set up CloudTrail audit logging

#### 7.2 Deployment Pipeline
- [ ] Set up GitHub Actions workflow
  - Run tests on PR
  - Build Lambda packages
  - Pulumi preview
  - Manual approval for prod
  - Pulumi up (deploy)
  - Smoke tests
- [ ] Configure blue/green deployment for Lambdas
- [ ] Set up rollback procedures

#### 7.3 Production Slack App
- [ ] Create production Slack app
- [ ] Configure OAuth scopes
- [ ] Set up event subscriptions
- [ ] Update webhook URL
- [ ] Test in production workspace

#### 7.4 Gradual Rollout
- [ ] Beta testing with 5 users (week 1)
- [ ] Expand to 25 users (week 2)
- [ ] Full rollout to all users (week 3)
- [ ] Monitor metrics at each stage
- [ ] Gather user feedback

#### 7.5 Documentation
- [ ] User guide (how to use the system)
- [ ] Ops runbook (incident response)
- [ ] Architecture documentation
- [ ] API documentation
- [ ] Deployment guide

**Deliverable**: System live in production

**Success Criteria**:
- Production deployment successful
- No critical issues in first week
- User satisfaction >80%
- Meeting prep completion rate >75%

## Phase 8: Future Enhancements (Weeks 10+)

### Backlog Items (Prioritized)

#### High Priority
1. **Real Agent Implementations**
   - Replace placeholder Budget Manager with real AWS Cost Explorer integration
   - Connect Incident Manager to PagerDuty/ServiceNow
   - Build HR Manager for 1-1s and reviews

2. **Additional Meeting Types**
   - Add support for interview debriefs
   - Add support for vendor meetings
   - Custom meeting types per user

3. **Enhanced Materials**
   - Auto-generate presentation slides
   - Include charts and visualizations
   - Previous meeting comparison

#### Medium Priority
4. **Voice Interface**
   - Accept voice responses during prep
   - Voice summary of materials
   - Phone call for prep session

5. **Mobile App**
   - Native iOS/Android app
   - Push notifications
   - Offline access to materials

6. **Smart Suggestions**
   - ML-based topic prioritization
   - Predicted questions based on history
   - Optimal prep timing based on user behavior

#### Low Priority
7. **Integrations**
   - Jira for project tracking
   - Linear for issue management
   - Confluence for documentation

8. **Advanced Features**
   - Multi-user prep (prep together with co-presenter)
   - Meeting outcome tracking
   - Quarterly trend analysis

## Development Guidelines

### Code Standards
- Follow Strands SDK patterns from `AGENTS.md`
- Type annotations everywhere
- Google-style docstrings
- Structured logging format
- Unit tests for all functions
- Integration tests for workflows

### Git Workflow
```
main (production)
  ↑
staging (pre-production testing)
  ↑
develop (integration)
  ↑
feature/* (individual features)
```

### Commit Messages
Use conventional commits:
- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation
- `test:` Tests
- `refactor:` Code refactoring
- `chore:` Build/tooling changes

### Code Review
- All PRs require review
- Automated tests must pass
- Manual testing required for UI changes
- Security review for IAM/auth changes

## Testing Strategy

### Unit Tests
- Test individual functions in isolation
- Mock external dependencies (Bedrock, DynamoDB, Slack)
- Fast execution (<1s per test)
- Run on every commit

### Integration Tests
- Test agent interactions
- Real DynamoDB (local instance)
- Real Bedrock calls (dev account)
- Run before merge to develop

### End-to-End Tests
- Test complete workflows
- Real infrastructure (dev environment)
- Simulated user interactions
- Run before merge to staging

### Performance Tests
- Load testing (concurrent users)
- Latency testing (p50, p95, p99)
- Cost testing (Bedrock token usage)
- Run weekly

## Success Metrics

### Technical Metrics
- **Availability**: 99.9% uptime
- **Latency**: p95 < 5s for prep notification
- **Error Rate**: < 1% failed workflows
- **Cost**: < $200/month for 100 meetings

### User Metrics
- **Adoption**: 80% of users use system monthly
- **Engagement**: 75% of meetings prepped
- **Satisfaction**: NPS > 50
- **Time Saved**: 15 min saved per meeting

### Business Metrics
- **Meeting Effectiveness**: More decisions made per meeting
- **Action Item Completion**: Higher completion rate
- **Strategic Alignment**: Big Rocks progress improved

## Risk Mitigation

### Technical Risks
| Risk | Impact | Mitigation |
|------|--------|------------|
| Bedrock API limits | High | Request quota increase, implement caching |
| Calendar API rate limits | Medium | Batch requests, cache aggressively |
| Lambda cold starts | Low | Use provisioned concurrency for critical functions |
| Step Function costs | Medium | Use Express workflows, optimize execution time |

### Business Risks
| Risk | Impact | Mitigation |
|------|--------|------------|
| Low user adoption | High | User training, gather feedback early |
| Poor material quality | High | Iterate on prompts, A/B testing |
| PHI exposure | Critical | Security audit, encrypt all data |
| Calendar access revoked | Medium | Graceful degradation, notify user |

## Timeline Summary

```
Week 1-2:  Foundation (infrastructure, Slack bot basics)
Week 3:    Calendar integration
Week 4-5:  Meeting prep workflow (core feature)
Week 6:    Context gathering
Week 7:    Post-meeting processing
Week 8:    Production hardening
Week 9:    Production deployment
Week 10+:  Enhancements and iteration
```

**Total time to MVP**: 8 weeks
**Time to production**: 9 weeks

## Resources Required

### Personnel
- 1 Full-stack engineer (Python/AWS)
- 0.25 DevOps engineer (infrastructure)
- 0.25 Product manager (requirements, testing)

### AWS Resources
- Development account
- Production account
- Estimated cost: $50/month dev, $200/month prod

### Third-Party Services
- Slack workspace (existing)
- Google/Microsoft 365 account (existing)
- GitHub account (existing)

## Next Steps

1. **Review and approve this plan** with stakeholders
2. **Set up development environment** (week 1, day 1)
3. **Create project in GitHub** and set up repository
4. **Schedule weekly check-ins** to track progress
5. **Begin Phase 1 implementation**

## Questions to Resolve

Before starting implementation:

1. **Calendar Choice**: Google Calendar or Microsoft 365?
2. **Slack Workspace**: Which workspace to deploy to?
3. **AWS Account**: Use existing account or create new?
4. **User Pilot**: Who are the 5 beta testers?
5. **Budget Approval**: Approved budget for AWS costs?
6. **Security Review**: When should security team review?
7. **Compliance**: HIPAA compliance review timeline?

---

**Document Version**: 1.0
**Last Updated**: 2025-12-16
**Owner**: Development Team
