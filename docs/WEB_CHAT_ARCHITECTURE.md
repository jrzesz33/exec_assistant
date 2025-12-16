# Web Chat Interface Architecture

## Overview

Instead of starting with Slack integration, we'll build a web-based chat interface with Google OAuth for authentication. This approach provides:
- Easier local development and testing
- Direct integration with Google Calendar (same auth flow)
- Better control over UX during early phases
- Foundation for future multi-channel support

## Architecture Components

### High-Level Flow

```
User Browser
    ↓ (HTTPS)
    ↓
CloudFront + S3 (Static Web App)
    ↓
    ↓ (REST/WebSocket)
    ↓
API Gateway
    ↓
    ├─→ Auth Lambda (Google OAuth)
    ├─→ Chat Lambda (WebSocket handler)
    ├─→ Meetings API Lambda
    └─→ Calendar Lambda
         ↓
         ↓
    ┌────┴────┐
    ↓         ↓
DynamoDB   Bedrock
(Users,    (Agents)
Sessions,
Meetings)
```

## Phase 1.5: Web Chat Foundation (Week 2.5)

### Goals
- Add web frontend with Google OAuth
- Create user management system
- Implement WebSocket-based chat
- Real-time meeting prep experience

### New Components

#### 1. User Model & Authentication

**File**: `src/exec_assistant/shared/models.py` (extend)

```python
class User(BaseModel):
    """User account linked to Google identity."""

    user_id: str              # UUID
    google_id: str            # Google's unique ID
    email: str                # Google email
    name: str                 # Display name
    picture_url: str | None   # Profile picture

    # Calendar integration
    calendar_connected: bool = False
    calendar_refresh_token: str | None = None  # Encrypted

    # Preferences
    timezone: str = "America/New_York"
    notification_preferences: dict[str, bool]

    created_at: datetime
    last_login_at: datetime
```

**File**: `src/exec_assistant/shared/auth.py` (new)

```python
class GoogleOAuthHandler:
    """Handle Google OAuth 2.0 flow."""

    def get_authorization_url() -> str:
        """Generate OAuth authorization URL."""

    def exchange_code_for_tokens(code: str) -> dict:
        """Exchange authorization code for access/refresh tokens."""

    def verify_id_token(id_token: str) -> dict:
        """Verify and decode Google ID token."""

    def refresh_access_token(refresh_token: str) -> dict:
        """Refresh expired access token."""
```

#### 2. Web Frontend

**Tech Stack**: React + TypeScript + Vite

**Structure**:
```
frontend/
├── src/
│   ├── components/
│   │   ├── Auth/
│   │   │   ├── GoogleLoginButton.tsx
│   │   │   └── AuthCallback.tsx
│   │   ├── Chat/
│   │   │   ├── ChatWindow.tsx
│   │   │   ├── MessageList.tsx
│   │   │   ├── MessageInput.tsx
│   │   │   └── TypingIndicator.tsx
│   │   ├── Meetings/
│   │   │   ├── MeetingList.tsx
│   │   │   ├── MeetingCard.tsx
│   │   │   └── PrepButton.tsx
│   │   └── Layout/
│   │       ├── Header.tsx
│   │       ├── Sidebar.tsx
│   │       └── MainLayout.tsx
│   ├── services/
│   │   ├── api.ts          # REST API client
│   │   ├── websocket.ts    # WebSocket client
│   │   └── auth.ts         # Auth utilities
│   ├── hooks/
│   │   ├── useAuth.ts
│   │   ├── useChat.ts
│   │   └── useMeetings.ts
│   ├── context/
│   │   └── AuthContext.tsx
│   └── App.tsx
├── package.json
├── vite.config.ts
└── tsconfig.json
```

**Key Features**:
- Google OAuth login button
- Real-time chat interface (WebSocket)
- Meeting list with prep status
- Responsive design (mobile-friendly)
- Dark mode support

#### 3. API Layer

**File**: `src/exec_assistant/api/` (new directory)

```
api/
├── __init__.py
├── auth_handler.py        # OAuth endpoints
├── websocket_handler.py   # WebSocket chat
├── meetings_handler.py    # REST API for meetings
├── users_handler.py       # User CRUD
└── middleware.py          # JWT validation, CORS
```

**Endpoints**:

**Authentication**:
- `POST /auth/google/login` - Get OAuth URL
- `POST /auth/google/callback` - Handle OAuth callback
- `POST /auth/refresh` - Refresh JWT token
- `POST /auth/logout` - Invalidate session

**Users**:
- `GET /users/me` - Get current user profile
- `PATCH /users/me` - Update preferences
- `GET /users/me/calendar/status` - Calendar connection status
- `POST /users/me/calendar/connect` - Initiate calendar OAuth

**Meetings**:
- `GET /meetings` - List user's meetings
- `GET /meetings/{id}` - Get meeting details
- `GET /meetings/{id}/materials` - Get prep materials
- `POST /meetings/{id}/prep/start` - Start prep session

