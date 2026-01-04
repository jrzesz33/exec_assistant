"""Main Pulumi program for Executive Assistant infrastructure.

Deploys all AWS resources for the Executive Assistant system:
- Phase 1: KMS keys, DynamoDB tables, S3 buckets (storage foundation)
- Phase 1.5: Lambda functions, API Gateway, authentication, chat UI
- Future phases: Step Functions, EventBridge, full agent deployment
"""

import pulumi

from storage import create_dynamodb_tables, create_kms_key, create_s3_buckets

# Phase 1.5+ imports (optional - only if enabled in config)
try:
    from api import (
        create_agent_lambda,
        create_lambda_policy,
        create_lambda_role,
        create_ui_bucket,
    )

    PHASE_1_5_AVAILABLE = True
except ImportError:
    PHASE_1_5_AVAILABLE = False

# Get configuration
config = pulumi.Config()
environment = config.get("environment") or "dev"

# Export environment
pulumi.export("environment", environment)

# Create KMS key for encryption
kms_key = create_kms_key(environment)
pulumi.export("kms_key_id", kms_key.id)
pulumi.export("kms_key_arn", kms_key.arn)

# Create DynamoDB tables
tables = create_dynamodb_tables(environment, kms_key)

# Export table names and ARNs
pulumi.export("meetings_table_name", tables["meetings"].name)
pulumi.export("meetings_table_arn", tables["meetings"].arn)

pulumi.export("chat_sessions_table_name", tables["chat_sessions"].name)
pulumi.export("chat_sessions_table_arn", tables["chat_sessions"].arn)

pulumi.export("action_items_table_name", tables["action_items"].name)
pulumi.export("action_items_table_arn", tables["action_items"].arn)

pulumi.export("users_table_name", tables["users"].name)
pulumi.export("users_table_arn", tables["users"].arn)

# Create S3 buckets
buckets = create_s3_buckets(environment, kms_key)

# Export bucket names and ARNs
pulumi.export("documents_bucket_name", buckets["documents"].bucket)
pulumi.export("documents_bucket_arn", buckets["documents"].arn)

pulumi.export("sessions_bucket_name", buckets["sessions"].bucket)
pulumi.export("sessions_bucket_arn", buckets["sessions"].arn)

# Phase 1.5: Authentication and Chat UI (optional - enable via config)
enable_phase_1_5 = config.get_bool("enable_phase_1_5") or False

if enable_phase_1_5 and PHASE_1_5_AVAILABLE:
    pulumi.log.info("Deploying Phase 1.5: Authentication and Chat UI")

    # Create Lambda IAM role
    lambda_role = create_lambda_role(environment)
    pulumi.export("lambda_role_arn", lambda_role.arn)

    # Check if Phase 2 is enabled to determine Lambda policy permissions
    enable_phase_2 = config.get_bool("enable_phase_2") or False

    # Create Lambda policy for DynamoDB and KMS access (+ S3 and Bedrock if Phase 2)
    create_lambda_policy(
        environment,
        lambda_role,
        tables,
        kms_key,
        sessions_bucket=buckets["sessions"] if enable_phase_2 else None,
    )

    # Phase 2: Agent Lambda (optional)
    agent_lambda = None
    if enable_phase_2:
        pulumi.log.info("Deploying Phase 2: Meeting Coordinator Agent with AWS Nova")

        # Create agent Lambda
        agent_lambda = create_agent_lambda(
            environment,
            lambda_role,
            tables["chat_sessions"],
            buckets["sessions"],
            config,
        )
        pulumi.export("agent_lambda_arn", agent_lambda.arn)
        pulumi.export("agent_lambda_name", agent_lambda.name)

        pulumi.log.info("Phase 2: Agent Lambda created")

    # Create authentication Lambda and API Gateway together
    # This ensures the auth Lambda gets the correct OAuth redirect URI
    from api import create_auth_and_api_gateway

    auth_lambda, calendar_lambda, api, api_endpoint = create_auth_and_api_gateway(
        environment, lambda_role, tables["users"], config, agent_lambda
    )

    pulumi.export("auth_lambda_arn", auth_lambda.arn)
    pulumi.export("auth_lambda_name", auth_lambda.name)
    pulumi.export("calendar_lambda_arn", calendar_lambda.arn)
    pulumi.export("calendar_lambda_name", calendar_lambda.name)
    pulumi.export("api_id", api.id)
    pulumi.export("api_endpoint", api_endpoint)

    # Export the OAuth redirect URIs for reference
    oauth_redirect_uri = api_endpoint.apply(lambda endpoint: f"{endpoint}/auth/callback")
    pulumi.export("oauth_redirect_uri", oauth_redirect_uri)

    calendar_redirect_uri = api_endpoint.apply(lambda endpoint: f"{endpoint}/calendar/callback")
    pulumi.export("calendar_redirect_uri", calendar_redirect_uri)

    # Create UI bucket for static website hosting
    ui_bucket, ui_website_url = create_ui_bucket(environment)
    pulumi.export("ui_bucket_name", ui_bucket.bucket)
    pulumi.export("ui_website_url", ui_website_url)

    # Upload UI files to S3
    import pulumi_aws as aws
    from pathlib import Path

    ui_dir = Path(__file__).parent.parent / "ui"

    # Upload index.html
    aws.s3.BucketObjectv2(
        f"ui-index-{environment}",
        bucket=ui_bucket.id,
        key="index.html",
        source=pulumi.FileAsset(str(ui_dir / "index.html")),
        content_type="text/html",
    )

    # Upload app.js with API endpoint injected
    app_js_template = (ui_dir / "app.js").read_text()

    # Use .apply() to handle Pulumi Output
    app_js_content = api_endpoint.apply(
        lambda endpoint: app_js_template.replace("API_ENDPOINT_PLACEHOLDER", endpoint)
    )

    aws.s3.BucketObjectv2(
        f"ui-app-js-{environment}",
        bucket=ui_bucket.id,
        key="app.js",
        content=app_js_content,
        content_type="application/javascript",
    )

    # Upload error.html
    aws.s3.BucketObjectv2(
        f"ui-error-{environment}",
        bucket=ui_bucket.id,
        key="error.html",
        source=pulumi.FileAsset(str(ui_dir / "error.html")),
        content_type="text/html",
    )

    # Log deployment completion
    if enable_phase_2:
        pulumi.log.info("Phase 2 deployment complete! Agent chat endpoint ready at /chat/send")
    else:
        pulumi.log.info("Phase 1.5 deployment complete! Check stack outputs for URLs.")
        pulumi.log.info("To enable agent chat, set enable_phase_2=true in config.")

