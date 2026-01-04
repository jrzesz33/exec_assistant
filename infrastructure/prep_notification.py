"""Meeting prep notification infrastructure for Phase 3 Sprint 3.

Defines:
- Prep trigger handler Lambda function (responds to MeetingPrepRequired events)
- EventBridge rule to route MeetingPrepRequired events to handler
- Slack bot Lambda updates (adds DynamoDB and EventBridge permissions)
- IAM policies for multi-channel notifications (Slack, Twilio, SES)
- CloudWatch log groups
"""

import json
import shutil
import subprocess
from pathlib import Path

import pulumi
import pulumi_aws as aws


def create_prep_trigger_lambda(
    environment: str,
    role: aws.iam.Role,
    users_table: aws.dynamodb.Table,
    meetings_table: aws.dynamodb.Table,
    config: pulumi.Config,
) -> aws.lambda_.Function:
    """Create Lambda function for prep trigger handling.

    This Lambda is triggered by EventBridge MeetingPrepRequired events from
    the calendar monitor. It:
    1. Fetches meeting and user from DynamoDB
    2. Updates meeting status to PREP_SCHEDULED
    3. Sends multi-channel notifications via NotificationService
    4. Tracks notification delivery status

    Args:
        environment: Environment name
        role: Lambda IAM role (with DynamoDB, SES, EventBridge permissions)
        users_table: Users DynamoDB table
        meetings_table: Meetings DynamoDB table
        config: Pulumi configuration

    Returns:
        Lambda function resource
    """
    # Create CloudWatch log group
    log_group = aws.cloudwatch.LogGroup(
        f"exec-assistant-prep-trigger-logs-{environment}",
        name=f"/aws/lambda/exec-assistant-prep-trigger-{environment}",
        retention_in_days=7 if environment == "dev" else 30,
        tags={
            "Environment": environment,
            "Project": "exec-assistant",
            "ManagedBy": "pulumi",
        },
    )

    # Get config values
    slack_bot_token = config.require_secret("slack_bot_token")

    # Optional: Twilio credentials (for SMS fallback)
    twilio_account_sid = config.get_secret("twilio_account_sid") or pulumi.Output.secret("")
    twilio_auth_token = config.get_secret("twilio_auth_token") or pulumi.Output.secret("")
    twilio_from_number = config.get_secret("twilio_from_number") or pulumi.Output.secret("")

    # Optional: SES from email (for email fallback)
    ses_from_email = config.get("ses_from_email") or ""

    # Build Lambda deployment package
    package_dir = Path(__file__).parent / ".lambda_build_prep_trigger"
    package_dir.mkdir(exist_ok=True)

    # Copy source code
    src_dir = Path(__file__).parent.parent / "src" / "exec_assistant"

    # Copy relevant modules (shared and workflows)
    for module in ["shared", "workflows"]:
        src_module = src_dir / module
        dest_module = package_dir / "exec_assistant" / module
        if dest_module.exists():
            shutil.rmtree(dest_module)
        if src_module.exists():
            shutil.copytree(src_module, dest_module)

    # Create __init__.py files
    (package_dir / "exec_assistant").mkdir(exist_ok=True)
    (package_dir / "exec_assistant" / "__init__.py").touch()

    # Install dependencies to package directory
    requirements = [
        "pydantic>=2.0",
        "requests",
        "boto3",
        "botocore",
    ]

    print(f"Installing prep trigger Lambda dependencies to {package_dir}...")
    subprocess.run(
        [
            "pip",
            "install",
            "--target",
            str(package_dir),
            "--upgrade",
            "--no-user",
        ]
        + requirements,
        check=True,
        capture_output=True,
    )

    # Use the package directory as Lambda code
    lambda_code = pulumi.AssetArchive(
        {
            ".": pulumi.FileArchive(str(package_dir)),
        }
    )

    # Build environment variables dict
    env_vars = {
        "MEETINGS_TABLE_NAME": meetings_table.name,
        "USERS_TABLE_NAME": users_table.name,
        "SLACK_BOT_TOKEN": slack_bot_token,
        "TWILIO_ACCOUNT_SID": twilio_account_sid,
        "TWILIO_AUTH_TOKEN": twilio_auth_token,
        "TWILIO_FROM_NUMBER": twilio_from_number,
        "SES_FROM_EMAIL": ses_from_email,
        "AWS_REGION": config.get("aws:region") or "us-east-1",
    }

    # Create Lambda function
    prep_trigger_lambda = aws.lambda_.Function(
        f"exec-assistant-prep-trigger-{environment}",
        name=f"exec-assistant-prep-trigger-{environment}",
        role=role.arn,
        runtime="python3.13",
        handler="exec_assistant.workflows.prep_trigger_handler.lambda_handler",
        code=lambda_code,
        timeout=60,
        memory_size=512,
        environment=aws.lambda_.FunctionEnvironmentArgs(
            variables=env_vars,
        ),
        tags={
            "Environment": environment,
            "Project": "exec-assistant",
            "ManagedBy": "pulumi",
        },
    )

    return prep_trigger_lambda