**Chat** (WebSocket):
- `wss://api.example.com/chat` - WebSocket connection
  - Messages: `{"type": "message", "content": "..."}`
  - System events: `{"type": "prep_complete", "materials_url": "..."}`

#### 4. Session & JWT Management

**File**: `src/exec_assistant/shared/jwt_handler.py` (new)

```python
class JWTHandler:
    """JWT token generation and validation."""

    def create_access_token(user_id: str, expires_minutes: int = 60) -> str:
        """Create JWT access token."""

    def create_refresh_token(user_id: str, expires_days: int = 30) -> str:
        """Create JWT refresh token."""

    def verify_token(token: str) -> dict:
        """Verify and decode JWT token."""
```

**Token Storage**:
- Access token: Short-lived (1 hour), stored in memory
- Refresh token: Long-lived (30 days), stored in httpOnly cookie
- Tokens signed with RS256 (KMS-managed keys)

## Infrastructure Changes

### New Resources (Pulumi)

**File**: `infrastructure/api.py` (new)

```python
# API Gateway (WebSocket + REST)
api_gateway = aws.apigatewayv2.Api(
    "exec-assistant-api",
    protocol_type="WEBSOCKET",  # For chat
)

rest_api_gateway = aws.apigatewayv2.Api(
    "exec-assistant-rest-api",
    protocol_type="HTTP",  # For REST endpoints
)

# CloudFront + S3 for static frontend
frontend_bucket = aws.s3.Bucket(
    "exec-assistant-frontend",
    website=aws.s3.BucketWebsiteArgs(
        index_document="index.html",
        error_document="index.html",  # For SPA routing
    ),
)

cloudfront_distribution = aws.cloudfront.Distribution(
    "exec-assistant-cdn",
    origins=[...],
    default_cache_behavior={...},
)

# Cognito User Pool (alternative to custom JWT)
# Optional: Use AWS Cognito instead of custom JWT handling
user_pool = aws.cognito.UserPool(
    "exec-assistant-users",
    ...
)
```

**New DynamoDB Table**:
```python
users_table = aws.dynamodb.Table(
    "exec-assistant-users-dev",
    hash_key="user_id",
    attributes=[
        {"name": "user_id", "type": "S"},
        {"name": "google_id", "type": "S"},
        {"name": "email", "type": "S"},
    ],
    global_secondary_indexes=[
        # Index for looking up by Google ID
        {
            "name": "GoogleIdIndex",
            "hash_key": "google_id",
            "projection_type": "ALL",
        },
        # Index for looking up by email
        {
            "name": "EmailIndex",
            "hash_key": "email",
            "projection_type": "ALL",
        },
    ],
)
```

## Implementation Plan

### Week 2.5: Days 1-2 (User Auth & Models)

**Tasks**:
- [ ] Add `User` model to `shared/models.py`
- [ ] Create `shared/auth.py` with Google OAuth handler
- [ ] Create `shared/jwt_handler.py` for token management
- [ ] Add `users` DynamoDB table to Pulumi
- [ ] Write unit tests for auth flow
- [ ] Create API Lambda handler for auth endpoints

**Deliverable**: User can authenticate with Google and receive JWT

### Week 2.5: Days 3-4 (Web Frontend Basics)

**Tasks**:
- [ ] Initialize React + Vite project in `frontend/`
- [ ] Set up TypeScript, ESLint, Prettier
- [ ] Implement Google OAuth login flow
- [ ] Create auth context and protected routes
- [ ] Design basic UI layout (header, sidebar, main area)
- [ ] Set up API client with JWT handling

**Deliverable**: Users can log in and see authenticated dashboard

### Week 2.5: Days 5-6 (Chat Interface)

**Tasks**:
- [ ] Create WebSocket Lambda handler
- [ ] Implement WebSocket connection management (DynamoDB for connection IDs)
- [ ] Build chat UI components
- [ ] Implement message sending/receiving
- [ ] Add typing indicators
- [ ] Handle disconnection/reconnection

**Deliverable**: Real-time chat working between user and system

### Week 2.5: Day 7 (Meetings Integration)

**Tasks**:
- [ ] Create meetings REST API endpoints
- [ ] Build MeetingList component
- [ ] Add "Start Prep" button to meetings
- [ ] Connect prep button to WebSocket chat session
- [ ] Test end-to-end meeting prep flow

**Deliverable**: User can view meetings and start prep via web chat

## Updated Phase 2: Calendar Integration

With web chat in place, Phase 2 remains similar but uses web UI:

### Week 3: Calendar Integration

**Changes**:
- OAuth flow already implemented (reuse for calendar)
- Calendar connection UI in frontend
- REST API endpoints for calendar status
- Same calendar monitor Lambda as planned

**Flow**:
1. User logs in with Google (OAuth)
2. User clicks "Connect Calendar" in settings
3. OAuth consent screen for calendar access
4. Store refresh token (encrypted) in Users table
5. Calendar monitor runs every 2 hours
6. New meetings → notifications in web UI
7. User clicks "Prep Now" → opens chat session