elif enable_phase_1_5 and not PHASE_1_5_AVAILABLE:
    pulumi.log.warn("Phase 1.5 enabled but api.py module not found. Skipping Phase 1.5 deployment.")

else:
    pulumi.log.info("Phase 1.5 disabled. Set enable_phase_1_5=true in config to deploy authentication and UI.")

# Phase 3 Sprint 2: Calendar Monitor (optional - enable via config)
enable_calendar_monitor = config.get_bool("enable_calendar_monitor") or False

if enable_calendar_monitor and enable_phase_1_5 and PHASE_1_5_AVAILABLE:
    pulumi.log.info("Deploying Phase 3 Sprint 2: Calendar Monitor Infrastructure")

    from calendar_monitor import create_calendar_monitor_infrastructure

    # Create calendar monitor Lambda and EventBridge rule
    calendar_monitor_lambda, calendar_monitor_rule = create_calendar_monitor_infrastructure(
        environment, lambda_role, tables["users"], tables["meetings"], config
    )

    pulumi.export("calendar_monitor_lambda_arn", calendar_monitor_lambda.arn)
    pulumi.export("calendar_monitor_lambda_name", calendar_monitor_lambda.name)
    pulumi.export("calendar_monitor_rule_arn", calendar_monitor_rule.arn)

    pulumi.log.info("Phase 3 Sprint 2: Calendar monitor deployed - runs every 2 hours")
elif enable_calendar_monitor and not (enable_phase_1_5 and PHASE_1_5_AVAILABLE):
    pulumi.log.warn("Calendar monitor enabled but requires Phase 1.5. Enable phase_1_5=true first.")
else:
    pulumi.log.info("Calendar monitor disabled. Set enable_calendar_monitor=true to deploy.")

# Phase 3 Sprint 3: Prep Notification Workflow (optional - enable via config)
enable_prep_notification = config.get_bool("enable_prep_notification") or False

if enable_prep_notification and enable_calendar_monitor and enable_phase_1_5 and PHASE_1_5_AVAILABLE:
    pulumi.log.info("Deploying Phase 3 Sprint 3: Prep Notification Workflow")

    from prep_notification import create_prep_notification_infrastructure

    # Create prep trigger handler, EventBridge rule, and Slack bot
    prep_trigger_lambda, prep_trigger_rule, slack_bot_lambda = create_prep_notification_infrastructure(
        environment,
        lambda_role,
        tables["users"],
        tables["meetings"],
        tables["chat_sessions"],
        api,
        config,
    )

    pulumi.export("prep_trigger_lambda_arn", prep_trigger_lambda.arn)
    pulumi.export("prep_trigger_lambda_name", prep_trigger_lambda.name)
    pulumi.export("prep_trigger_rule_arn", prep_trigger_rule.arn)
    pulumi.export("slack_bot_lambda_arn", slack_bot_lambda.arn)
    pulumi.export("slack_bot_lambda_name", slack_bot_lambda.name)

    # Export Slack webhook URL for configuration
    slack_webhook_url = api_endpoint.apply(lambda endpoint: f"{endpoint}/slack/webhook")
    pulumi.export("slack_webhook_url", slack_webhook_url)

    pulumi.log.info("Phase 3 Sprint 3: Prep notification workflow deployed")
elif enable_prep_notification and not (enable_calendar_monitor and enable_phase_1_5 and PHASE_1_5_AVAILABLE):
    pulumi.log.warn("Prep notification enabled but requires calendar monitor and Phase 1.5. Enable both first.")
else:
    pulumi.log.info("Prep notification disabled. Set enable_prep_notification=true to deploy.")

# Future phases will add:
# - Phase 4: Step Functions for meeting prep workflow
# - Phase 5: Additional agents (Budget, HR, Incident managers)
# - Phase 6: CloudWatch alarms and dashboards
# - Phase 7: VPC and enhanced security
