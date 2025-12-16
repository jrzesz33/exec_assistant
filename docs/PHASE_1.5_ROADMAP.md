# Phase 1.5: Web Chat Interface - Implementation Roadmap

## Overview

**Duration**: 1 week (7 days)
**Goal**: Replace Slack bot with web-based chat interface using Google OAuth
**Status**: Ready to start

## Why Phase 1.5?

Between Phase 1 (Foundation) and Phase 2 (Calendar), we're adding a web interface to make development and testing easier. This gives us:
- Self-service testing without Slack workspace setup
- Direct Google Calendar integration (same OAuth)
- Better control over UX during development
- Foundation for production web app

## What We Keep from Phase 1

✅ All existing work is still valuable:
- Data models (Meeting, ChatSession, MeetingMaterials) - **unchanged**
- Configuration system (agents.yaml, meeting_types.yaml) - **unchanged**
- DynamoDB tables (meetings, chat_sessions) - **add users table**
- S3 buckets - **unchanged**
- Config loader - **unchanged**
- All tests - **still pass**

We're **adding** a web frontend, not replacing the backend!

## What's New

🆕 Components we're adding:
- Web frontend (React app)
- User authentication (Google OAuth)
- User model and management
- WebSocket for real-time chat
- REST API for meetings/users
- JWT token handling

## Day-by-Day Plan

### Day 1: User Model & Auth Backend (Monday)

**Morning**: Extend data models
```python
# src/exec_assistant/shared/models.py
class User(BaseModel):
    user_id: str
    google_id: str
    email: str
    name: str
    picture_url: str | None
    calendar_connected: bool
    calendar_refresh_token: str | None
    timezone: str
    preferences: dict[str, Any]
    created_at: datetime
    last_login_at: datetime
```

**Afternoon**: Google OAuth handler
```python
# src/exec_assistant/shared/auth.py
class GoogleOAuthHandler:
    - get_authorization_url()
    - exchange_code_for_tokens()
    - verify_id_token()
    - refresh_access_token()
```

**Evening**: JWT token management
```python
# src/exec_assistant/shared/jwt_handler.py
class JWTHandler:
    - create_access_token()
    - create_refresh_token()
    - verify_token()
```

**Tests**: Unit tests for all auth components

**Deliverable**: Auth backend ready, tests passing

---

### Day 2: Infrastructure & API Setup (Tuesday)

**Morning**: Pulumi infrastructure updates
```python
# infrastructure/storage.py - add Users table
# infrastructure/api.py - new file
  - API Gateway (HTTP + WebSocket)
  - Lambda function stubs
  - CloudFront + S3 for frontend
```

**Afternoon**: API Lambda handlers (stubs)
```python
# src/exec_assistant/api/
  - auth_handler.py (OAuth endpoints)
  - users_handler.py (user CRUD)
  - meetings_handler.py (meetings API)
  - websocket_handler.py (chat handler)
  - middleware.py (JWT validation)
```

**Evening**: Deploy infrastructure
```bash
cd infrastructure
pulumi up
# Creates API Gateway, Users table, Lambda functions
```

**Tests**: Integration tests for API handlers

**Deliverable**: API infrastructure deployed

---

### Day 3: Frontend Setup & Auth UI (Wednesday)

**Morning**: Initialize React project
```bash
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install @tanstack/react-query axios
```

**Afternoon**: Build auth components
```typescript
// frontend/src/components/Auth/
  - GoogleLoginButton.tsx
  - AuthCallback.tsx
  - ProtectedRoute.tsx

// frontend/src/context/
  - AuthContext.tsx

// frontend/src/services/
  - auth.ts (Google OAuth flow)
  - api.ts (API client with JWT)
```

**Evening**: Basic layout
```typescript
// frontend/src/components/Layout/
  - Header.tsx (user profile, logout)
  - Sidebar.tsx (navigation)
  - MainLayout.tsx
```

**Tests**: Component tests with Vitest

**Deliverable**: User can log in with Google

---

