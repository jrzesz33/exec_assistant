# AWS Infrastructure Architecture

## Overview

This document describes the AWS infrastructure for the Executive Assistant system, including all services, networking, security, and deployment architecture.

## High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                      Internet/User Layer                          │
│  - Slack Platform                                                 │
│  - Google/Microsoft Calendar API                                  │
│  - User's devices                                                 │
└────────────────────────────┬─────────────────────────────────────┘
                             │ HTTPS
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                    AWS Edge Layer                                 │
│  ┌──────────────────┐        ┌──────────────────┐               │
│  │  API Gateway     │        │   CloudFront     │               │
│  │  (HTTP API)      │        │   (CDN)          │               │
│  └────────┬─────────┘        └────────┬─────────┘               │
└───────────┼──────────────────────────┼───────────────────────────┘
            │                          │
            ▼                          ▼
┌──────────────────────────────────────────────────────────────────┐
│                    Compute Layer (VPC)                            │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  Private Subnets (Multi-AZ)                                │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │  │
│  │  │   Lambda     │  │   Lambda     │  │   Lambda     │    │  │
│  │  │   Functions  │  │   Functions  │  │   Functions  │    │  │
│  │  │   (Agents)   │  │   (Slack)    │  │   (Utils)    │    │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘    │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
            │                          │
            ▼                          ▼
┌──────────────────────────────────────────────────────────────────┐
│                  Orchestration Layer                              │
│  ┌──────────────────┐        ┌──────────────────┐               │
│  │  Step Functions  │        │  EventBridge     │               │
│  │  (Workflows)     │        │  (Scheduling)    │               │
│  └──────────────────┘        └──────────────────┘               │
└──────────────────────────────────────────────────────────────────┘
            │                          │
            ▼                          ▼
┌──────────────────────────────────────────────────────────────────┐
│                      Data Layer                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │ DynamoDB │  │    S3    │  │ Secrets  │  │   KMS    │        │
│  │ (State)  │  │  (Docs)  │  │ Manager  │  │  (Keys)  │        │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │
└──────────────────────────────────────────────────────────────────┘
            │                          │
            ▼                          ▼
┌──────────────────────────────────────────────────────────────────┐
│                      AI Layer                                     │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │  Amazon Bedrock (Claude 3.5 Sonnet)                          ││
│  └──────────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────┘
            │
            ▼
┌──────────────────────────────────────────────────────────────────┐
│                  Monitoring Layer                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │CloudWatch│  │  X-Ray   │  │CloudTrail│  │   SNS    │        │
│  │(Logs/Mtx)│  │(Tracing) │  │ (Audit)  │  │ (Alerts) │        │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │
└──────────────────────────────────────────────────────────────────┘
```

## Network Architecture

### VPC Design

```
VPC: exec-assistant-vpc (10.0.0.0/16)

┌─────────────────────────────────────────────────────────────────┐
│  Availability Zone us-east-1a                                    │
│  ┌────────────────────────────┐  ┌─────────────────────────────┐│
│  │ Public Subnet              │  │ Private Subnet              ││
│  │ 10.0.1.0/24                │  │ 10.0.11.0/24                ││
│  │ - NAT Gateway              │  │ - Lambda Functions          ││
│  │                            │  │ - VPC Endpoints             ││
│  └────────────────────────────┘  └─────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  Availability Zone us-east-1b                                    │
│  ┌────────────────────────────┐  ┌─────────────────────────────┐│
│  │ Public Subnet              │  │ Private Subnet              ││
│  │ 10.0.2.0/24                │  │ 10.0.12.0/24                ││
│  │ - NAT Gateway              │  │ - Lambda Functions          ││
│  │                            │  │ - VPC Endpoints             ││
│  └────────────────────────────┘  └─────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘

