"""Storage resources: DynamoDB tables and S3 buckets.

Defines all data storage infrastructure for the Executive Assistant system.
"""

import pulumi
import pulumi_aws as aws


def create_dynamodb_tables(environment: str, kms_key: aws.kms.Key) -> dict[str, aws.dynamodb.Table]:
    """Create DynamoDB tables for the Executive Assistant system.

    Args:
        environment: Environment name (dev, staging, prod)
        kms_key: KMS key for encryption at rest

    Returns:
        Dictionary of table name to Table resource
    """
    tables = {}

    # Meetings table
    meetings_table = aws.dynamodb.Table(
        f"exec-assistant-meetings-{environment}",
        name=f"exec-assistant-meetings-{environment}",
        billing_mode="PAY_PER_REQUEST",  # On-demand pricing
        hash_key="meeting_id",
        range_key="user_id",
        attributes=[
            aws.dynamodb.TableAttributeArgs(name="meeting_id", type="S"),
            aws.dynamodb.TableAttributeArgs(name="user_id", type="S"),
            aws.dynamodb.TableAttributeArgs(name="start_time", type="S"),
        ],
        global_secondary_indexes=[
            # Index for querying meetings by user and start time
            aws.dynamodb.TableGlobalSecondaryIndexArgs(
                name="UserStartTimeIndex",
                hash_key="user_id",
                range_key="start_time",
                projection_type="ALL",
            ),
        ],
        ttl=aws.dynamodb.TableTtlArgs(
            enabled=True,
            attribute_name="ttl",  # Optional TTL for old meetings
        ),
        server_side_encryption=aws.dynamodb.TableServerSideEncryptionArgs(
            enabled=True,
            kms_key_arn=kms_key.arn,
        ),
        point_in_time_recovery=aws.dynamodb.TablePointInTimeRecoveryArgs(
            enabled=(environment == "prod"),  # Only enable PITR for prod
        ),
        tags={
            "Environment": environment,
            "Project": "exec-assistant",
            "ManagedBy": "pulumi",
        },
    )
    tables["meetings"] = meetings_table

    # Chat sessions table
    chat_sessions_table = aws.dynamodb.Table(
        f"exec-assistant-chat-sessions-{environment}",
        name=f"exec-assistant-chat-sessions-{environment}",
        billing_mode="PAY_PER_REQUEST",
        hash_key="session_id",
        attributes=[
            aws.dynamodb.TableAttributeArgs(name="session_id", type="S"),
            aws.dynamodb.TableAttributeArgs(name="user_id", type="S"),
            aws.dynamodb.TableAttributeArgs(name="meeting_id", type="S"),
        ],
        global_secondary_indexes=[
            # Index for querying sessions by user
            aws.dynamodb.TableGlobalSecondaryIndexArgs(
                name="UserIndex",
                hash_key="user_id",
                projection_type="ALL",
            ),
            # Index for querying sessions by meeting
            aws.dynamodb.TableGlobalSecondaryIndexArgs(
                name="MeetingIndex",
                hash_key="meeting_id",
                projection_type="ALL",
            ),
        ],
        ttl=aws.dynamodb.TableTtlArgs(
            enabled=True,
            attribute_name="expires_at",  # Auto-delete expired sessions
        ),
        server_side_encryption=aws.dynamodb.TableServerSideEncryptionArgs(
            enabled=True,
            kms_key_arn=kms_key.arn,
        ),
        point_in_time_recovery=aws.dynamodb.TablePointInTimeRecoveryArgs(
            enabled=(environment == "prod"),
        ),
        tags={
            "Environment": environment,
            "Project": "exec-assistant",
            "ManagedBy": "pulumi",
        },
    )
    tables["chat_sessions"] = chat_sessions_table

    # Action items table (for Phase 5+)
    action_items_table = aws.dynamodb.Table(
        f"exec-assistant-action-items-{environment}",
        name=f"exec-assistant-action-items-{environment}",
        billing_mode="PAY_PER_REQUEST",
        hash_key="action_id",
        attributes=[
            aws.dynamodb.TableAttributeArgs(name="action_id", type="S"),
            aws.dynamodb.TableAttributeArgs(name="meeting_id", type="S"),
            aws.dynamodb.TableAttributeArgs(name="owner", type="S"),
        ],
        global_secondary_indexes=[
            # Index for querying action items by meeting
            aws.dynamodb.TableGlobalSecondaryIndexArgs(
                name="MeetingIndex",
                hash_key="meeting_id",
                projection_type="ALL",
            ),
            # Index for querying action items by owner
            aws.dynamodb.TableGlobalSecondaryIndexArgs(
                name="OwnerIndex",
                hash_key="owner",
                projection_type="ALL",
            ),
        ],
        server_side_encryption=aws.dynamodb.TableServerSideEncryptionArgs(
            enabled=True,
            kms_key_arn=kms_key.arn,
        ),
        point_in_time_recovery=aws.dynamodb.TablePointInTimeRecoveryArgs(
            enabled=(environment == "prod"),
        ),
        tags={
            "Environment": environment,
            "Project": "exec-assistant",
            "ManagedBy": "pulumi",
        },
    )
    tables["action_items"] = action_items_table

    # Users table (for Phase 1.5 - web auth)
    users_table = aws.dynamodb.Table(
        f"exec-assistant-users-{environment}",
        name=f"exec-assistant-users-{environment}",
        billing_mode="PAY_PER_REQUEST",
        hash_key="user_id",
        attributes=[
            aws.dynamodb.TableAttributeArgs(name="user_id", type="S"),
            aws.dynamodb.TableAttributeArgs(name="google_id", type="S"),
            aws.dynamodb.TableAttributeArgs(name="email", type="S"),
        ],
        global_secondary_indexes=[
            # Index for looking up user by Google ID
            aws.dynamodb.TableGlobalSecondaryIndexArgs(
                name="GoogleIdIndex",
                hash_key="google_id",
                projection_type="ALL",
            ),
            # Index for looking up user by email
            aws.dynamodb.TableGlobalSecondaryIndexArgs(
                name="EmailIndex",
                hash_key="email",
                projection_type="ALL",
            ),
        ],
        server_side_encryption=aws.dynamodb.TableServerSideEncryptionArgs(
            enabled=True,
            kms_key_arn=kms_key.arn,
        ),
        point_in_time_recovery=aws.dynamodb.TablePointInTimeRecoveryArgs(
            enabled=(environment == "prod"),
        ),
        tags={
            "Environment": environment,
            "Project": "exec-assistant",
            "ManagedBy": "pulumi",
        },
    )
    tables["users"] = users_table

    return tables