def create_prep_trigger_eventbridge_rule(
    environment: str,
    prep_trigger_lambda: aws.lambda_.Function,
) -> aws.cloudwatch.EventRule:
    """Create EventBridge rule to route MeetingPrepRequired events to prep trigger Lambda.

    This rule listens for events from the calendar monitor and routes them
    to the prep trigger handler.

    Args:
        environment: Environment name
        prep_trigger_lambda: Prep trigger Lambda function

    Returns:
        EventBridge rule resource
    """
    # Create EventBridge rule with event pattern
    rule = aws.cloudwatch.EventRule(
        f"exec-assistant-prep-trigger-rule-{environment}",
        name=f"exec-assistant-prep-trigger-{environment}",
        description="Route MeetingPrepRequired events to prep trigger handler",
        event_pattern=json.dumps(
            {
                "source": ["exec-assistant.calendar-monitor"],
                "detail-type": ["MeetingPrepRequired"],
            }
        ),
        state="ENABLED",
        tags={
            "Environment": environment,
            "Project": "exec-assistant",
            "ManagedBy": "pulumi",
        },
    )

    # Create EventBridge target pointing to Lambda
    target = aws.cloudwatch.EventTarget(
        f"exec-assistant-prep-trigger-target-{environment}",
        rule=rule.name,
        arn=prep_trigger_lambda.arn,
    )

    # Grant EventBridge permission to invoke Lambda
    aws.lambda_.Permission(
        f"exec-assistant-prep-trigger-eventbridge-permission-{environment}",
        action="lambda:InvokeFunction",
        function=prep_trigger_lambda.name,
        principal="events.amazonaws.com",
        source_arn=rule.arn,
    )

    return rule