Internet Gateway: Attached to VPC
NAT Gateways: One per AZ for HA
VPC Endpoints: For AWS services (no internet routing)
```

### VPC Endpoints

Private endpoints for AWS services (no data leaves AWS network):

```
- com.amazonaws.us-east-1.bedrock-runtime
- com.amazonaws.us-east-1.dynamodb
- com.amazonaws.us-east-1.s3
- com.amazonaws.us-east-1.secretsmanager
- com.amazonaws.us-east-1.kms
- com.amazonaws.us-east-1.logs
- com.amazonaws.us-east-1.sns
- com.amazonaws.us-east-1.sqs
- com.amazonaws.us-east-1.states (Step Functions)
```

### Security Groups

```python
# Lambda security group
lambda_sg = aws.ec2.SecurityGroup(
    "lambda-sg",
    vpc_id=vpc.id,
    description="Security group for Lambda functions",
    egress=[{
        "protocol": "-1",
        "from_port": 0,
        "to_port": 0,
        "cidr_blocks": ["0.0.0.0/0"]
    }]
)

# VPC endpoint security group
vpc_endpoint_sg = aws.ec2.SecurityGroup(
    "vpc-endpoint-sg",
    vpc_id=vpc.id,
    description="Security group for VPC endpoints",
    ingress=[{
        "protocol": "tcp",
        "from_port": 443,
        "to_port": 443,
        "security_groups": [lambda_sg.id]
    }]
)
```

## Compute Resources (Lambda)

### Lambda Functions

#### 1. CalendarMonitor
**Purpose**: Poll calendar API for upcoming meetings

```python
Function Name: exec-assistant-calendar-monitor
Runtime: python3.11
Memory: 512 MB
Timeout: 5 minutes
Trigger: EventBridge (cron: 0 */2 * * ? *)  # Every 2 hours
Environment Variables:
  - CALENDAR_API_TYPE
  - CALENDAR_API_ENDPOINT
  - MEETINGS_TABLE
  - CALENDAR_OAUTH_SECRET_ARN
VPC: Yes (private subnets)
Reserved Concurrency: 1 (prevent overlapping runs)
```

#### 2. MeetingClassifier
**Purpose**: Classify meeting type and load prep template

```python
Function Name: exec-assistant-meeting-classifier
Runtime: python3.11
Memory: 256 MB
Timeout: 30 seconds
Trigger: Step Functions
Environment Variables:
  - MEETING_TYPES_CONFIG_S3_KEY
VPC: Yes
```

#### 3. SlackWebhookHandler
**Purpose**: Handle all Slack webhook events

```python
Function Name: exec-assistant-slack-webhook
Runtime: python3.11
Memory: 512 MB
Timeout: 30 seconds
Trigger: API Gateway
Environment Variables:
  - SLACK_SIGNING_SECRET_ARN
  - SLACK_BOT_TOKEN_ARN
  - SESSIONS_TABLE
VPC: Yes
Reserved Concurrency: 10
```

#### 4. MeetingPrepAgent
**Purpose**: Run Meeting Coordinator agent to generate materials

```python
Function Name: exec-assistant-meeting-prep-agent
Runtime: python3.11
Memory: 3008 MB  # Max for more CPU
Timeout: 10 minutes
Trigger: Step Functions
Environment Variables:
  - BEDROCK_MODEL_ID
  - SESSIONS_S3_BUCKET
  - DOCUMENTS_S3_BUCKET
VPC: Yes
Ephemeral Storage: 1024 MB (for Strands SDK caching)
```

#### 5. ContextGatherer (Multiple)
**Purpose**: Query other agents for context

```python
# Separate Lambda for each agent for parallel invocation
Functions:
  - exec-assistant-budget-context
  - exec-assistant-big-rocks-context
  - exec-assistant-incidents-context
  - exec-assistant-staffing-context
  - exec-assistant-decisions-context

