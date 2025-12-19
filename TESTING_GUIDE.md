# Testing Guide

## Overview

This guide explains how to test the Executive Assistant agents locally during development.

## Problem Solved

The original implementation had a critical issue with `S3SessionManager` initialization:
- **Error**: `S3SessionManager.__init__() missing 2 required positional arguments: 'session_id' and 'bucket'`
- **Root Cause**: Session manager was being initialized at module level without a session_id
- **Impact**: Agents couldn't run in Lambda or locally

## Solution Architecture

### Environment-Based Session Management

The system now supports two modes:

| Mode | Environment | Session Manager | Storage Location |
|------|-------------|-----------------|------------------|
| **Local Development** | `ENV=local` | `FileSessionManager` | `.sessions/` directory |
| **Production** | `ENV=prod` | `S3SessionManager` | S3 bucket |

### Key Changes

1. **Session Manager Factory Pattern**:
   ```python
   def create_session_manager(session_id: str):
       if ENV == "local":
           return FileSessionManager(session_id=session_id, directory=".sessions")
       else:
           return S3SessionManager(session_id=session_id, bucket=SESSIONS_BUCKET_NAME, region_name=AWS_REGION)
   ```

2. **Per-Request Agent Creation**:
   ```python
   # OLD (BROKEN): Module-level agent
   session_manager = S3SessionManager(bucket_name=BUCKET)  # ❌ Missing session_id
   agent = Agent(model=model, session_manager=session_manager)

   # NEW (CORRECT): Per-request agent
   agent = create_agent(session_id)  # ✅ Creates session manager with session_id
   response = await agent.invoke_async(message)
   ```

3. **Lazy AWS Client Initialization**:
   - DynamoDB client now created on-demand instead of at module import
   - Prevents "NoRegionError" during testing
   - Allows tests to set mock credentials before client initialization

## Testing Workflow

### 1. Quick Mock Testing (No AWS Required)

Best for: Unit tests, CI/CD pipelines, development without AWS credentials

```bash
# Activate virtual environment
source .venv/bin/activate

# Set local environment
export ENV=local

# Run tests with mocks
pytest tests/test_meeting_coordinator.py -v
```

**What happens:**
- Uses `FileSessionManager` with `.sessions/` directory
- Mocks Bedrock API calls
- Mocks DynamoDB with `moto`
- No AWS credentials needed

### 2. Integration Testing (Real Bedrock)

Best for: Testing with actual AI responses, validating model behavior

```bash
# Activate virtual environment
source .venv/bin/activate

# Set environment and enable Bedrock
export ENV=local
export AWS_BEDROCK_ENABLED=1

# Ensure AWS credentials are configured
# Option 1: AWS CLI profile
aws configure

# Option 2: Environment variables
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
export AWS_REGION=us-east-1

# Run integration tests
pytest tests/test_meeting_coordinator.py -v -m integration
```

**What happens:**
- Uses `FileSessionManager` for sessions (no S3 needed)
- Makes real Bedrock API calls (costs apply)
- Validates actual agent responses
- Tests conversation flow and context retention

### 3. Interactive Local Testing

Best for: Development iteration, manual testing, exploring agent behavior

```bash
# Activate virtual environment
source .venv/bin/activate

# Set environment
export ENV=local

# Optional: Enable real Bedrock calls
# export AWS_BEDROCK_ENABLED=1

# Start interactive session
python scripts/test_agent_local.py
```

**What happens:**
- Opens interactive chat session with agent
- Session state persisted to `.sessions/`
- Can start new sessions with `new` command
- Type `quit` to exit

**Commands:**
- Type your message and press Enter
- `new` - Start a new session
- `history` - Show message count
- `quit` or `exit` - End session

### 4. Quick Example Test

Best for: Verifying setup, quick smoke test

```bash
python scripts/test_agent_local.py --example
```

Runs a single non-interactive test with greeting message.

## Test Files

### Core Test Modules

| File | Purpose |
|------|---------|
| `tests/test_utils.py` | Test utilities and helpers |
| `tests/conftest.py` | Pytest fixtures and configuration |
| `tests/test_meeting_coordinator.py` | Meeting Coordinator agent tests |
| `scripts/test_agent_local.py` | Interactive testing script |

### Test Utilities API

```python
from tests.test_utils import (
    set_local_test_env,           # Set up test environment variables
    generate_test_session_id,      # Generate unique session ID
    generate_test_user_id,         # Generate unique user ID
    create_test_dynamodb_tables,   # Create mock DynamoDB tables
    AgentTestHelper,               # Helper for conversation testing
)
```

## Environment Variables

### Required for All Modes

| Variable | Default | Description |
|----------|---------|-------------|
| `ENV` | `local` | Environment mode (`local` or `prod`) |
| `AWS_REGION` | `us-east-1` | AWS region |

