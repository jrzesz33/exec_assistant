# Phase 3 Sprint 3: Prep Notification Workflow - Deployment Guide

## Overview

This deployment adds the prep notification workflow infrastructure to enable proactive meeting preparation reminders with multi-channel delivery and interactive Slack buttons.

## Infrastructure Components

### 1. Prep Trigger Handler Lambda
**File**: `src/exec_assistant/workflows/prep_trigger_handler.py`
**Handler**: `exec_assistant.workflows.prep_trigger_handler.lambda_handler`
**Trigger**: EventBridge event pattern (MeetingPrepRequired from calendar monitor)
**Memory**: 512 MB
**Timeout**: 60s

**Responsibilities**:
- Responds to `MeetingPrepRequired` events from calendar monitor
- Fetches meeting and user details from DynamoDB
- Updates meeting status to `PREP_SCHEDULED`
- Sends notifications via NotificationService (Slack → SMS → Email fallback)
- Tracks notification delivery status

**Environment Variables**:
- `MEETINGS_TABLE_NAME`: DynamoDB meetings table
- `USERS_TABLE_NAME`: DynamoDB users table
- `SLACK_BOT_TOKEN`: Slack bot OAuth token (required)
- `TWILIO_ACCOUNT_SID`: Twilio account SID (optional)
- `TWILIO_AUTH_TOKEN`: Twilio auth token (optional)
- `TWILIO_FROM_NUMBER`: Twilio sender phone (optional)
- `SES_FROM_EMAIL`: SES sender email (optional)
- `AWS_REGION`: AWS region

### 2. EventBridge Rule (MeetingPrepRequired)
**Name**: `exec-assistant-prep-trigger-{environment}`
**Event Pattern**:
```json
{
  "source": ["exec-assistant.calendar-monitor"],
  "detail-type": ["MeetingPrepRequired"]
}
```

**Target**: Prep trigger handler Lambda
**State**: ENABLED

### 3. Slack Bot Lambda
**File**: `src/exec_assistant/interfaces/slack_bot.py`
**Handler**: `exec_assistant.interfaces.slack_bot.lambda_handler`
**Trigger**: API Gateway POST /slack/webhook
**Memory**: 512 MB
**Timeout**: 30s

**Responsibilities**:
- Verifies Slack webhook signatures
- Handles slash commands (`/meetings`)
- Handles interactive messages:
  - "Start Prep" button → Creates chat session, sends DM
  - "Remind Later" button → Schedules EventBridge reminder in 2 hours
- Handles direct messages (for chat sessions)

**Environment Variables**:
- `SLACK_SIGNING_SECRET`: Slack app signing secret
- `SLACK_BOT_TOKEN`: Slack bot OAuth token
- `USERS_TABLE_NAME`: DynamoDB users table
- `MEETINGS_TABLE_NAME`: DynamoDB meetings table
- `CHAT_SESSIONS_TABLE_NAME`: DynamoDB chat sessions table
- `EVENT_BUS_NAME`: EventBridge event bus (default)
- `AWS_REGION`: AWS region
- `ENV`: Environment (dev/staging/prod)

### 4. API Gateway Integration
**Route**: `POST /slack/webhook`
**Integration**: Lambda proxy (Slack bot Lambda)

**Slack App Configuration**:
1. Set Request URL to: `{api_endpoint}/slack/webhook`
2. Enable Event Subscriptions: `message.im`
3. Enable Interactivity

### 5. IAM Permissions (added to Lambda role)

**DynamoDB**:
- `GetItem`, `PutItem`, `UpdateItem` on meetings, users, chat_sessions tables

**SES** (for email notifications):
- `SendEmail`, `SendRawEmail` on all resources

**EventBridge** (for "Remind Later" functionality):
- `PutRule`, `PutTargets`, `DeleteRule`, `RemoveTargets` on `prep-reminder-*` rules

## Deployment Steps

### Prerequisites
1. Phase 1.5 (authentication, API Gateway) must be deployed
2. Phase 3 Sprint 2 (calendar monitor) must be deployed
3. Slack app created with Bot Token and Signing Secret
4. (Optional) Twilio account for SMS notifications
5. (Optional) SES verified sender email for email notifications

### 1. Update Pulumi Configuration

Add to `Pulumi.dev.yaml`:

```yaml
exec-assistant:enable_prep_notification: "true"

# Required: Slack credentials
exec-assistant:slack_bot_token:
  secure: AAABXXXXXXXXXXXXX
exec-assistant:slack_signing_secret:
  secure: AAABXXXXXXXXXXXXX

# Optional: Twilio credentials (for SMS fallback)
exec-assistant:twilio_account_sid:
  secure: AAABXXXXXXXXXXXXX
exec-assistant:twilio_auth_token:
  secure: AAABXXXXXXXXXXXXX
exec-assistant:twilio_from_number:
  secure: AAABXXXXXXXXXXXXX

# Optional: SES sender email (for email fallback)
exec-assistant:ses_from_email: "assistant@example.com"
```

**Security Note**: Use `pulumi config set --secret` to encrypt credentials:
```bash
pulumi config set --secret slack_bot_token xoxb-your-token
pulumi config set --secret slack_signing_secret your-signing-secret
```

### 2. Run Pulumi Preview

```bash
cd infrastructure
source ../.venv/bin/activate
pulumi preview
```

**Expected Changes**:
- **+6 new resources**: prep trigger Lambda, Slack bot Lambda, EventBridge rule, 2 log groups, API route
- **~1 updated resource**: Lambda IAM role policy (new permissions)

### 3. Deploy Infrastructure

```bash
pulumi up
```

Review the changes and confirm deployment.

### 4. Configure Slack App