def create_s3_buckets(environment: str, kms_key: aws.kms.Key) -> dict[str, aws.s3.Bucket]:
    """Create S3 buckets for the Executive Assistant system.

    Args:
        environment: Environment name (dev, staging, prod)
        kms_key: KMS key for encryption at rest

    Returns:
        Dictionary of bucket name to Bucket resource
    """
    buckets = {}

    # Documents bucket (for meeting materials)
    documents_bucket = aws.s3.Bucket(
        f"exec-assistant-documents-{environment}",
        bucket=f"exec-assistant-documents-{environment}",
        acl="private",
        versioning=aws.s3.BucketVersioningArgs(
            enabled=(environment == "prod"),  # Versioning for prod
        ),
        server_side_encryption_configuration=aws.s3.BucketServerSideEncryptionConfigurationArgs(
            rule=aws.s3.BucketServerSideEncryptionConfigurationRuleArgs(
                apply_server_side_encryption_by_default=aws.s3.BucketServerSideEncryptionConfigurationRuleApplyServerSideEncryptionByDefaultArgs(
                    sse_algorithm="aws:kms",
                    kms_master_key_id=kms_key.id,
                ),
            ),
        ),
        lifecycle_rules=[
            aws.s3.BucketLifecycleRuleArgs(
                enabled=True,
                id="expire-old-materials",
                expiration=aws.s3.BucketLifecycleRuleExpirationArgs(
                    days=90,  # Delete materials after 90 days
                ),
            ),
        ],
        tags={
            "Environment": environment,
            "Project": "exec-assistant",
            "ManagedBy": "pulumi",
        },
    )

    # Block public access
    aws.s3.BucketPublicAccessBlock(
        f"exec-assistant-documents-{environment}-public-access-block",
        bucket=documents_bucket.id,
        block_public_acls=True,
        block_public_policy=True,
        ignore_public_acls=True,
        restrict_public_buckets=True,
    )

    buckets["documents"] = documents_bucket

    # Agent sessions bucket (for Strands SDK session persistence)
    sessions_bucket = aws.s3.Bucket(
        f"exec-assistant-sessions-{environment}",
        bucket=f"exec-assistant-sessions-{environment}",
        acl="private",
        versioning=aws.s3.BucketVersioningArgs(
            enabled=False,  # No versioning needed for sessions
        ),
        server_side_encryption_configuration=aws.s3.BucketServerSideEncryptionConfigurationArgs(
            rule=aws.s3.BucketServerSideEncryptionConfigurationRuleArgs(
                apply_server_side_encryption_by_default=aws.s3.BucketServerSideEncryptionConfigurationRuleApplyServerSideEncryptionByDefaultArgs(
                    sse_algorithm="aws:kms",
                    kms_master_key_id=kms_key.id,
                ),
            ),
        ),
        lifecycle_rules=[
            aws.s3.BucketLifecycleRuleArgs(
                enabled=True,
                id="expire-old-sessions",
                expiration=aws.s3.BucketLifecycleRuleExpirationArgs(
                    days=7,  # Delete sessions after 7 days
                ),
            ),
        ],
        tags={
            "Environment": environment,
            "Project": "exec-assistant",
            "ManagedBy": "pulumi",
        },
    )

    # Block public access
    aws.s3.BucketPublicAccessBlock(
        f"exec-assistant-sessions-{environment}-public-access-block",
        bucket=sessions_bucket.id,
        block_public_acls=True,
        block_public_policy=True,
        ignore_public_acls=True,
        restrict_public_buckets=True,
    )

    buckets["sessions"] = sessions_bucket

    return buckets


def create_kms_key(environment: str) -> aws.kms.Key:
    """Create KMS key for encryption at rest.

    Args:
        environment: Environment name (dev, staging, prod)

    Returns:
        KMS key resource
    """
    kms_key = aws.kms.Key(
        f"exec-assistant-{environment}",
        description=f"KMS key for Executive Assistant {environment} environment",
        deletion_window_in_days=30,
        enable_key_rotation=True,
        tags={
            "Environment": environment,
            "Project": "exec-assistant",
            "ManagedBy": "pulumi",
        },
    )

    # Create key alias for easier reference
    aws.kms.Alias(
        f"exec-assistant-{environment}-alias",
        name=f"alias/exec-assistant-{environment}",
        target_key_id=kms_key.id,
    )

    return kms_key
