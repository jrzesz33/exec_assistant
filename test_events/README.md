# Test Events

This directory contains sample AWS Lambda event files for local testing.

## Event Files

### `chat_message.json`
Basic chat message event for testing the Meeting Coordinator agent.

**Usage:**
```bash
python scripts/test_lambda_locally.py --event test_events/chat_message.json
```

**Expected Response:**
- Status Code: 200
- Body: JSON with session_id, message (agent response), and state

### `chat_message_with_session.json`
Chat message with existing session ID for testing conversation continuity.

**Usage:**
```bash
python scripts/test_lambda_locally.py --event test_events/chat_message_with_session.json
```

**Note:** Session must exist in DynamoDB (for real AWS) or will be created (for mocked tests).

### `auth_token.json`
Authentication token generation event for testing auth handler.

**Usage:**
```bash
python scripts/test_lambda_locally.py --handler auth_handler --event test_events/auth_token.json
```

**Expected Response:**
- Status Code: 200
- Body: JSON with access_token and expires_in

## Creating Custom Events

To create custom events, use the API Gateway event format:

```json
{
  "httpMethod": "POST",
  "path": "/your/path",
  "headers": {
    "authorization": "Bearer <jwt-token>",
    "content-type": "application/json"
  },
  "body": "{\"key\": \"value\"}"
}
```

**Important:** The `body` field must be a JSON string, not a JSON object.

## Testing with Real AWS

To test with real AWS services (Bedrock, DynamoDB):

```bash
# Set environment variable
export AWS_BEDROCK_ENABLED=1

# Ensure AWS credentials are configured
aws sts get-caller-identity

# Run test
python scripts/test_lambda_locally.py --event test_events/chat_message.json --real-aws
```

## JWT Tokens

The sample JWT tokens in these events are for testing only. They use a test secret key and have far-future expiration times.

**For production testing**, generate real tokens:

```bash
# Get access token from auth endpoint
curl -X POST http://localhost:8080/auth/token \
  -H "Content-Type: application/json" \
  -d '{"user_id": "your-user-id"}'

# Use returned token in authorization header
```
