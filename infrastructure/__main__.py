"""Main Pulumi program for Executive Assistant infrastructure.

Deploys all AWS resources for the Executive Assistant system:
- KMS keys for encryption
- DynamoDB tables for data storage
- S3 buckets for documents and sessions
- (Future phases: Lambda functions, API Gateway, Step Functions, EventBridge)
"""

import pulumi

from storage import create_dynamodb_tables, create_kms_key, create_s3_buckets

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

# Future phases will add:
# - Lambda functions (agents, webhook handlers)
# - API Gateway (for Slack webhooks)
# - Step Functions (for meeting prep workflow)
# - EventBridge rules (for calendar monitoring)
# - CloudWatch alarms and dashboards
# - VPC and networking (if needed for security)