def create_slack_bot_lambda(
    environment: str,
    role: aws.iam.Role,
    users_table: aws.dynamodb.Table,
    meetings_table: aws.dynamodb.Table,
    chat_sessions_table: aws.dynamodb.Table,
    config: pulumi.Config,
) -> aws.lambda_.Function:
    """Create Slack bot Lambda function for webhook handling.

    This Lambda handles:
    - Slack signature verification
    - Slash commands (/meetings)
    - Interactive messages (Start Prep, Remind Later buttons)
    - Event subscriptions (DMs)

    Args:
        environment: Environment name
        role: Lambda IAM role (with DynamoDB, EventBridge permissions)
        users_table: Users DynamoDB table
        meetings_table: Meetings DynamoDB table
        chat_sessions_table: Chat sessions DynamoDB table
        config: Pulumi configuration

    Returns:
        Lambda function resource
    """
    # Create CloudWatch log group
    log_group = aws.cloudwatch.LogGroup(
        f"exec-assistant-slack-bot-logs-{environment}",
        name=f"/aws/lambda/exec-assistant-slack-bot-{environment}",
        retention_in_days=7 if environment == "dev" else 30,
        tags={
            "Environment": environment,
            "Project": "exec-assistant",
            "ManagedBy": "pulumi",
        },
    )

    # Get config values
    slack_signing_secret = config.require_secret("slack_signing_secret")
    slack_bot_token = config.require_secret("slack_bot_token")

    # Build Lambda deployment package
    package_dir = Path(__file__).parent / ".lambda_build_slack_bot"
    package_dir.mkdir(exist_ok=True)

    # Copy source code
    src_dir = Path(__file__).parent.parent / "src" / "exec_assistant"

    # Copy relevant modules
    for module in ["shared", "interfaces"]:
        src_module = src_dir / module
        dest_module = package_dir / "exec_assistant" / module
        if dest_module.exists():
            shutil.rmtree(dest_module)
        if src_module.exists():
            shutil.copytree(src_module, dest_module)

    # Create __init__.py files
    (package_dir / "exec_assistant").mkdir(exist_ok=True)
    (package_dir / "exec_assistant" / "__init__.py").touch()

    # Install dependencies
    requirements = [
        "pydantic>=2.0",
        "requests",
        "boto3",
        "botocore",
    ]

    print(f"Installing Slack bot Lambda dependencies to {package_dir}...")
    subprocess.run(
        [
            "pip",
            "install",
            "--target",
            str(package_dir),
            "--upgrade",
            "--no-user",
        ]
        + requirements,
        check=True,
        capture_output=True,
    )

    # Use the package directory as Lambda code
    lambda_code = pulumi.AssetArchive(
        {
            ".": pulumi.FileArchive(str(package_dir)),
        }
    )

    # Build environment variables dict
    env_vars = {
        "SLACK_SIGNING_SECRET": slack_signing_secret,
        "SLACK_BOT_TOKEN": slack_bot_token,
        "USERS_TABLE_NAME": users_table.name,
        "MEETINGS_TABLE_NAME": meetings_table.name,
        "CHAT_SESSIONS_TABLE_NAME": chat_sessions_table.name,
        "EVENT_BUS_NAME": "default",
        "AWS_REGION": config.get("aws:region") or "us-east-1",
        "ENV": environment,
    }

    # Create Lambda function
    slack_bot_lambda = aws.lambda_.Function(
        f"exec-assistant-slack-bot-{environment}",
        name=f"exec-assistant-slack-bot-{environment}",
        role=role.arn,
        runtime="python3.13",
        handler="exec_assistant.interfaces.slack_bot.lambda_handler",
        code=lambda_code,
        timeout=30,
        memory_size=512,
        environment=aws.lambda_.FunctionEnvironmentArgs(
            variables=env_vars,
        ),
        tags={
            "Environment": environment,
            "Project": "exec-assistant",
            "ManagedBy": "pulumi",
        },
    )

    return slack_bot_lambda


def add_prep_notification_permissions(
    environment: str,
    role: aws.iam.Role,
    meetings_table: aws.dynamodb.Table,
    users_table: aws.dynamodb.Table,
    chat_sessions_table: aws.dynamodb.Table,
) -> None:
    """Add IAM permissions for prep notification workflow.

    This adds permissions for:
    - DynamoDB: GetItem, PutItem on meetings, users, chat_sessions tables
    - SES: SendEmail for email notifications
    - EventBridge: PutRule, PutTargets for "Remind Later" functionality

    Args:
        environment: Environment name
        role: Lambda IAM role to attach policy to
        meetings_table: Meetings DynamoDB table
        users_table: Users DynamoDB table
        chat_sessions_table: Chat sessions DynamoDB table
    """
    # Build resource list for Output.all()
    resources = [
        meetings_table.arn,
        users_table.arn,
        chat_sessions_table.arn,
    ]

    # Policy for prep notification workflow
    policy_document = pulumi.Output.all(*resources).apply(
        lambda args: json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "PrepNotificationDynamoDB",
                        "Effect": "Allow",
                        "Action": [
                            "dynamodb:GetItem",
                            "dynamodb:PutItem",
                            "dynamodb:UpdateItem",
                        ],
                        "Resource": [
                            args[0],  # meetings_table_arn
                            args[1],  # users_table_arn
                            args[2],  # chat_sessions_table_arn
                        ],
                    },
                    {
                        "Sid": "PrepNotificationSES",
                        "Effect": "Allow",
                        "Action": [
                            "ses:SendEmail",
                            "ses:SendRawEmail",
                        ],
                        "Resource": "*",  # SES email sending (no specific resource ARN)
                    },
                    {
                        "Sid": "PrepNotificationEventBridge",
                        "Effect": "Allow",
                        "Action": [
                            "events:PutRule",
                            "events:PutTargets",
                            "events:DeleteRule",
                            "events:RemoveTargets",
                        ],
                        "Resource": "arn:aws:events:*:*:rule/prep-reminder-*",
                    },
                ],
            }
        )
    )

    aws.iam.RolePolicy(
        f"exec-assistant-prep-notification-policy-{environment}",
        role=role.id,
        policy=policy_document,
    )