### Day 4: Chat Interface UI (Thursday)

**Morning**: Chat components
```typescript
// frontend/src/components/Chat/
  - ChatWindow.tsx (main container)
  - MessageList.tsx (scrollable messages)
  - MessageInput.tsx (text input)
  - Message.tsx (single message bubble)
  - TypingIndicator.tsx
```

**Afternoon**: WebSocket client
```typescript
// frontend/src/services/websocket.ts
class WebSocketClient {
  - connect(sessionId: string)
  - send(message: string)
  - onMessage(callback)
  - disconnect()
}

// frontend/src/hooks/useChat.ts
export function useChat(sessionId: string) {
  // React hook for chat functionality
}
```

**Evening**: Style chat UI
- Message bubbles (user vs assistant)
- Timestamp display
- Typing animation
- Responsive layout

**Tests**: WebSocket mock tests

**Deliverable**: Chat UI complete (no backend yet)

---

### Day 5: WebSocket Backend (Friday)

**Morning**: WebSocket Lambda handler
```python
# src/exec_assistant/api/websocket_handler.py

def connect_handler(event, context):
    # Store connection_id in DynamoDB
    # Validate JWT token
    # Associate connection with user_id

def disconnect_handler(event, context):
    # Remove connection from DynamoDB

def message_handler(event, context):
    # Parse message from client
    # Load ChatSession
    # Route to agent or update session
    # Send response back through WebSocket
```

**Afternoon**: Connection management
```python
# DynamoDB table for active connections
connections_table = {
    "connection_id": "abc123",
    "user_id": "user-456",
    "session_id": "session-789",
    "connected_at": "2025-01-15T10:00:00Z",
}
```

**Evening**: Integrate with chat session
```python
# When user sends message:
1. Receive via WebSocket
2. Load ChatSession from DynamoDB
3. Add message to session
4. Update session state
5. Send acknowledgment back
```

**Tests**: WebSocket handler tests with moto

**Deliverable**: WebSocket backend working

---

### Day 6: End-to-End Integration (Saturday)

**Morning**: Meetings list UI
```typescript
// frontend/src/components/Meetings/
  - MeetingList.tsx
  - MeetingCard.tsx (shows meeting details)
  - PrepButton.tsx ("Start Prep" button)

// frontend/src/services/meetings.ts
async function getMeetings(): Promise<Meeting[]>
async function startPrep(meetingId: string): Promise<ChatSession>
```

**Afternoon**: Connect prep to chat
```typescript
// User flow:
1. View MeetingList
2. Click "Start Prep" on a meeting
3. API creates ChatSession
4. Frontend opens chat window
5. WebSocket connects to session
6. Agent starts asking prep questions
```

**Evening**: Polish UX
- Loading states
- Error handling
- Success notifications
- Smooth transitions

**Tests**: E2E test with Playwright

**Deliverable**: Full prep flow working

---

### Day 7: Testing & Documentation (Sunday)

**Morning**: Comprehensive testing
- Unit tests for all new components
- Integration tests for API endpoints
- E2E test for complete user journey
- Load testing for WebSocket (optional)

**Afternoon**: Documentation
```markdown
# Update docs:
  - API documentation (OpenAPI spec)
  - Frontend README (setup, dev, deploy)
  - Architecture diagrams
  - User guide (screenshots)
```

**Evening**: Deployment & verification
```bash
# Deploy frontend
cd frontend
npm run build
# Upload to S3 + CloudFront

# Verify production
- Test login flow
- Test chat functionality
- Check error handling
- Monitor CloudWatch logs
```

**Tests**: All tests passing, coverage >80%

**Deliverable**: Phase 1.5 complete, ready for Phase 2

---

## Technical Decisions to Make

Before starting, we should decide:

### 1. JWT vs AWS Cognito?

**Option A: Custom JWT (what I've spec'd)**
- ✅ Full control over auth flow
- ✅ No vendor lock-in
- ✅ Simpler for development
- ❌ More code to maintain
- ❌ Need to handle token rotation

