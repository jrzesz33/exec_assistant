# Testing and Validation Workflow

This document provides a comprehensive testing strategy for the Executive Assistant multi-agent system, with special focus on catching bugs before AWS Lambda deployment.

## Table of Contents

1. [Overview](#overview)
2. [Testing Pyramid](#testing-pyramid)
3. [Local Testing](#local-testing)
4. [Pre-Deployment Validation](#pre-deployment-validation)
5. [Post-Deployment Health Checks](#post-deployment-health-checks)
6. [Common Issues and Solutions](#common-issues-and-solutions)

---

## Overview

**Critical Rule**: No code changes are deployed to AWS without passing the complete validation workflow.

The testing workflow consists of three layers:
1. **Unit Tests**: Fast, isolated tests with mocked dependencies
2. **Integration Tests**: Tests with real AWS services (Bedrock, DynamoDB)
3. **End-to-End Tests**: Complete workflow tests simulating production scenarios

---

## Testing Pyramid

```
                    /\
                   /  \
                  /E2E \          <- Slowest, most comprehensive
                 /------\
                /        \
               /Integration\      <- Medium speed, real AWS calls
              /------------\
             /              \
            /   Unit Tests   \   <- Fastest, mocked dependencies
           /------------------\
```

### Unit Tests (Base Layer)
- **Purpose**: Test individual functions and agent tools in isolation
- **Speed**: Very fast (< 1 second per test)
- **Dependencies**: All AWS services mocked using `moto`
- **When to Run**: After every code change, before committing

### Integration Tests (Middle Layer)
- **Purpose**: Test agents with real Bedrock calls and AWS services
- **Speed**: Medium (2-5 seconds per test)
- **Dependencies**: Requires AWS credentials and Bedrock access
- **When to Run**: Before creating pull requests

### End-to-End Tests (Top Layer)
- **Purpose**: Test complete workflows (meeting prep, incident response)
- **Speed**: Slow (10-30 seconds per test)
- **Dependencies**: Full AWS stack, calendar integration mocks
- **When to Run**: Before production deployment

---

## Local Testing

### Environment Setup

Always use the Python virtual environment:

```bash
# Activate virtual environment
source .venv/bin/activate

# Verify activation
which python  # Should show: /workspaces/exec_assistant/.venv/bin/python
```

### Set Environment Variables

Create a `.env.test` file (gitignored):

```bash
# Required for all tests
ENV=local
AWS_REGION=us-east-1

# For mocked tests (default)
AWS_ACCESS_KEY_ID=testing
AWS_SECRET_ACCESS_KEY=testing

# For integration tests with real Bedrock
AWS_BEDROCK_ENABLED=1
# Use real AWS credentials (aws configure or environment variables)

# DynamoDB table names (mocked)
CHAT_SESSIONS_TABLE_NAME=test-chat-sessions
MEETINGS_TABLE_NAME=test-meetings

# JWT for auth tests
JWT_SECRET_KEY=test-secret-key-for-development-only
```

Load environment:
```bash
source .env.test
# Or use export for individual variables
export ENV=local
```

### Running Unit Tests

Run all unit tests with mocked AWS services:

```bash
# All tests
pytest tests/ -v

# Specific test file
pytest tests/test_meeting_coordinator.py -v

# Specific test class or method
pytest tests/test_meeting_coordinator.py::TestMeetingCoordinator::test_create_agent -v

# With coverage report
pytest tests/ -v --cov=src/exec_assistant --cov-report=html
```

**Expected Output**:
```
tests/test_meeting_coordinator.py::TestMeetingCoordinator::test_create_session_manager_local PASSED
tests/test_meeting_coordinator.py::TestMeetingCoordinator::test_create_agent PASSED
tests/test_meeting_coordinator.py::TestMeetingCoordinator::test_run_meeting_coordinator_greeting PASSED
...
===== 15 passed in 2.34s =====
```

### Running Integration Tests

Integration tests require real AWS Bedrock access:

```bash
# Set Bedrock flag
export AWS_BEDROCK_ENABLED=1

# Ensure AWS credentials are configured
aws sts get-caller-identity

# Run only integration tests
pytest tests/ -v -m integration

# Run all tests including integration
pytest tests/ -v
```

**Important**: Integration tests are automatically skipped unless `AWS_BEDROCK_ENABLED=1` is set.

### Interactive Agent Testing

Test agents conversationally without writing test code:

```bash
# Mock mode (no AWS calls)
python scripts/test_agent_local.py

# Real Bedrock mode
export AWS_BEDROCK_ENABLED=1
python scripts/test_agent_local.py

# Quick non-interactive example
python scripts/test_agent_local.py --example
```

**Interactive Commands**:
- Type messages to chat with the agent
- `new` - Start a new session
- `history` - Show message count
- `quit` or `exit` - End session

---

## Pre-Deployment Validation

**Mandatory Checklist**: Complete these steps before deploying to AWS.

### Step 1: Run Automated Validation

Use the automated validation script:

```bash
# Basic validation (unit tests + syntax checks)
python scripts/validate_deployment.py

# Full validation (includes integration tests)
export AWS_BEDROCK_ENABLED=1
python scripts/validate_deployment.py --full

# Validate specific component
python scripts/validate_deployment.py --component meeting_coordinator
```

**What it checks**:
- ✅ All unit tests pass
- ✅ All integration tests pass (if `--full`)
- ✅ Python syntax is valid
- ✅ All imports resolve correctly
- ✅ Lambda package can be built
- ✅ No common runtime errors (AttributeError, ImportError)
- ✅ Code coverage meets threshold (>70%)

**Sample Output**:
```
========================================
DEPLOYMENT VALIDATION REPORT
========================================

✅ Python Syntax: PASSED
✅ Import Resolution: PASSED
✅ Unit Tests: PASSED (15/15)
✅ Integration Tests: PASSED (3/3)
✅ Lambda Package Build: PASSED
✅ Code Coverage: 82% (threshold: 70%)

========================================
VALIDATION STATUS: READY FOR DEPLOYMENT
========================================
```

### Step 2: Test Lambda Locally

Simulate the Lambda environment before deploying:

```bash
# Test with mock AWS services
python scripts/test_lambda_locally.py --event test_events/chat_message.json

# Test with real Bedrock
export AWS_BEDROCK_ENABLED=1
python scripts/test_lambda_locally.py --event test_events/chat_message.json --real-aws

# Test specific handler function
python scripts/test_lambda_locally.py --handler agent_handler --event test_events/chat_message.json
```

**Sample Event** (`test_events/chat_message.json`):
```json
{
  "httpMethod": "POST",
  "path": "/chat/send",
  "headers": {
    "authorization": "Bearer <valid-jwt-token>"
  },
  "body": "{\"message\": \"Hello, I need help with meeting prep\"}"
}
```

**Expected Response**:
```json
{
  "statusCode": 200,
  "headers": {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*"
  },
  "body": "{\"session_id\": \"...\", \"message\": \"Hello! I'm your Meeting Coordinator...\"}"
}
```

### Step 3: Verify Code Quality

Run linting and type checking:

```bash
# Lint with ruff
ruff check src/ tests/

# Format code
ruff format src/ tests/

# Type checking with mypy (if configured)
mypy src/
```

### Step 4: Review CloudWatch Logs Simulation

Check for common runtime errors:

```bash
# Simulate CloudWatch log patterns
python scripts/validate_deployment.py --check-logs
```

**Common Errors to Check**:
- `AttributeError: 'dict' object has no attribute 'content'`
- `ImportError: No module named 'xyz'`
- `KeyError: 'session_id'`
- Timeout errors
- Memory limit exceeded

---

## Post-Deployment Health Checks

After deploying to AWS, perform these health checks.

### Immediate Health Check (< 5 minutes)

```bash
# Check Lambda function logs
aws logs tail /aws/lambda/exec-assistant-agent-handler --follow

# Invoke Lambda directly
aws lambda invoke \
  --function-name exec-assistant-agent-handler \
  --payload file://test_events/chat_message.json \
  response.json

cat response.json
```

### Smoke Tests (< 10 minutes)

Test critical paths:

1. **Authentication Flow**
   ```bash
   # Get access token
   curl -X POST https://api.exec-assistant.example.com/auth/token \
     -H "Content-Type: application/json" \
     -d '{"user_id": "test-user", "password": "test-password"}'
   ```

2. **Chat Message**
   ```bash
   # Send chat message
   curl -X POST https://api.exec-assistant.example.com/chat/send \
     -H "Authorization: Bearer <access-token>" \
     -H "Content-Type: application/json" \
     -d '{"message": "Hello"}'
   ```

3. **Meeting Coordinator Tools**
   - Test `get_upcoming_meetings` is called correctly
   - Test `save_prep_response` saves to DynamoDB
   - Verify session persistence in S3

### Monitoring Checklist

Monitor these metrics for 24 hours post-deployment:

- **CloudWatch Logs**: No ERROR or CRITICAL level logs
- **Lambda Metrics**:
  - Invocation count > 0
  - Error rate < 1%
  - Duration < 5 seconds (p99)
  - Throttles = 0
- **DynamoDB Metrics**:
  - Read/write capacity not exceeded
  - System errors = 0
- **API Gateway**:
  - 4xx errors < 5%
  - 5xx errors < 0.1%
  - Latency < 2 seconds (p95)

---

## Common Issues and Solutions

### Issue 1: AttributeError - 'dict' object has no attribute 'content'

**Symptom**:
```python
len(response.message.content[0].text)
# AttributeError: 'dict' object has no attribute 'content'
```

**Root Cause**: Strands SDK returns `response.message` as a dictionary, not an object.

**Solution**:
```python
# INCORRECT
len(response.message.content[0].text)

# CORRECT
len(response.message["content"][0]["text"])
```

**Prevention**: Always check Strands SDK documentation for response format.

### Issue 2: S3SessionManager in Local Environment

**Symptom**:
```
ClientError: Unable to locate credentials
```

**Root Cause**: `ENV` is not set to `local`, so code tries to use S3.

**Solution**:
```bash
export ENV=local
```

**Prevention**: Always set `ENV=local` for local testing.

### Issue 3: Import Errors in Lambda

**Symptom**:
```
ImportError: No module named 'exec_assistant'
```

**Root Cause**: Lambda package not built correctly or missing dependencies.

**Solution**:
1. Rebuild Lambda package:
   ```bash
   cd infrastructure
   pulumi up --yes
   ```

2. Verify package contents:
   ```bash
   unzip -l .lambda_build_agent/package.zip | grep exec_assistant
   ```

**Prevention**: Run `validate_deployment.py --check-package` before deploying.

### Issue 4: Bedrock Model Access Denied

**Symptom**:
```
AccessDeniedException: User is not authorized to perform: bedrock:InvokeModel
```

**Root Cause**: IAM role lacks Bedrock permissions or model not enabled.

**Solution**:
1. Enable model in AWS Console: Bedrock → Model access → Request access
2. Update IAM role in `infrastructure/lambda_functions.py`:
   ```python
   iam.PolicyStatement(
       actions=["bedrock:InvokeModel"],
       resources=["arn:aws:bedrock:*::foundation-model/us.amazon.nova-lite-v1:0"],
   )
   ```

**Prevention**: Check IAM permissions during validation.

### Issue 5: Session Files Not Persisting

**Symptom**: Agent doesn't remember conversation context.

**Root Cause**: Session manager not configured correctly.

**Solution**:
```python
# Ensure session_id is passed correctly
session_manager = create_session_manager(session_id)

# For local testing
ENV=local  # Uses FileSessionManager with .sessions/ directory

# For production
ENV=prod
SESSIONS_BUCKET_NAME=exec-assistant-sessions
```

**Prevention**: Test session persistence with multiple messages.

### Issue 6: DynamoDB ValidationException - Empty String in Index Key

**Symptom**:
```
botocore.exceptions.ClientError: An error occurred (ValidationException) when calling the PutItem operation:
One or more parameter values are not valid. A value specified for a secondary index key is not supported.
The AttributeValue for a key attribute cannot contain an empty string value.
IndexName: MeetingIndex, IndexKey: meeting_id
```

**Root Cause**: DynamoDB does not allow empty strings in fields used as Global Secondary Index (GSI) keys.

**Solution**:

**INCORRECT** - Setting field to empty string:
```python
chat_session = ChatSession(
    session_id="abc-123",
    user_id="U12345",
    meeting_id="",  # Empty string - WRONG!
)
```

**CORRECT** - Use None or omit the field:
```python
# Option 1: Use None
chat_session = ChatSession(
    session_id="abc-123",
    user_id="U12345",
    meeting_id=None,  # Correct
)

# Option 2: Omit field entirely (if optional)
chat_session = ChatSession(
    session_id="abc-123",
    user_id="U12345",
    # No meeting_id - also correct
)
```

**Model Implementation** - Omit empty strings in `to_dynamodb()`:
```python
def to_dynamodb(self) -> dict[str, Any]:
    """Convert to DynamoDB item format."""
    data = self.model_dump()

    # Remove meeting_id if empty (MeetingIndex GSI constraint)
    if not data.get("meeting_id"):
        data.pop("meeting_id", None)

    return data
```

**Prevention**:
1. Run DynamoDB validation tests: `pytest tests/test_dynamodb_validation.py -v`
2. Use pre-deployment validation: `python scripts/validate_deployment.py` (includes DynamoDB checks)
3. Review GSI keys in `infrastructure/storage.py` before model changes

**DynamoDB Constraints to Remember**:
- ❌ No empty strings in index keys (primary or secondary)
- ❌ No missing required attributes
- ✅ Use `None` or omit attributes instead of empty strings
- ✅ Validate data types match schema

**Tables with GSI Keys**:

| Table | GSI Name | Hash Key | Range Key |
|-------|----------|----------|-----------|
| chat-sessions | MeetingIndex | meeting_id | - |
| chat-sessions | UserIndex | user_id | - |
| meetings | UserStartTimeIndex | user_id | start_time |
| action-items | MeetingIndex | meeting_id | - |
| action-items | OwnerIndex | owner | - |
| users | GoogleIdIndex | google_id | - |
| users | EmailIndex | email | - |

**Testing DynamoDB Models Locally**:

```bash
# Run DynamoDB validation tests
pytest tests/test_dynamodb_validation.py -v

# Test specific model serialization
pytest tests/test_dynamodb_validation.py::TestChatSessionDynamoDB::test_chat_session_without_meeting_id -v

# Validate all models before deployment
python scripts/validate_deployment.py
```

**What the validation checks**:
- No empty strings in GSI keys
- Datetime fields are ISO strings
- Optional fields handled correctly
- Roundtrip serialization preserves data

---

## Quick Reference

### Pre-Commit Checklist

Before committing code:

- [ ] Virtual environment activated
- [ ] `ENV=local` set
- [ ] All unit tests pass: `pytest tests/ -v`
- [ ] Code formatted: `ruff format src/ tests/`
- [ ] No linting errors: `ruff check src/ tests/`

### Pre-PR Checklist

Before creating pull request:

- [ ] All pre-commit checks pass
- [ ] Integration tests pass: `AWS_BEDROCK_ENABLED=1 pytest tests/ -v -m integration`
- [ ] Code coverage > 70%: `pytest --cov=src/exec_assistant --cov-report=term`
- [ ] Manual testing completed: `python scripts/test_agent_local.py`
- [ ] No TODO or FIXME comments without GitHub issues

### Pre-Deployment Checklist

Before deploying to AWS:

- [ ] All pre-PR checks pass
- [ ] Validation script passes: `python scripts/validate_deployment.py --full`
- [ ] Lambda test succeeds: `python scripts/test_lambda_locally.py`
- [ ] Infrastructure changes reviewed (if applicable)
- [ ] Rollback plan documented
- [ ] Monitoring alerts configured

### Post-Deployment Checklist

After deploying to AWS:

- [ ] Smoke tests pass (< 10 minutes)
- [ ] CloudWatch logs show no errors (< 1 hour)
- [ ] Lambda metrics healthy (< 24 hours)
- [ ] User acceptance testing completed
- [ ] Documentation updated (if needed)

---

## Testing Tools Reference

### pytest

```bash
# Run all tests
pytest

# Verbose output
pytest -v

# Stop on first failure
pytest -x

# Run specific marker
pytest -m integration

# Skip specific marker
pytest -m "not integration"

# Run with coverage
pytest --cov=src/exec_assistant --cov-report=html

# Parallel execution
pytest -n auto
```

### moto (AWS Mocking)

```python
from moto import mock_aws

@mock_aws
def test_with_mocked_aws():
    # All boto3 calls are mocked
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    table = dynamodb.create_table(...)
```

### Validation Script

```bash
# Basic validation
python scripts/validate_deployment.py

# Full validation with integration tests
python scripts/validate_deployment.py --full

# Validate specific component
python scripts/validate_deployment.py --component meeting_coordinator

# Check Lambda package
python scripts/validate_deployment.py --check-package

# Simulate CloudWatch logs check
python scripts/validate_deployment.py --check-logs
```

### Lambda Test Harness

```bash
# Test with mock AWS
python scripts/test_lambda_locally.py --event test_events/chat_message.json

# Test with real AWS
python scripts/test_lambda_locally.py --event test_events/chat_message.json --real-aws

# Show full stack traces
python scripts/test_lambda_locally.py --event test_events/chat_message.json --verbose
```

---

## Additional Resources

- **Strands SDK Documentation**: https://strandsagents.com/
- **AWS Lambda Best Practices**: https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html
- **pytest Documentation**: https://docs.pytest.org/
- **moto Documentation**: https://docs.getmoto.org/

---

## Feedback and Improvements

If you encounter issues not covered in this guide, please:

1. Document the issue in the "Common Issues" section above
2. Create a GitHub issue with reproduction steps
3. Update the pre-deployment checklist if a new check is needed

**Remember**: Every production bug that could have been caught locally improves this workflow.