## Data Flow Examples

### Authentication Flow

```
1. User clicks "Sign in with Google"
   → Frontend redirects to Google OAuth URL

2. User approves in Google
   → Google redirects to /auth/google/callback

3. Callback Lambda:
   - Exchange code for tokens
   - Verify ID token
   - Look up user by google_id (or create new user)
   - Generate JWT access + refresh tokens
   - Return tokens to frontend

4. Frontend stores tokens:
   - Access token: localStorage (short-lived)
   - Refresh token: httpOnly cookie (long-lived)

5. All API calls include: Authorization: Bearer <access_token>
```

### Meeting Prep Flow

```
1. User sees meeting in MeetingList
2. Clicks "Start Prep" button
   → POST /meetings/{id}/prep/start

3. API creates ChatSession in DynamoDB
   → Returns session_id

4. Frontend opens WebSocket connection
   → wss://api/chat?session_id={session_id}

5. Backend (via WebSocket Lambda):
   - Loads ChatSession
   - Invokes Meeting Coordinator agent
   - Agent asks prep questions
   - Streams messages to WebSocket

6. User responds via chat UI
   → Messages sent over WebSocket
   → Agent processes responses

7. Agent generates materials
   → Stores in S3
   → Sends completion message with URL

8. Frontend displays "Materials Ready" with link
```

## Security Considerations

### Authentication
- Google OAuth 2.0 with PKCE flow
- JWT tokens signed with RS256 (asymmetric)
- Token rotation on refresh
- Secure httpOnly cookies for refresh tokens

### API Security
- All endpoints require valid JWT
- CORS configured for frontend domain only
- Rate limiting on auth endpoints
- Input validation with Pydantic

### Data Security
- Calendar refresh tokens encrypted at rest (KMS)
- No PHI in logs or client-side code
- WebSocket connections validated per message
- XSS protection (Content Security Policy)

## Configuration Changes

**File**: `config/webapp.yaml` (new)

```yaml
webapp:
  frontend:
    domain: "app.example.com"
    api_domain: "api.example.com"

  google_oauth:
    client_id: "${GOOGLE_OAUTH_CLIENT_ID}"
    scopes:
      - openid
      - email
      - profile
      - https://www.googleapis.com/auth/calendar.readonly

  jwt:
    access_token_expires_minutes: 60
    refresh_token_expires_days: 30
    algorithm: RS256

  websocket:
    idle_timeout_seconds: 300
    max_connections_per_user: 3

  cors:
    allowed_origins:
      - "https://app.example.com"
      - "http://localhost:3000"  # For dev
```

## Testing Strategy

### Unit Tests
- Auth flow (token generation, verification)
- User model CRUD operations
- WebSocket message handling
- JWT token validation

### Integration Tests
- Google OAuth flow (with mock Google responses)
- WebSocket connection lifecycle
- End-to-end prep session
- Calendar sync with web UI

### E2E Tests (Cypress/Playwright)
- User login flow
- Navigate to meetings
- Start prep session
- Complete Q&A
- View materials

## Deployment

### Frontend Deployment
```bash
# Build frontend
cd frontend
npm run build

# Deploy to S3
aws s3 sync dist/ s3://exec-assistant-frontend-dev/

# Invalidate CloudFront cache
aws cloudfront create-invalidation \
  --distribution-id E123456 \
  --paths "/*"
```

### Backend Deployment
```bash
# Infrastructure
cd infrastructure
pulumi up

# Lambda functions (package and deploy)
# Will add Lambda deployment in Phase 1.5 implementation
```

## Advantages of This Approach

1. **Faster Development**: No Slack app approval process
2. **Better Testing**: Full control over UI during development
3. **Calendar Integration**: Same auth flow as Google login
4. **Unified UX**: Consistent experience across all features
5. **Future-Proof**: Can add Slack/Teams later as additional channels
6. **Cost Effective**: Serverless architecture scales to zero
7. **Healthcare Compliance**: Full control over data handling

## Migration Path to Multi-Channel

Once web chat is working, we can easily add Slack:

```
                  ┌─→ Web Chat (primary)
User Authentication ─→ Slack Bot (secondary)
                  └─→ Teams Bot (future)

All channels share:
- Same agent backend
- Same data models
- Same DynamoDB tables
- Same meeting coordinator logic
```

The Slack bot code we wrote in Phase 1 is still valuable - we'll just adapt it to work alongside the web interface.

## Next Steps

1. **Review this architecture** - feedback welcome!
2. **Finalize tech stack choices**:
   - Cognito vs custom JWT? (I recommend Cognito for production)
   - React vs Vue vs Svelte? (I recommend React + TypeScript)
   - REST + WebSocket vs GraphQL + Subscriptions?
3. **Start Phase 1.5 implementation**
4. **Design mockups** (optional but helpful)

Ready to proceed with implementation?
