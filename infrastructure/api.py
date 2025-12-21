"""API Gateway and Lambda resources for authentication and chat interface.

Defines:
- Lambda functions for auth endpoints
- API Gateway REST API
- Lambda permissions
- CloudWatch log groups
"""

import json
from pathlib import Path

import pulumi
import pulumi_aws as aws


def create_lambda_role(environment: str) -> aws.iam.Role:
    """Create IAM role for Lambda functions.

    Args:
        environment: Environment name (dev, staging, prod)

    Returns:
        IAM role for Lambda execution
    """
    # Trust policy allowing Lambda to assume this role
    assume_role_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Action": "sts:AssumeRole",
                "Effect": "Allow",
                "Principal": {
                    "Service": "lambda.amazonaws.com",
                },
            },
        ],
    }

    role = aws.iam.Role(
        f"exec-assistant-lambda-role-{environment}",
        name=f"exec-assistant-lambda-role-{environment}",
        assume_role_policy=json.dumps(assume_role_policy),
        tags={
            "Environment": environment,
            "Project": "exec-assistant",
            "ManagedBy": "pulumi",
        },
    )

    # Attach basic Lambda execution policy
    aws.iam.RolePolicyAttachment(
        f"exec-assistant-lambda-basic-{environment}",
        role=role.name,
        policy_arn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
    )

    return role


def create_lambda_policy(
    environment: str,
    role: aws.iam.Role,
    dynamodb_tables: dict[str, aws.dynamodb.Table],
    kms_key: aws.kms.Key,
    sessions_bucket: aws.s3.Bucket | None = None,
) -> None:
    """Create IAM policy for Lambda functions to access resources.

    Args:
        environment: Environment name
        role: Lambda IAM role
        dynamodb_tables: Dictionary of DynamoDB tables
        kms_key: KMS key for encryption
        sessions_bucket: Optional S3 bucket for session storage
    """
    # Get all table ARNs
    users_table_arn = dynamodb_tables["users"].arn
    chat_sessions_table_arn = dynamodb_tables["chat_sessions"].arn
    meetings_table_arn = dynamodb_tables["meetings"].arn
    action_items_table_arn = dynamodb_tables["action_items"].arn

    # Build resource list for Output.all()
    resources = [
        users_table_arn,
        chat_sessions_table_arn,
        meetings_table_arn,
        action_items_table_arn,
        kms_key.arn,
    ]
    if sessions_bucket:
        resources.append(sessions_bucket.arn)

    # Policy allowing Lambda to access DynamoDB, KMS, S3, and Bedrock
    policy_document = pulumi.Output.all(*resources).apply(
        lambda args: json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": [
                            "dynamodb:GetItem",
                            "dynamodb:PutItem",
                            "dynamodb:UpdateItem",
                            "dynamodb:Query",
                            "dynamodb:Scan",
                            "dynamodb:DeleteItem",
                        ],
                        "Resource": [
                            args[0],  # users_table_arn
                            f"{args[0]}/index/*",  # users table indexes
                            args[1],  # chat_sessions_table_arn
                            f"{args[1]}/index/*",  # chat_sessions table indexes
                            args[2],  # meetings_table_arn
                            f"{args[2]}/index/*",  # meetings table indexes
                            args[3],  # action_items_table_arn
                            f"{args[3]}/index/*",  # action_items table indexes
                        ],
                    },
                    {
                        "Effect": "Allow",
                        "Action": [
                            "kms:Decrypt",
                            "kms:Encrypt",
                            "kms:GenerateDataKey",
                            "kms:DescribeKey",
                        ],
                        "Resource": args[4],  # kms_key_arn
                    },
                    {
                        "Effect": "Allow",
                        "Action": [
                            "secretsmanager:GetSecretValue",
                        ],
                        "Resource": "*",  # Will narrow down in production
                    },
                ]
                + (
                    [
                        {
                            "Effect": "Allow",
                            "Action": [
                                "s3:ListBucket",
                            ],
                            "Resource": args[5],  # sessions_bucket_arn (bucket itself)
                        },
                        {
                            "Effect": "Allow",
                            "Action": [
                                "s3:GetObject",
                                "s3:PutObject",
                                "s3:DeleteObject",
                            ],
                            "Resource": f"{args[5]}/*",  # sessions_bucket_arn (objects)
                        },
                        {
                            "Effect": "Allow",
                            "Action": [
                                "bedrock:InvokeModel",
                                "bedrock:InvokeModelWithResponseStream",
                            ],
                            "Resource": [
                                "arn:aws:bedrock:*::foundation-model/us.amazon.nova-*",
                                "arn:aws:bedrock:*:*:inference-profile/*",
                            ],
                        },
                    ]
                    if sessions_bucket
                    else []
                ),
            }
        )
    )

    aws.iam.RolePolicy(
        f"exec-assistant-lambda-policy-{environment}",
        role=role.id,
        policy=policy_document,
    )