Runtime: python3.11
Memory: 256 MB
Timeout: 30 seconds
Trigger: Step Functions (parallel)
VPC: Yes
```

#### 6. PostMeetingProcessor
**Purpose**: Process meeting notes and extract action items

```python
Function Name: exec-assistant-post-meeting
Runtime: python3.11
Memory: 1024 MB
Timeout: 5 minutes
Trigger: S3 (notes upload) or Slack webhook
Environment Variables:
  - BEDROCK_MODEL_ID
  - MEETINGS_TABLE
VPC: Yes
```

### Lambda Layer (Shared Dependencies)

```python
Layer Name: exec-assistant-deps
Contents:
  - strands-sdk
  - boto3 (latest)
  - slack-sdk
  - google-auth + google-api-python-client (for Calendar)
  - requests

Size: ~50 MB
Compatible Runtimes: python3.11
```

## Orchestration

### Step Functions Workflows

#### MeetingPrepWorkflow (Standard)

```json
{
  "Comment": "Meeting preparation workflow",
  "StartAt": "ClassifyMeeting",
  "States": {
    "ClassifyMeeting": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:...:function:exec-assistant-meeting-classifier",
      "Next": "SendPrepNotification",
      "Retry": [
        {
          "ErrorEquals": ["States.TaskFailed"],
          "IntervalSeconds": 2,
          "MaxAttempts": 3,
          "BackoffRate": 2
        }
      ]
    },

    "SendPrepNotification": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:...:function:exec-assistant-slack-send-notification",
      "Next": "WaitForUserResponses",
      "ResultPath": "$.notification"
    },

    "WaitForUserResponses": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke.waitForTaskToken",
      "Parameters": {
        "FunctionName": "exec-assistant-chat-session-manager",
        "Payload": {
          "session_id.$": "$.session_id",
          "task_token.$": "$$.Task.Token"
        }
      },
      "TimeoutSeconds": 86400,
      "Next": "GatherContext",
      "Catch": [
        {
          "ErrorEquals": ["States.Timeout"],
          "Next": "HandleTimeout",
          "ResultPath": "$.error"
        }
      ]
    },

    "GatherContext": {
      "Type": "Parallel",
      "Branches": [
        {
          "StartAt": "GetBudgetContext",
          "States": {
            "GetBudgetContext": {
              "Type": "Task",
              "Resource": "arn:aws:lambda:...:function:exec-assistant-budget-context",
              "End": true
            }
          }
        },
        {
          "StartAt": "GetBigRocksContext",
          "States": {
            "GetBigRocksContext": {
              "Type": "Task",
              "Resource": "arn:aws:lambda:...:function:exec-assistant-big-rocks-context",
              "End": true
            }
          }
        },
        {
          "StartAt": "GetIncidentsContext",
          "States": {
            "GetIncidentsContext": {
              "Type": "Task",
              "Resource": "arn:aws:lambda:...:function:exec-assistant-incidents-context",
              "End": true
            }
          }
        },
        {
          "StartAt": "GetStaffingContext",
          "States": {
            "GetStaffingContext": {
              "Type": "Task",
              "Resource": "arn:aws:lambda:...:function:exec-assistant-staffing-context",
              "End": true
            }
          }
        },
        {
          "StartAt": "GetDecisionsContext",
          "States": {
            "GetDecisionsContext": {
              "Type": "Task",
              "Resource": "arn:aws:lambda:...:function:exec-assistant-decisions-context",
              "End": true
            }
          }
        }
      ],
      "ResultPath": "$.context",
      "Next": "GenerateMaterials"
    },

    "GenerateMaterials": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:...:function:exec-assistant-meeting-prep-agent",
      "Next": "SendPrepMaterials",
      "TimeoutSeconds": 600,
      "ResultPath": "$.materials"
    },

    "SendPrepMaterials": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:...:function:exec-assistant-slack-send-materials",
      "Next": "ScheduleFinalReminder",
      "ResultPath": "$.sent"
    },

    "ScheduleFinalReminder": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:...:function:exec-assistant-schedule-reminder",
      "End": true
    },

    "HandleTimeout": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:...:function:exec-assistant-handle-timeout",
      "Next": "GatherContext"
    }
  }
}
```

**Workflow Metrics:**
- Average duration: 5-15 minutes (depends on user response time)
- Cost per execution: ~$0.05 (Standard workflow + Lambda)
- Concurrency: Up to 100 parallel executions

### EventBridge Rules

#### Calendar Monitoring (Scheduled)

```python
calendar_monitor_rule = aws.cloudwatch.EventRule(
    "calendar-monitor-rule",
    description="Trigger calendar monitoring every 2 hours",
    schedule_expression="cron(0 */2 * * ? *)",  # Every 2 hours
    targets=[{
        "arn": calendar_monitor_lambda.arn,
        "input": json.dumps({
            "source": "scheduled",
            "time_range_days": 14
        })
    }]
)
```

#### Meeting Prep Trigger (Event Pattern)

```python
meeting_prep_rule = aws.cloudwatch.EventRule(
    "meeting-prep-trigger",
    description="Trigger meeting prep workflow",
    event_pattern=json.dumps({
        "source": ["exec-assistant"],
        "detail-type": ["MeetingPrepRequired"],
        "detail": {
            "meeting_id": [{"exists": True}]
        }
    }),
    targets=[{
        "arn": meeting_prep_workflow.state_machine_arn,
        "role_arn": eventbridge_role.arn,
        "input_path": "$.detail"
    }]
)
```

#### Final Reminder (Dynamic, One-time)

Created dynamically by ScheduleFinalReminder Lambda:

```python
def schedule_final_reminder(meeting_id: str, meeting_time: datetime) -> None:
    """Schedule one-time reminder 2 hours before meeting."""
    reminder_time = meeting_time - timedelta(hours=2)

    # Create one-time rule
    rule_name = f"reminder-{meeting_id}"

    events_client.put_rule(
        Name=rule_name,
        ScheduleExpression=f"at({reminder_time.strftime('%Y-%m-%dT%H:%M:%S')})",
        State="ENABLED",
        Description=f"Final reminder for meeting {meeting_id}"
    )

    # Add target
    events_client.put_targets(
        Rule=rule_name,
        Targets=[{
            "Arn": reminder_lambda_arn,
            "Input": json.dumps({"meeting_id": meeting_id})
        }]
    )