**Option B: AWS Cognito**
- ✅ Managed service (less code)
- ✅ Built-in user pool
- ✅ Handles token rotation
- ✅ HIPAA compliant by default
- ❌ AWS-specific
- ❌ Learning curve

**Recommendation**: Start with custom JWT (simpler), migrate to Cognito for production

### 2. WebSocket Connection Management?

**Option A: DynamoDB for connection IDs (what I've spec'd)**
- ✅ Serverless, scales automatically
- ✅ Familiar technology (already using DynamoDB)
- ❌ Additional costs per connection

**Option B: ElastiCache (Redis)**
- ✅ Very fast lookups
- ✅ Built-in pub/sub
- ❌ Requires VPC setup
- ❌ Fixed costs (even when idle)

**Recommendation**: DynamoDB (keeps architecture serverless)

### 3. Frontend State Management?

**Option A: React Context + TanStack Query (what I've spec'd)**
- ✅ Modern, lightweight
- ✅ Great for server state
- ✅ Built-in caching
- ❌ Not ideal for complex client state

**Option B: Redux Toolkit**
- ✅ Predictable state updates
- ✅ Time-travel debugging
- ❌ More boilerplate
- ❌ Overkill for our use case

**Recommendation**: Context + TanStack Query (simpler for our needs)

### 4. Real-time Communication?

**Option A: WebSocket (what I've spec'd)**
- ✅ True bidirectional communication
- ✅ Low latency
- ✅ Works well for chat
- ❌ Connection management overhead

**Option B: Server-Sent Events (SSE)**
- ✅ Simpler than WebSocket
- ✅ Auto-reconnection
- ❌ One-way only (server → client)
- ❌ Need separate POST for client → server

**Option C: HTTP long-polling**
- ✅ Works everywhere
- ❌ Higher latency
- ❌ More server load

**Recommendation**: WebSocket (best for chat experience)

## Resource Estimates

### AWS Costs (Development)

**New resources**:
- API Gateway WebSocket: ~$0.25/million messages
- Lambda function calls: ~$0.20/million invocations
- CloudFront: ~$0.085/GB data transfer
- S3 static hosting: ~$0.023/GB storage

**Estimated monthly cost** (dev with light usage):
- Existing (Phase 1): $2-10/month
- New (Phase 1.5): $5-15/month
- **Total**: $10-25/month for development

### Development Time

- **Estimated effort**: 40-50 hours (1 full week)
- **Critical path**: Backend auth → Frontend auth → Chat UI → WebSocket
- **Risk areas**: WebSocket connection management, JWT security
- **Mitigation**: Start with simple implementation, iterate based on testing

## Success Criteria

Phase 1.5 is complete when:

- [ ] User can log in with Google
- [ ] User profile displays correctly
- [ ] User can view list of meetings (even if placeholder data)
- [ ] User can click "Start Prep" on a meeting
- [ ] Chat window opens and connects via WebSocket
- [ ] User can send/receive messages in real-time
- [ ] Chat session persists in DynamoDB
- [ ] All unit tests passing (>80% coverage)
- [ ] E2E test passes for full user journey
- [ ] Frontend deployed to CloudFront
- [ ] API deployed to API Gateway
- [ ] Documentation updated

## Rollback Plan

If we need to revert:

1. **Keep all Phase 1 work** - it's still valid
2. **Frontend** - Just delete CloudFront distribution and S3 bucket
3. **API** - Delete API Gateway and Lambda functions
4. **Database** - Keep existing tables, just don't use Users table
5. **Can still proceed with Phase 2** - Calendar integration doesn't depend on web UI

No data loss, no breaking changes to existing code.

## Next Steps

1. **Review this roadmap** - Any questions or concerns?
2. **Make technical decisions** - Choose JWT vs Cognito, etc.
3. **Set up development environment** - Node.js, React dev server
4. **Create frontend skeleton** - Initialize Vite project
5. **Start Day 1 implementation** - User model and auth backend

Ready to start? Which day would you like to tackle first?
