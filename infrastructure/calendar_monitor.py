"""Calendar monitoring infrastructure for Phase 3 Sprint 2.

Defines:
- Calendar monitor Lambda function
- EventBridge scheduled rule (every 2 hours)
- Lambda permissions for EventBridge invocation
- CloudWatch log groups
"""

import json
import shutil
import subprocess
from pathlib import Path

import pulumi
import pulumi_aws as aws


def create_calendar_monitor_lambda(
    environment: str,
    role: aws.iam.Role,
    users_table: aws.dynamodb.Table,
    meetings_table: aws.dynamodb.Table,
    config: pulumi.Config,
) -> aws.lambda_.Function:
    """Create Lambda function for calendar monitoring.

    This Lambda is triggered every 2 hours by EventBridge to:
    1. Find all users with calendar_connected=true
    2. Fetch their upcoming calendar meetings (next 14 days)
    3. Classify each meeting using MeetingClassifier
    4. Sync meetings to DynamoDB (create/update)
    5. Check if meetings need prep triggered
    6. Emit EventBridge events for meetings requiring prep

    Args:
        environment: Environment name
        role: Lambda IAM role
        users_table: Users DynamoDB table
        meetings_table: Meetings DynamoDB table
        config: Pulumi configuration

    Returns:
        Lambda function resource
    """
    # Create CloudWatch log group
    log_group = aws.cloudwatch.LogGroup(
        f"exec-assistant-calendar-monitor-logs-{environment}",
        name=f"/aws/lambda/exec-assistant-calendar-monitor-{environment}",
        retention_in_days=7 if environment == "dev" else 30,
        tags={
            "Environment": environment,
            "Project": "exec-assistant",
            "ManagedBy": "pulumi",
        },
    )

    # Get config values
    google_calendar_client_id = config.require_secret("google_calendar_client_id")
    google_calendar_client_secret = config.require_secret("google_calendar_client_secret")

    # Get redirect URI from config (calendar monitor doesn't need dynamic API endpoint)
    google_calendar_redirect_uri = config.get("google_calendar_redirect_uri") or "https://placeholder.com/calendar/callback"

    # Build Lambda deployment package with dependencies
    # Create deployment package
    package_dir = Path(__file__).parent / ".lambda_build_calendar_monitor"
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
        "google-auth",
        "google-auth-oauthlib",
        "google-auth-httplib2",
        "google-api-python-client",
        "boto3",
        "botocore",
    ]

    print(f"Installing calendar monitor Lambda dependencies to {package_dir}...")
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
        "USERS_TABLE_NAME": users_table.name,
        "MEETINGS_TABLE_NAME": meetings_table.name,
        "GOOGLE_CALENDAR_CLIENT_ID": google_calendar_client_id,
        "GOOGLE_CALENDAR_CLIENT_SECRET": google_calendar_client_secret,
        "GOOGLE_CALENDAR_REDIRECT_URI": google_calendar_redirect_uri,
        "AWS_REGION": config.get("aws:region") or "us-east-1",
        "EVENT_BUS_NAME": "default",
        "CALENDAR_LOOKAHEAD_DAYS": config.get("calendar_lookahead_days") or "14",
    }

    # Create Lambda function
    calendar_monitor_lambda = aws.lambda_.Function(
        f"exec-assistant-calendar-monitor-{environment}",
        name=f"exec-assistant-calendar-monitor-{environment}",
        role=role.arn,
        runtime="python3.13",
        handler="exec_assistant.workflows.calendar_monitor.lambda_handler",
        code=lambda_code,
        timeout=300,  # 5 minutes to process multiple users
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

    return calendar_monitor_lambda


def create_calendar_monitor_eventbridge_rule(
    environment: str,
    calendar_monitor_lambda: aws.lambda_.Function,
) -> aws.cloudwatch.EventRule:
    """Create EventBridge scheduled rule to trigger calendar monitor every 2 hours.

    Args:
        environment: Environment name
        calendar_monitor_lambda: Calendar monitor Lambda function

    Returns:
        EventBridge rule resource
    """
    # Create EventBridge rule with cron schedule (every 2 hours)
    rule = aws.cloudwatch.EventRule(
        f"exec-assistant-calendar-monitor-rule-{environment}",
        name=f"exec-assistant-calendar-monitor-{environment}",
        description="Trigger calendar monitor Lambda every 2 hours",
        schedule_expression="cron(0 */2 * * ? *)",  # Every 2 hours at minute 0
        state="ENABLED",
        tags={
            "Environment": environment,
            "Project": "exec-assistant",
            "ManagedBy": "pulumi",
        },
    )

    # Create EventBridge target pointing to Lambda
    target = aws.cloudwatch.EventTarget(
        f"exec-assistant-calendar-monitor-target-{environment}",
        rule=rule.name,
        arn=calendar_monitor_lambda.arn,
    )

    # Grant EventBridge permission to invoke Lambda
    aws.lambda_.Permission(
        f"exec-assistant-calendar-monitor-eventbridge-permission-{environment}",
        action="lambda:InvokeFunction",
        function=calendar_monitor_lambda.name,
        principal="events.amazonaws.com",
        source_arn=rule.arn,
    )

    return rule


def create_calendar_monitor_infrastructure(
    environment: str,
    role: aws.iam.Role,
    users_table: aws.dynamodb.Table,
    meetings_table: aws.dynamodb.Table,
    config: pulumi.Config,
) -> tuple[aws.lambda_.Function, aws.cloudwatch.EventRule]:
    """Create complete calendar monitor infrastructure.

    This is the main entry point for calendar monitoring infrastructure.

    Args:
        environment: Environment name
        role: Lambda IAM role (with required permissions)
        users_table: Users DynamoDB table
        meetings_table: Meetings DynamoDB table
        config: Pulumi configuration

    Returns:
        Tuple of (Lambda function, EventBridge rule)
    """
    # Create calendar monitor Lambda
    calendar_monitor_lambda = create_calendar_monitor_lambda(
        environment, role, users_table, meetings_table, config
    )

    # Create EventBridge rule to trigger Lambda every 2 hours
    eventbridge_rule = create_calendar_monitor_eventbridge_rule(
        environment, calendar_monitor_lambda
    )

    return calendar_monitor_lambda, eventbridge_rule