```

## Data Storage

### DynamoDB Tables

#### exec-assistant-meetings

```python
meetings_table = aws.dynamodb.Table(
    "exec-assistant-meetings",
    name="exec-assistant-meetings",
    billing_mode="PAY_PER_REQUEST",  # On-demand
    hash_key="meeting_id",
    range_key="calendar_id",
    attributes=[
        {"name": "meeting_id", "type": "S"},
        {"name": "calendar_id", "type": "S"},
        {"name": "status", "type": "S"},
        {"name": "start_time", "type": "S"}
    ],
    global_secondary_indexes=[{
        "name": "status-start_time-index",
        "hash_key": "status",
        "range_key": "start_time",
        "projection_type": "ALL"
    }],
    point_in_time_recovery={"enabled": True},
    server_side_encryption={"enabled": True},
    tags={"Environment": "production", "Service": "exec-assistant"}
)
```

**Capacity Planning:**
- Estimated reads: 100-500/day
- Estimated writes: 50-200/day
- On-demand pricing: ~$5-10/month

#### exec-assistant-chat-sessions

```python
sessions_table = aws.dynamodb.Table(
    "exec-assistant-chat-sessions",
    name="exec-assistant-chat-sessions",
    billing_mode="PAY_PER_REQUEST",
    hash_key="session_id",
    attributes=[
        {"name": "session_id", "type": "S"},
        {"name": "user_id", "type": "S"},
        {"name": "created_at", "type": "N"}
    ],
    global_secondary_indexes=[{
        "name": "user_id-created_at-index",
        "hash_key": "user_id",
        "range_key": "created_at",
        "projection_type": "ALL"
    }],
    ttl={"enabled": True, "attribute_name": "expires_at"},
    point_in_time_recovery={"enabled": True},
    server_side_encryption={"enabled": True}
)
```

**TTL Configuration:**
- Sessions auto-deleted 7 days after expiration
- Reduces storage costs
- Compliance with data retention policies

### S3 Buckets

#### exec-assistant-documents

```python
documents_bucket = aws.s3.Bucket(
    "exec-assistant-documents",
    bucket="exec-assistant-documents-{account_id}",
    versioning={"enabled": True},
    server_side_encryption_configuration={
        "rule": {
            "apply_server_side_encryption_by_default": {
                "sse_algorithm": "aws:kms",
                "kms_master_key_id": kms_key.arn
            }
        }
    },
    lifecycle_rules=[
        {
            "id": "archive-old-meetings",
            "enabled": True,
            "transitions": [{
                "days": 90,
                "storage_class": "GLACIER"
            }],
            "noncurrent_version_transitions": [{
                "days": 30,
                "storage_class": "GLACIER"
            }]
        },
        {
            "id": "delete-temp-files",
            "enabled": True,
            "expiration": {"days": 7},
            "prefix": "temp/"
        }
    ],
    public_access_block_configuration={
        "block_public_acls": True,
        "block_public_policy": True,
        "ignore_public_acls": True,
        "restrict_public_buckets": True
    }
)
```

**Bucket Structure:**
```
s3://exec-assistant-documents-{account}/
├── meetings/
│   └── {meeting_id}/
│       ├── agenda.json
│       ├── questions.json
│       ├── context.json
│       ├── notes_template.md
│       └── notes.md
├── sessions/
│   └── {session_id}.json
├── agents/
│   └── {agent_name}/
│       └── sessions/
│           └── {session_id}.json
├── config/
│   ├── meeting_types.yaml
│   └── notification_rules.yaml
└── temp/
    └── {temp_files}.json  # Auto-deleted after 7 days