After deployment, get the Slack webhook URL:
```bash
pulumi stack output slack_webhook_url
```

Configure your Slack app:
1. Go to https://api.slack.com/apps
2. Select your app
3. Under "Interactivity & Shortcuts":
   - Enable Interactivity
   - Set Request URL to `{slack_webhook_url}`
4. Under "Event Subscriptions":
   - Enable Events
   - Set Request URL to `{slack_webhook_url}`
   - Subscribe to bot events: `message.im`

### 5. Verify Deployment

**Test EventBridge Rule**:
```bash
aws events put-events \
  --entries '[{
    "Source": "exec-assistant.calendar-monitor",
    "DetailType": "MeetingPrepRequired",
    "Detail": "{\"meeting_id\":\"test-123\",\"user_id\":\"U12345\",\"meeting_type\":\"leadership_team\",\"start_time\":\"2024-01-15T14:00:00Z\",\"title\":\"Test Meeting\"}"
  }]'
```

**Check CloudWatch Logs**:
```bash
aws logs tail /aws/lambda/exec-assistant-prep-trigger-dev --follow
```

**Test Slack Bot**:
1. Send `/meetings` command in Slack
2. Click a "Start Prep" button (if you have test meetings)
3. Verify DM is received from bot

## Configuration Reference

### Notification Channel Priority

Default order (with automatic fallback):
1. **Slack** - Interactive message with buttons
2. **SMS** - Text message via Twilio (if configured and user has phone)
3. **Email** - HTML email via SES (if configured)

Notifications are sent to the first available channel that succeeds. If Slack fails, SMS is attempted. If SMS fails, email is attempted.

### Meeting Prep Timing

Configured in `config/agents.yaml`:
```yaml
meeting_coordinator:
  prep_timing:
    leadership_team: 24  # Hours before meeting
    one_on_one: 24
    all_hands: 48
    default: 24
```

### Interactive Slack Message Format

```
🗓️ Meeting Prep Reminder

You have a Leadership Team coming up:
• Meeting Title
• 📅 Monday, January 15 at 2:00 PM
• ⏱️ 60 minutes
• 👥 5 attendee(s)

Time to prepare! I can help you create:
✅ Customized agenda
✅ Context from budget, incidents, and strategic priorities
✅ Question bank for discussion
✅ Note-taking template

[Start Prep Session] [Remind Me in 2 Hours]
```

## Monitoring and Troubleshooting

### CloudWatch Logs

**Prep Trigger Handler**:
```bash
aws logs tail /aws/lambda/exec-assistant-prep-trigger-dev --follow
```

**Slack Bot**:
```bash
aws logs tail /aws/lambda/exec-assistant-slack-bot-dev --follow
```

### Common Issues

**Slack notifications not arriving**:
- Check `SLACK_BOT_TOKEN` is set correctly
- Verify bot has `chat:write` scope
- Check CloudWatch logs for Slack API errors

**"Remind Later" not working**:
- Check Lambda has EventBridge permissions (`PutRule`, `PutTargets`)
- Verify `EVENT_BUS_NAME` is set to `default`
- Check CloudWatch logs for EventBridge errors

**SMS/Email fallback not working**:
- SMS: Verify Twilio credentials, user has phone_number
- Email: Verify SES sender email is verified, user has email
- Check CloudWatch logs for API errors

### Key Metrics

**Lambda Invocations**:
```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=exec-assistant-prep-trigger-dev \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-01-02T00:00:00Z \
  --period 3600 \
  --statistics Sum
```

**Lambda Errors**:
```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Errors \
  --dimensions Name=FunctionName,Value=exec-assistant-prep-trigger-dev \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-01-02T00:00:00Z \
  --period 3600 \
  --statistics Sum
```

## Security Considerations

1. **Slack Webhook Verification**: Slack bot Lambda verifies HMAC signatures on all webhooks
2. **Secrets Encryption**: All credentials stored encrypted in Pulumi config
3. **Least Privilege IAM**: Lambda role has minimal required permissions
4. **DynamoDB Encryption**: All tables encrypted at rest with KMS
5. **CloudWatch Logs**: Retained for 7 days (dev) or 30 days (prod)

## Rollback Procedure

If deployment fails or causes issues:

```bash
# Disable prep notification in config
pulumi config set enable_prep_notification false

# Revert infrastructure
pulumi up

# Or rollback to previous stack state
pulumi stack history
pulumi stack export --version <previous-version> | pulumi stack import
```

## Next Steps (Future Sprints)

- Phase 3 Sprint 4: Meeting Prep Agent Integration (chat session handling)
- Phase 3 Sprint 5: Post-meeting action item extraction
- Phase 4: Step Functions orchestration for complex workflows

## Cost Estimates

**Monthly costs (approximate)**:
- Lambda invocations: ~$0.20 (assuming 100 meetings/month)
- EventBridge events: $0.00 (first 1M events free)
- DynamoDB read/writes: ~$0.50 (light usage)
- CloudWatch Logs: ~$0.50 (7-day retention)
- SES emails: ~$0.10 (if using email fallback)
- Twilio SMS: ~$0.75/message (if using SMS fallback)

**Total**: ~$1.30-2.00/month (excluding SMS)

## Support and Documentation

- **Pulumi Infrastructure**: `/workspaces/exec_assistant/infrastructure/prep_notification.py`
- **Handler Code**: `/workspaces/exec_assistant/src/exec_assistant/workflows/prep_trigger_handler.py`
- **Slack Bot Code**: `/workspaces/exec_assistant/src/exec_assistant/interfaces/slack_bot.py`
- **Notification Service**: `/workspaces/exec_assistant/src/exec_assistant/shared/notification_service.py`
- **Testing Guide**: `/workspaces/exec_assistant/docs/TESTING.md`