def create_slack_bot_api_integration(
    environment: str,
    api: aws.apigatewayv2.Api,
    slack_bot_lambda: aws.lambda_.Function,
) -> None:
    """Create API Gateway integration for Slack bot webhook.

    Args:
        environment: Environment name
        api: API Gateway HTTP API
        slack_bot_lambda: Slack bot Lambda function
    """
    # Create Lambda integration for Slack bot
    slack_bot_integration = aws.apigatewayv2.Integration(
        f"exec-assistant-slack-bot-integration-{environment}",
        api_id=api.id,
        integration_type="AWS_PROXY",
        integration_uri=slack_bot_lambda.arn,
        payload_format_version="2.0",
    )

    # Create route for Slack webhook
    aws.apigatewayv2.Route(
        f"exec-assistant-post-slack-webhook-{environment}",
        api_id=api.id,
        route_key="POST /slack/webhook",
        target=slack_bot_integration.id.apply(lambda id: f"integrations/{id}"),
    )

    # Grant API Gateway permission to invoke Slack bot Lambda
    aws.lambda_.Permission(
        f"exec-assistant-api-slack-bot-lambda-permission-{environment}",
        action="lambda:InvokeFunction",
        function=slack_bot_lambda.name,
        principal="apigateway.amazonaws.com",
        source_arn=api.execution_arn.apply(lambda arn: f"{arn}/*/*"),
    )


def create_prep_notification_infrastructure(
    environment: str,
    role: aws.iam.Role,
    users_table: aws.dynamodb.Table,
    meetings_table: aws.dynamodb.Table,
    chat_sessions_table: aws.dynamodb.Table,
    api: aws.apigatewayv2.Api,
    config: pulumi.Config,
) -> tuple[aws.lambda_.Function, aws.cloudwatch.EventRule, aws.lambda_.Function]:
    """Create complete prep notification infrastructure.

    This is the main entry point for Phase 3 Sprint 3 infrastructure.

    Components created:
    1. Prep trigger handler Lambda (responds to EventBridge events)
    2. EventBridge rule (routes MeetingPrepRequired events)
    3. Slack bot Lambda (handles interactive messages)
    4. API Gateway integration (Slack webhook endpoint)
    5. IAM permissions (DynamoDB, SES, EventBridge)

    Args:
        environment: Environment name
        role: Lambda IAM role (will be extended with new permissions)
        users_table: Users DynamoDB table
        meetings_table: Meetings DynamoDB table
        chat_sessions_table: Chat sessions DynamoDB table
        api: API Gateway HTTP API
        config: Pulumi configuration

    Returns:
        Tuple of (prep trigger Lambda, EventBridge rule, Slack bot Lambda)
    """
    # Add IAM permissions for prep notification workflow
    add_prep_notification_permissions(
        environment, role, meetings_table, users_table, chat_sessions_table
    )

    # Create prep trigger handler Lambda
    prep_trigger_lambda = create_prep_trigger_lambda(
        environment, role, users_table, meetings_table, config
    )

    # Create EventBridge rule to route MeetingPrepRequired events
    eventbridge_rule = create_prep_trigger_eventbridge_rule(environment, prep_trigger_lambda)

    # Create Slack bot Lambda
    slack_bot_lambda = create_slack_bot_lambda(
        environment, role, users_table, meetings_table, chat_sessions_table, config
    )

    # Create API Gateway integration for Slack webhook
    create_slack_bot_api_integration(environment, api, slack_bot_lambda)

    return prep_trigger_lambda, eventbridge_rule, slack_bot_lambda