```

#### exec-assistant-sessions

```python
sessions_bucket = aws.s3.Bucket(
    "exec-assistant-sessions",
    bucket="exec-assistant-sessions-{account_id}",
    versioning={"enabled": False},  # Don't need versions for sessions
    server_side_encryption_configuration={...},
    lifecycle_rules=[{
        "id": "delete-old-sessions",
        "enabled": True,
        "expiration": {"days": 30}  # Delete after 30 days
    }]
)
```

**Purpose:** Strands SDK session storage for agent conversations

## AI/ML Services

### Amazon Bedrock

#### Model Configuration

```python
# No Pulumi resource needed - Bedrock is serverless
# Enable model access in Bedrock console or via AWS CLI

# Runtime configuration (in Lambda)
BEDROCK_MODEL_ID = "anthropic.claude-3-5-sonnet-20241022-v2:0"
BEDROCK_REGION = "us-east-1"
```

#### IAM Policy for Bedrock Access

```python
bedrock_policy = aws.iam.Policy(
    "bedrock-invoke-policy",
    policy=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream"
            ],
            "Resource": [
                f"arn:aws:bedrock:{region}::foundation-model/{BEDROCK_MODEL_ID}"
            ]
        }]
    })
)
```

#### Cost Estimates

**Claude 3.5 Sonnet Pricing (On-Demand):**
- Input: $3.00 / 1M tokens
- Output: $15.00 / 1M tokens

**Estimated Usage:**
- Meeting prep: ~10K input + 5K output tokens = $0.11/meeting
- Context gathering: ~5K input + 2K output = $0.05/query
- Post-meeting processing: ~8K input + 3K output = $0.07/meeting

**Monthly Estimate (100 meetings):**
- Prep: $11
- Context: $50 (10 queries per day)
- Post-processing: $7
- **Total: ~$70/month**

## Security

### IAM Roles

#### Lambda Execution Role

```python
lambda_role = aws.iam.Role(
    "lambda-execution-role",
    assume_role_policy=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": "sts:AssumeRole"
        }]
    })
)