def create_auth_lambda(
    environment: str,
    role: aws.iam.Role,
    users_table: aws.dynamodb.Table,
    config: pulumi.Config,
    api_endpoint: pulumi.Output[str] | None = None,
) -> aws.lambda_.Function:
    """Create Lambda function for authentication endpoints.

    Args:
        environment: Environment name
        role: Lambda IAM role
        users_table: Users DynamoDB table
        config: Pulumi configuration
        api_endpoint: Optional API Gateway endpoint URL (Pulumi Output)

    Returns:
        Lambda function resource
    """
    # Create CloudWatch log group
    log_group = aws.cloudwatch.LogGroup(
        f"exec-assistant-auth-lambda-logs-{environment}",
        name=f"/aws/lambda/exec-assistant-auth-{environment}",
        retention_in_days=7 if environment == "dev" else 30,
        tags={
            "Environment": environment,
            "Project": "exec-assistant",
            "ManagedBy": "pulumi",
        },
    )

    # Get config values
    google_oauth_client_id = config.require_secret("google_oauth_client_id")
    google_oauth_client_secret = config.require_secret("google_oauth_client_secret")
    jwt_secret_key = config.require_secret("jwt_secret_key") if config.get_secret("jwt_secret_key") else pulumi.Output.secret("changeme-generate-secure-key")

    # Construct redirect URI from API endpoint
    # If api_endpoint provided, use it to construct the OAuth callback URL
    # Otherwise fall back to config value or placeholder
    if api_endpoint:
        redirect_uri = api_endpoint.apply(lambda endpoint: f"{endpoint}/auth/callback")
    else:
        redirect_uri = config.get("google_oauth_redirect_uri") or "https://placeholder.com/auth/callback"

    frontend_url = config.get("frontend_url") or "https://placeholder.com"

    # Build Lambda deployment package with dependencies
    import subprocess
    import shutil
    import tempfile

    # Create deployment package
    package_dir = Path(__file__).parent / ".lambda_build"
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

    # Install dependencies to package directory
    requirements = [
        "pydantic>=2.0",
        "requests",
        "pyjwt",
    ]

    print(f"Installing Lambda dependencies to {package_dir}...")
    subprocess.run(
        [
            "pip",
            "install",
            "--target",
            str(package_dir),
            "--upgrade",
            "--no-user",
        ] + requirements,
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
    # Use Output.all() to handle both static values and Pulumi Outputs
    env_vars = {
        "USERS_TABLE_NAME": users_table.name,
        "GOOGLE_OAUTH_CLIENT_ID": google_oauth_client_id,
        "GOOGLE_OAUTH_CLIENT_SECRET": google_oauth_client_secret,
        "JWT_SECRET_KEY": jwt_secret_key,
        "FRONTEND_URL": frontend_url,
        "ENV": environment,  # Set to 'dev', 'staging', or 'prod' (NOT 'local')
    }

    # Add GOOGLE_OAUTH_REDIRECT_URI
    # If it's a Pulumi Output, Pulumi will handle it automatically
    env_vars["GOOGLE_OAUTH_REDIRECT_URI"] = redirect_uri

    # Create Lambda function
    auth_lambda = aws.lambda_.Function(
        f"exec-assistant-auth-{environment}",
        name=f"exec-assistant-auth-{environment}",
        role=role.arn,
        runtime="python3.13",
        handler="exec_assistant.interfaces.auth_handler.handler",
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

    return auth_lambda


def create_agent_lambda(
    environment: str,
    role: aws.iam.Role,
    chat_sessions_table: aws.dynamodb.Table,
    sessions_bucket: aws.s3.Bucket,
    config: pulumi.Config,
) -> aws.lambda_.Function:
    """Create Lambda function for agent chat endpoints.

    Args:
        environment: Environment name
        role: Lambda IAM role
        chat_sessions_table: Chat sessions DynamoDB table
        sessions_bucket: S3 bucket for session storage
        config: Pulumi configuration

    Returns:
        Lambda function resource
    """
    # Create CloudWatch log group
    log_group = aws.cloudwatch.LogGroup(
        f"exec-assistant-agent-lambda-logs-{environment}",
        name=f"/aws/lambda/exec-assistant-agent-{environment}",
        retention_in_days=7 if environment == "dev" else 30,
        tags={
            "Environment": environment,
            "Project": "exec-assistant",
            "ManagedBy": "pulumi",
        },
    )

    # Get config values
    jwt_secret_key = config.require_secret("jwt_secret_key")

    # Build Lambda deployment package with dependencies
    import subprocess
    import shutil

    # Create deployment package
    package_dir = Path(__file__).parent / ".lambda_build_agent"
    package_dir.mkdir(exist_ok=True)

    # Copy source code
    src_dir = Path(__file__).parent.parent / "src" / "exec_assistant"

    # Copy relevant modules (including agents)
    for module in ["shared", "interfaces", "agents"]:
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
        "pyjwt",
        "strands-agents",  # Strands Agent SDK
    ]

    print(f"Installing agent Lambda dependencies to {package_dir}...")
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

    # Create Lambda function
    agent_lambda = aws.lambda_.Function(
        f"exec-assistant-agent-{environment}",
        name=f"exec-assistant-agent-{environment}",
        role=role.arn,
        runtime="python3.13",
        handler="exec_assistant.interfaces.agent_handler.handler",
        code=lambda_code,
        timeout=60,  # Longer timeout for agent processing
        memory_size=1024,  # More memory for agent execution
        environment=aws.lambda_.FunctionEnvironmentArgs(
            variables={
                "CHAT_SESSIONS_TABLE_NAME": chat_sessions_table.name,
                "MEETINGS_TABLE_NAME": "",  # Will be added in future phases
                "SESSIONS_BUCKET_NAME": sessions_bucket.bucket,
                "JWT_SECRET_KEY": jwt_secret_key,
                "ENV": environment,  # Set to 'dev', 'staging', or 'prod' (NOT 'local')
                #"AWS_REGION": "us-east-1",
            },
        ),
        tags={
            "Environment": environment,
            "Project": "exec-assistant",
            "ManagedBy": "pulumi",
        },
    )

    return agent_lambda


def create_api_gateway(
    environment: str,
    auth_lambda: aws.lambda_.Function,
    agent_lambda: aws.lambda_.Function | None = None,
) -> tuple[aws.apigatewayv2.Api, pulumi.Output[str]]:
    """Create API Gateway HTTP API.

    Args:
        environment: Environment name
        auth_lambda: Authentication Lambda function
        agent_lambda: Optional agent chat Lambda function

    Returns:
        Tuple of (API Gateway resource, API endpoint URL as Pulumi Output)
    """
    # Create HTTP API
    api = aws.apigatewayv2.Api(
        f"exec-assistant-api-{environment}",
        name=f"exec-assistant-api-{environment}",
        protocol_type="HTTP",
        cors_configuration=aws.apigatewayv2.ApiCorsConfigurationArgs(
            allow_origins=["*"],  # Should be restricted in production
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization"],
            # Note: allow_credentials not supported with wildcard origin
        ),
        tags={
            "Environment": environment,
            "Project": "exec-assistant",
            "ManagedBy": "pulumi",
        },
    )

    # Create Lambda integration for auth
    auth_integration = aws.apigatewayv2.Integration(
        f"exec-assistant-auth-integration-{environment}",
        api_id=api.id,
        integration_type="AWS_PROXY",
        integration_uri=auth_lambda.arn,
        payload_format_version="2.0",
    )

    # Create auth routes
    auth_routes = [
        ("GET", "/auth/login"),
        ("GET", "/auth/callback"),
        ("POST", "/auth/refresh"),
        ("GET", "/auth/me"),
    ]

    for method, path in auth_routes:
        aws.apigatewayv2.Route(
            f"exec-assistant-{method.lower()}-{path.replace('/', '-')}-{environment}",
            api_id=api.id,
            route_key=f"{method} {path}",
            target=auth_integration.id.apply(lambda id: f"integrations/{id}"),
        )

    # Grant API Gateway permission to invoke auth Lambda
    aws.lambda_.Permission(
        f"exec-assistant-api-auth-lambda-permission-{environment}",
        action="lambda:InvokeFunction",
        function=auth_lambda.name,
        principal="apigateway.amazonaws.com",
        source_arn=api.execution_arn.apply(lambda arn: f"{arn}/*/*"),
    )

    # Create agent integration and routes if agent Lambda provided
    if agent_lambda:
        agent_integration = aws.apigatewayv2.Integration(
            f"exec-assistant-agent-integration-{environment}",
            api_id=api.id,
            integration_type="AWS_PROXY",
            integration_uri=agent_lambda.arn,
            payload_format_version="2.0",
        )

        # Create agent routes
        agent_routes = [
            ("POST", "/chat/send"),
        ]

        for method, path in agent_routes:
            aws.apigatewayv2.Route(
                f"exec-assistant-{method.lower()}-{path.replace('/', '-')}-{environment}",
                api_id=api.id,
                route_key=f"{method} {path}",
                target=agent_integration.id.apply(lambda id: f"integrations/{id}"),
            )

        # Grant API Gateway permission to invoke agent Lambda
        aws.lambda_.Permission(
            f"exec-assistant-api-agent-lambda-permission-{environment}",
            action="lambda:InvokeFunction",
            function=agent_lambda.name,
            principal="apigateway.amazonaws.com",
            source_arn=api.execution_arn.apply(lambda arn: f"{arn}/*/*"),
        )

    # Create stage (auto-deploy)
    stage = aws.apigatewayv2.Stage(
        f"exec-assistant-api-stage-{environment}",
        api_id=api.id,
        name="$default",
        auto_deploy=True,
        tags={
            "Environment": environment,
            "Project": "exec-assistant",
            "ManagedBy": "pulumi",
        },
    )

    # API endpoint URL
    api_endpoint = api.api_endpoint

    return api, api_endpoint


def create_auth_and_api_gateway(
    environment: str,
    lambda_role: aws.iam.Role,
    users_table: aws.dynamodb.Table,
    config: pulumi.Config,
    agent_lambda: aws.lambda_.Function | None = None,
) -> tuple[aws.lambda_.Function, aws.apigatewayv2.Api, pulumi.Output[str]]:
    """Create authentication Lambda and API Gateway with proper redirect URI configuration.

    This function solves the circular dependency between auth Lambda and API Gateway:
    - Auth Lambda needs API Gateway endpoint for OAuth redirect URI
    - API Gateway needs auth Lambda ARN for integration

    Solution: Create a temporary API resource to get the endpoint, then create auth Lambda
    with that endpoint, then complete the API Gateway setup.

    Args:
        environment: Environment name
        lambda_role: Lambda IAM role
        users_table: Users DynamoDB table
        config: Pulumi configuration
        agent_lambda: Optional agent Lambda function

    Returns:
        Tuple of (auth Lambda, API Gateway, API endpoint URL)
    """
    # Step 1: Create API Gateway resource first (without routes)
    api = aws.apigatewayv2.Api(
        f"exec-assistant-api-{environment}",
        name=f"exec-assistant-api-{environment}",
        protocol_type="HTTP",
        cors_configuration=aws.apigatewayv2.ApiCorsConfigurationArgs(
            allow_origins=["*"],  # Should be restricted in production
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization"],
        ),
        tags={
            "Environment": environment,
            "Project": "exec-assistant",
            "ManagedBy": "pulumi",
        },
    )

    # Get API endpoint
    api_endpoint = api.api_endpoint

    # Step 2: Create auth Lambda with the API endpoint for redirect URI
    auth_lambda = create_auth_lambda(
        environment, lambda_role, users_table, config, api_endpoint
    )

    # Step 3: Create Lambda integration for auth
    auth_integration = aws.apigatewayv2.Integration(
        f"exec-assistant-auth-integration-{environment}",
        api_id=api.id,
        integration_type="AWS_PROXY",
        integration_uri=auth_lambda.arn,
        payload_format_version="2.0",
    )

    # Create auth routes
    auth_routes = [
        ("GET", "/auth/login"),
        ("GET", "/auth/callback"),
        ("POST", "/auth/refresh"),
        ("GET", "/auth/me"),
    ]

    for method, path in auth_routes:
        aws.apigatewayv2.Route(
            f"exec-assistant-{method.lower()}-{path.replace('/', '-')}-{environment}",
            api_id=api.id,
            route_key=f"{method} {path}",
            target=auth_integration.id.apply(lambda id: f"integrations/{id}"),
        )

    # Grant API Gateway permission to invoke auth Lambda
    aws.lambda_.Permission(
        f"exec-assistant-api-auth-lambda-permission-{environment}",
        action="lambda:InvokeFunction",
        function=auth_lambda.name,
        principal="apigateway.amazonaws.com",
        source_arn=api.execution_arn.apply(lambda arn: f"{arn}/*/*"),
    )

    # Step 4: Create agent integration and routes if agent Lambda provided
    if agent_lambda:
        agent_integration = aws.apigatewayv2.Integration(
            f"exec-assistant-agent-integration-{environment}",
            api_id=api.id,
            integration_type="AWS_PROXY",
            integration_uri=agent_lambda.arn,
            payload_format_version="2.0",
        )

        # Create agent routes
        agent_routes = [
            ("POST", "/chat/send"),
        ]

        for method, path in agent_routes:
            aws.apigatewayv2.Route(
                f"exec-assistant-{method.lower()}-{path.replace('/', '-')}-{environment}",
                api_id=api.id,
                route_key=f"{method} {path}",
                target=agent_integration.id.apply(lambda id: f"integrations/{id}"),
            )

        # Grant API Gateway permission to invoke agent Lambda
        aws.lambda_.Permission(
            f"exec-assistant-api-agent-lambda-permission-{environment}",
            action="lambda:InvokeFunction",
            function=agent_lambda.name,
            principal="apigateway.amazonaws.com",
            source_arn=api.execution_arn.apply(lambda arn: f"{arn}/*/*"),
        )

    # Step 5: Create stage (auto-deploy)
    stage = aws.apigatewayv2.Stage(
        f"exec-assistant-api-stage-{environment}",
        api_id=api.id,
        name="$default",
        auto_deploy=True,
        tags={
            "Environment": environment,
            "Project": "exec-assistant",
            "ManagedBy": "pulumi",
        },
    )

    return auth_lambda, api, api_endpoint


def create_ui_bucket(environment: str) -> tuple[aws.s3.Bucket, str]:
    """Create S3 bucket for hosting static chat UI.

    Args:
        environment: Environment name

    Returns:
        Tuple of (S3 bucket, website URL)
    """
    # Create bucket for UI
    ui_bucket = aws.s3.Bucket(
        f"exec-assistant-ui-{environment}",
        bucket=f"exec-assistant-ui-{environment}",
        website=aws.s3.BucketWebsiteArgs(
            index_document="index.html",
            error_document="error.html",
        ),
        tags={
            "Environment": environment,
            "Project": "exec-assistant",
            "ManagedBy": "pulumi",
        },
    )

    # Make bucket publicly readable
    public_access_block = aws.s3.BucketPublicAccessBlock(
        f"exec-assistant-ui-{environment}-public-access",
        bucket=ui_bucket.id,
        block_public_acls=False,
        block_public_policy=False,
        ignore_public_acls=False,
        restrict_public_buckets=False,
    )

    # Bucket policy to allow public read (depends on public access block)
    bucket_policy = aws.s3.BucketPolicy(
        f"exec-assistant-ui-{environment}-policy",
        bucket=ui_bucket.id,
        policy=ui_bucket.arn.apply(
            lambda arn: json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Sid": "PublicReadGetObject",
                            "Effect": "Allow",
                            "Principal": "*",
                            "Action": "s3:GetObject",
                            "Resource": f"{arn}/*",
                        },
                    ],
                }
            )
        ),
        opts=pulumi.ResourceOptions(depends_on=[public_access_block]),
    )

    # Website URL
    website_url = ui_bucket.website_endpoint.apply(lambda endpoint: f"http://{endpoint}")

    return ui_bucket, website_url