### Required for Local Testing

| Variable | Default | Description |
|----------|---------|-------------|
| `CHAT_SESSIONS_TABLE_NAME` | `test-chat-sessions` | DynamoDB table for sessions |
| `MEETINGS_TABLE_NAME` | `test-meetings` | DynamoDB table for meetings |
| `JWT_SECRET_KEY` | `test-secret-key` | JWT signing key |

### Optional for Integration Testing

| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_BEDROCK_ENABLED` | `0` | Enable real Bedrock API calls (`1` or `0`) |
| `AWS_ACCESS_KEY_ID` | - | AWS credentials (if not using profile) |
| `AWS_SECRET_ACCESS_KEY` | - | AWS credentials (if not using profile) |

### Required for Production

| Variable | Default | Description |
|----------|---------|-------------|
| `SESSIONS_BUCKET_NAME` | - | S3 bucket for session storage |

## Project Structure

```
exec_assistant/
├── .sessions/                          # Local session storage (gitignored)
├── scripts/
│   └── test_agent_local.py            # Interactive testing script
├── src/
│   └── exec_assistant/
│       ├── agents/
│       │   └── meeting_coordinator.py  # Agent implementation
│       └── interfaces/
│           └── agent_handler.py        # Lambda handler
└── tests/
    ├── conftest.py                     # Pytest fixtures
    ├── test_utils.py                   # Test utilities
    └── test_meeting_coordinator.py     # Agent tests
```

## Common Issues and Solutions

### Issue: S3SessionManager initialization error

**Error:**
```
TypeError: S3SessionManager.__init__() missing 2 required positional arguments: 'session_id' and 'bucket'
```

**Solution:**
Ensure `ENV=local` is set for local testing:
```bash
export ENV=local
```

### Issue: NoRegionError from boto3

**Error:**
```
botocore.exceptions.NoRegionError: You must specify a region.
```

**Solution:**
Set AWS_REGION environment variable:
```bash
export AWS_REGION=us-east-1
```

### Issue: Module import errors

**Error:**
```
ModuleNotFoundError: No module named 'exec_assistant'
```

**Solution:**
Add src directory to PYTHONPATH:
```bash
export PYTHONPATH=/workspaces/exec_assistant/src:$PYTHONPATH
```

Or run from project root with pytest:
```bash
pytest tests/
```

### Issue: Missing test dependencies

**Error:**
```
ModuleNotFoundError: No module named 'pytest'
```

**Solution:**
Install test dependencies:
```bash
source .venv/bin/activate
pip install pytest pytest-asyncio pytest-cov moto boto3 strands-agents
```

## Best Practices

### 1. Always Activate Virtual Environment

```bash
source .venv/bin/activate
```

### 2. Use Local Mode for Development

```bash
export ENV=local
```

This avoids S3 dependencies and costs.

### 3. Mock Bedrock for Unit Tests

Don't set `AWS_BEDROCK_ENABLED` for unit tests - use mocks for speed and cost.

### 4. Clean Session Directory

Session files accumulate in `.sessions/`. Clean periodically:

```bash
rm -rf .sessions/*
```

### 5. Use Integration Tests Sparingly

Real Bedrock calls have costs. Use for validation, not regular testing.

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Test

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.13'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-asyncio pytest-cov moto

      - name: Run tests
        env:
          ENV: local
          AWS_REGION: us-east-1
        run: |
          pytest tests/ -v --cov=src/exec_assistant
```

## Cost Considerations

| Test Mode | AWS Costs | Speed | Use Case |
|-----------|-----------|-------|----------|
| **Mock Testing** | $0 | Fast | Unit tests, CI/CD |
| **Integration (Bedrock)** | ~$0.01-0.10 per test run | Moderate | Validation, pre-deployment |
| **Production** | Variable | Fast | Live system |

**Bedrock Pricing (us.amazon.nova-lite-v1:0):**
- Input: ~$0.60 per 1M tokens
- Output: ~$2.40 per 1M tokens
- Typical test conversation: 500-2000 tokens = ~$0.001-0.005

## Next Steps

1. **Add More Agent Tests**: Extend `test_meeting_coordinator.py` with edge cases
2. **Integration Tests**: Test with real calendar APIs, Slack integration
3. **End-to-End Tests**: Full workflow tests with Step Functions
4. **Performance Tests**: Load testing with concurrent sessions

## Resources

- **Strands SDK Documentation**: https://strandsagents.com/
- **AWS Bedrock Docs**: https://docs.aws.amazon.com/bedrock/
- **pytest Documentation**: https://docs.pytest.org/
- **moto (AWS mocking)**: https://github.com/getmoto/moto

## Questions?

See CLAUDE.md for development patterns and architecture details.