# Attach policies
aws.iam.RolePolicyAttachment(
    "lambda-vpc-execution",
    role=lambda_role.name,
    policy_arn="arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
)

aws.iam.RolePolicyAttachment(
    "lambda-bedrock-access",
    role=lambda_role.name,
    policy_arn=bedrock_policy.arn
)

# Custom policy for DynamoDB, S3, Secrets Manager, etc.
custom_policy = aws.iam.RolePolicy(
    "lambda-custom-policy",
    role=lambda_role.name,
    policy=json.dumps({
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:Query",
                    "dynamodb:Scan"
                ],
                "Resource": [
                    meetings_table.arn,
                    sessions_table.arn,
                    f"{meetings_table.arn}/index/*",
                    f"{sessions_table.arn}/index/*"
                ]
            },
            {
                "Effect": "Allow",
                "Action": [
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:DeleteObject"
                ],
                "Resource": [
                    f"{documents_bucket.arn}/*",
                    f"{sessions_bucket.arn}/*"
                ]
            },
            {
                "Effect": "Allow",
                "Action": [
                    "secretsmanager:GetSecretValue"
                ],
                "Resource": [
                    slack_secret.arn,
                    calendar_secret.arn
                ]
            },
            {
                "Effect": "Allow",
                "Action": [
                    "kms:Decrypt",
                    "kms:DescribeKey"
                ],
                "Resource": [kms_key.arn]
            },
            {
                "Effect": "Allow",
                "Action": [
                    "states:SendTaskSuccess",
                    "states:SendTaskFailure"
                ],
                "Resource": ["*"]  # Step Functions task tokens
            }
        ]
    })
)
```

#### Step Functions Execution Role

```python
sfn_role = aws.iam.Role(
    "sfn-execution-role",
    assume_role_policy=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "states.amazonaws.com"},
            "Action": "sts:AssumeRole"
        }]
    })
)

aws.iam.RolePolicy(
    "sfn-invoke-lambda-policy",
    role=sfn_role.name,
    policy=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": [
                "lambda:InvokeFunction"
            ],
            "Resource": ["arn:aws:lambda:*:*:function:exec-assistant-*"]
        }]
    })
)
```

### KMS Encryption

```python
kms_key = aws.kms.Key(
    "exec-assistant-kms-key",
    description="Encryption key for Executive Assistant data",
    deletion_window_in_days=30,
    enable_key_rotation=True,
    policy=json.dumps({
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "Enable IAM User Permissions",
                "Effect": "Allow",
                "Principal": {"AWS": f"arn:aws:iam::{account_id}:root"},
                "Action": "kms:*",
                "Resource": "*"
            },
            {
                "Sid": "Allow Lambda to decrypt",
                "Effect": "Allow",
                "Principal": {"AWS": lambda_role.arn},
                "Action": [
                    "kms:Decrypt",
                    "kms:DescribeKey"
                ],
                "Resource": "*"
            }
        ]
    })
)

kms_alias = aws.kms.Alias(
    "exec-assistant-kms-alias",
    name="alias/exec-assistant",
    target_key_id=kms_key.id
)
```

### Secrets Manager

```python
slack_secret = aws.secretsmanager.Secret(
    "slack-credentials",
    name="exec-assistant/slack",
    description="Slack bot credentials",
    kms_key_id=kms_key.id
)

aws.secretsmanager.SecretVersion(
    "slack-credentials-version",
    secret_id=slack_secret.id,
    secret_string=json.dumps({
        "bot_token": "xoxb-...",
        "app_token": "xapp-...",
        "signing_secret": "...",
        "user_id": "U12345"
    })
)

calendar_secret = aws.secretsmanager.Secret(
    "calendar-credentials",
    name="exec-assistant/calendar",
    description="Calendar API credentials",
    kms_key_id=kms_key.id
)
```

## Monitoring & Observability

### CloudWatch Dashboards

```python
dashboard = aws.cloudwatch.Dashboard(
    "exec-assistant-dashboard",
    dashboard_name="ExecutiveAssistant",
    dashboard_body=json.dumps({
        "widgets": [
            {
                "type": "metric",
                "properties": {
                    "title": "Meeting Prep Success Rate",
                    "metrics": [
                        ["AWS/StepFunctions", "ExecutionsSucceeded",
                         {"stat": "Sum", "label": "Succeeded"}],
                        [".", "ExecutionsFailed",
                         {"stat": "Sum", "label": "Failed"}]
                    ],
                    "period": 300,
                    "stat": "Sum",
                    "region": "us-east-1",
                    "yAxis": {"left": {"min": 0}}
                }
            },
            {
                "type": "metric",
                "properties": {
                    "title": "Lambda Invocations",
                    "metrics": [
                        ["AWS/Lambda", "Invocations",
                         {"stat": "Sum"}]
                    ],
                    "period": 300
                }
            },
            {
                "type": "metric",
                "properties": {
                    "title": "Bedrock Token Usage",
                    "metrics": [
                        ["AWS/Bedrock", "InputTokens", {"stat": "Sum"}],
                        [".", "OutputTokens", {"stat": "Sum"}]
                    ],
                    "period": 3600
                }
            }
        ]
    })
)
```

### CloudWatch Alarms

```python
# High error rate alarm
error_alarm = aws.cloudwatch.MetricAlarm(
    "meeting-prep-error-alarm",
    alarm_name="exec-assistant-meeting-prep-errors",
    comparison_operator="GreaterThanThreshold",
    evaluation_periods=2,
    metric_name="ExecutionsFailed",
    namespace="AWS/StepFunctions",
    period=300,
    statistic="Sum",
    threshold=5,
    alarm_description="Alert when meeting prep workflow fails >5 times in 10 min",
    alarm_actions=[sns_topic.arn]
)

# Lambda duration alarm
duration_alarm = aws.cloudwatch.MetricAlarm(
    "lambda-duration-alarm",
    alarm_name="exec-assistant-lambda-duration",
    comparison_operator="GreaterThanThreshold",
    evaluation_periods=3,
    metric_name="Duration",
    namespace="AWS/Lambda",
    period=60,
    statistic="Average",
    threshold=10000,  # 10 seconds
    alarm_description="Alert when Lambda avg duration >10s",
    alarm_actions=[sns_topic.arn]
)
```

### X-Ray Tracing

```python
# Enable X-Ray tracing for all Lambda functions
calendar_monitor_lambda = aws.lambda_.Function(
    "calendar-monitor",
    # ... other config ...
    tracing_config={"mode": "Active"}
)

# X-Ray sampling rule
xray_sampling_rule = aws.xray.SamplingRule(
    "exec-assistant-sampling",
    rule_name="exec-assistant-sampling",
    priority=1000,
    version=1,
    reservoir_size=1,
    fixed_rate=0.1,  # Sample 10% of requests
    url_path="*",
    host="*",
    http_method="*",
    service_type="*",
    service_name="exec-assistant-*",
    resource_arn="*"
)
```

## Cost Optimization

### Estimated Monthly Costs

```
Service                    | Usage                  | Cost
---------------------------|------------------------|----------
Lambda                     | 50K invocations        | $2
  - Compute time           | 100 GB-seconds         | $2
DynamoDB (On-Demand)       | 10K reads, 5K writes   | $5
S3 Standard                | 10 GB storage          | $0.25
  - Requests               | 50K requests           | $0.02
Step Functions (Standard)  | 100 executions         | $2.50
EventBridge                | 10K events             | $0.01
Bedrock (Claude 3.5)       | 500K input tokens      | $70
                           | 250K output tokens     |
KMS                        | 10K requests           | $0.03
Secrets Manager            | 3 secrets              | $1.20
VPC                        | 2 NAT Gateways         | $90
Data Transfer              | 10 GB out              | $0.90
CloudWatch Logs            | 5 GB ingestion         | $2.50
---------------------------|------------------------|----------
TOTAL                                               | ~$176/month
```

### Optimization Strategies

1. **NAT Gateway Alternatives**:
   - Use VPC endpoints for all AWS services (reduce NAT traffic)
   - Consider NAT instances for lower cost (single AZ acceptable for dev)

2. **Lambda**:
   - Use ARM architecture (Graviton2) for 20% cost reduction
   - Right-size memory allocations (profile and adjust)
   - Use reserved concurrency only where needed

3. **DynamoDB**:
   - Monitor usage patterns, switch to provisioned capacity if predictable
   - Enable DAX caching for frequently accessed data (if needed)

4. **S3**:
   - Use Intelligent-Tiering for documents
   - Compress meeting materials before storage

5. **Bedrock**:
   - Cache common responses (agenda templates, question sets)
   - Use Claude 3 Haiku for simple context gathering ($0.25/$1.25 per 1M tokens)
   - Implement prompt caching (reduce input token costs)

## Disaster Recovery

### Backup Strategy

**DynamoDB:**
- Point-in-time recovery enabled (restore to any point in last 35 days)
- On-demand backups before major changes
- Export to S3 monthly for long-term retention

**S3:**
- Versioning enabled on documents bucket
- Cross-region replication to us-west-2 (optional, for critical data)
- Lifecycle policies to Glacier for cost optimization

**Secrets Manager:**
- Automatic rotation enabled (90 days)
- Replication to us-west-2

### Recovery Procedures

**RTO (Recovery Time Objective): 2 hours**
**RPO (Recovery Point Objective): 5 minutes**

**Failure Scenarios:**

1. **Lambda function failure**: Auto-retry via Step Functions, DLQ for analysis
2. **DynamoDB table corruption**: Restore from point-in-time recovery
3. **S3 data loss**: Restore from versioning or cross-region replica
4. **Regional outage**: Deploy to us-west-2 using Pulumi (pre-built stack)

## Deployment

### Pulumi Stacks

```
Development:   exec-assistant-dev   (us-east-1)
Staging:       exec-assistant-stage (us-east-1)
Production:    exec-assistant-prod  (us-east-1)
DR:            exec-assistant-dr    (us-west-2)
```

### Deployment Pipeline

```
1. Code changes committed to GitHub
2. GitHub Actions runs tests
3. Build Lambda deployment packages
4. Pulumi preview (show changes)
5. Manual approval (for prod)
6. Pulumi up (deploy changes)
7. Smoke tests
8. Rollback if tests fail
```

### Blue/Green Deployment

For Lambda functions:
- Use Lambda aliases ($LATEST, $BLUE, $GREEN)
- Shift traffic gradually (10% → 50% → 100%)
- Monitor error rates during shift
- Automatic rollback on error spike

## Compliance & Audit

### CloudTrail Logging

```python
cloudtrail = aws.cloudtrail.Trail(
    "exec-assistant-audit-trail",
    name="exec-assistant-audit",
    s3_bucket_name=audit_bucket.id,
    include_global_service_events=True,
    is_multi_region_trail=True,
    enable_log_file_validation=True,
    event_selectors=[{
        "read_write_type": "All",
        "include_management_events": True,
        "data_resources": [
            {
                "type": "AWS::DynamoDB::Table",
                "values": [
                    f"{meetings_table.arn}/",
                    f"{sessions_table.arn}/"
                ]
            },
            {
                "type": "AWS::S3::Object",
                "values": [
                    f"{documents_bucket.arn}/meetings/",
                    f"{sessions_bucket.arn}/"
                ]
            }
        ]
    }]
)
```

### HIPAA Compliance

- All data encrypted at rest (KMS) and in transit (TLS)
- Access logging enabled for all S3 buckets
- CloudTrail audit logging for all API calls
- No PHI in Lambda environment variables or logs
- BAA (Business Associate Agreement) with AWS
- Regular security audits and penetration testing
