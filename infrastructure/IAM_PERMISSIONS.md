# IAM Permissions and Roles

## Overview

This document describes the IAM roles and policies configured for the Executive Assistant application.

## Lambda Execution Role

**Role Name:** `exec-assistant-lambda-role-{environment}`

### Trust Policy

Allows Lambda service to assume this role:
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Action": "sts:AssumeRole",
    "Effect": "Allow",
    "Principal": {
      "Service": "lambda.amazonaws.com"
    }
  }]
}
```

### Managed Policies

- **AWSLambdaBasicExecutionRole** - Provides CloudWatch Logs permissions for Lambda function logging

### Custom Inline Policy

#### DynamoDB Permissions

Grants access to all application DynamoDB tables:

**Actions:**
- `dynamodb:GetItem` - Read individual items
- `dynamodb:PutItem` - Create new items
- `dynamodb:UpdateItem` - Modify existing items
- `dynamodb:Query` - Query table with filters
- `dynamodb:Scan` - Scan entire table
- `dynamodb:DeleteItem` - Delete items

**Resources:**
- `users` table and indexes
- `chat_sessions` table and indexes
- `meetings` table and indexes
- `action_items` table and indexes

#### KMS Permissions

Grants access to KMS key for encryption/decryption:

**Actions:**
- `kms:Decrypt` - Decrypt data
- `kms:Encrypt` - Encrypt data
- `kms:GenerateDataKey` - Generate data keys for envelope encryption
- `kms:DescribeKey` - Get key metadata

**Resources:**
- Application KMS key: `exec-assistant-kms-{environment}`

#### S3 Permissions (Phase 2+)

Grants access to session storage bucket:

**Actions - Bucket Level:**
- `s3:ListBucket` - List objects in bucket (required for session existence checks)

**Actions - Object Level:**
- `s3:GetObject` - Read session files
- `s3:PutObject` - Write session files
- `s3:DeleteObject` - Remove expired sessions

**Resources:**
- Sessions bucket: `exec-assistant-sessions-{environment}`

#### Bedrock Permissions (Phase 2+)

Grants access to AWS Bedrock models:

**Actions:**
- `bedrock:InvokeModel` - Call Bedrock foundation models

**Resources:**
- AWS Nova model family: `arn:aws:bedrock:*::foundation-model/us.amazon.nova-*`

#### Secrets Manager Permissions

Grants access to secrets:

**Actions:**
- `secretsmanager:GetSecretValue` - Read secret values

**Resources:**
- Currently: `*` (will be narrowed in production to specific secret ARNs)

## Lambda Functions

### Authentication Lambda

**Function Name:** `exec-assistant-auth-{environment}`

**Environment Variables:**
- `USERS_TABLE_NAME` - DynamoDB users table name
- `GOOGLE_OAUTH_CLIENT_ID` - Google OAuth client ID (secret)
- `GOOGLE_OAUTH_CLIENT_SECRET` - Google OAuth client secret (secret)
- `GOOGLE_OAUTH_REDIRECT_URI` - OAuth redirect URI
- `JWT_SECRET_KEY` - JWT signing key (secret)
- `FRONTEND_URL` - Frontend application URL
- `ENV` - Environment name (`dev`, `staging`, `prod`) - **NOT** `local`
- `AWS_REGION` - AWS region (`us-east-1`)

**Timeout:** 30 seconds
**Memory:** 512 MB
**Runtime:** Python 3.13

### Agent Lambda (Phase 2+)

**Function Name:** `exec-assistant-agent-{environment}`

**Environment Variables:**
- `CHAT_SESSIONS_TABLE_NAME` - DynamoDB chat sessions table name
- `MEETINGS_TABLE_NAME` - DynamoDB meetings table name (future use)
- `SESSIONS_BUCKET_NAME` - S3 bucket for session storage
- `JWT_SECRET_KEY` - JWT signing key (secret)
- `ENV` - Environment name (`dev`, `staging`, `prod`) - **NOT** `local`
- `AWS_REGION` - AWS region (`us-east-1`)

**Timeout:** 60 seconds
**Memory:** 1024 MB
**Runtime:** Python 3.13

## API Gateway Permissions

### Lambda Invoke Permissions

API Gateway is granted permission to invoke Lambda functions:

**Principal:** `apigateway.amazonaws.com`
**Action:** `lambda:InvokeFunction`
**Source ARN:** `{api-execution-arn}/*/*`

This allows API Gateway to invoke:
- Authentication Lambda for `/auth/*` routes
- Agent Lambda for `/chat/*` routes (Phase 2+)

## Security Best Practices

### Current Implementation

1. **Encryption at Rest:**
   - All DynamoDB tables encrypted with KMS
   - S3 buckets use server-side encryption

2. **Encryption in Transit:**
   - API Gateway uses HTTPS
   - All AWS service calls use TLS

3. **Least Privilege:**
   - Lambda role has only necessary permissions
   - Resources scoped to specific tables and buckets
   - KMS key access restricted to single key

4. **Secret Management:**
   - Sensitive values stored in Pulumi secrets
   - JWT keys and OAuth credentials protected
   - Secrets injected as environment variables at runtime

### Production Hardening (TODO)

1. **Narrow Secrets Access:**
   ```json
   {
     "Effect": "Allow",
     "Action": "secretsmanager:GetSecretValue",
     "Resource": [
       "arn:aws:secretsmanager:us-east-1:*:secret:exec-assistant/jwt-key-*",
       "arn:aws:secretsmanager:us-east-1:*:secret:exec-assistant/google-oauth-*"
     ]
   }
   ```

2. **VPC Configuration:**
   - Deploy Lambdas in VPC
   - Use VPC endpoints for AWS services
   - Security groups for network isolation

3. **Resource-Based Policies:**
   - DynamoDB table policies
   - S3 bucket policies
   - KMS key policies

4. **IAM Conditions:**
   - Time-based access
   - Source IP restrictions
   - MFA requirements for sensitive operations

5. **CloudTrail Logging:**
   - Log all IAM and API calls
   - Monitor for unauthorized access
   - Alert on suspicious activity

## Permission Troubleshooting

### Common Errors

#### 1. S3 AccessDenied - ListBucket

**Error:**
```
User: arn:aws:sts::*:assumed-role/exec-assistant-lambda-role-dev/*
is not authorized to perform: s3:ListBucket
```

**Cause:** Missing `s3:ListBucket` permission on bucket (not objects)

**Solution:** Add bucket-level permission:
```json
{
  "Effect": "Allow",
  "Action": ["s3:ListBucket"],
  "Resource": "arn:aws:s3:::exec-assistant-sessions-dev"
}
```

#### 2. DynamoDB AccessDenied

**Error:**
```
User is not authorized to perform: dynamodb:GetItem on resource: table/exec-assistant-*
```

**Cause:** Missing DynamoDB table permission

**Solution:** Ensure table ARN is in policy and includes indexes:
```json
{
  "Effect": "Allow",
  "Action": ["dynamodb:GetItem"],
  "Resource": [
    "arn:aws:dynamodb:us-east-1:*:table/exec-assistant-*",
    "arn:aws:dynamodb:us-east-1:*:table/exec-assistant-*/index/*"
  ]
}
```

#### 3. KMS AccessDenied

**Error:**
```
User is not authorized to perform: kms:Decrypt on resource: key/*
```

**Cause:** Missing KMS key permission

**Solution:** Add KMS key ARN to policy:
```json
{
  "Effect": "Allow",
  "Action": ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey"],
  "Resource": "arn:aws:kms:us-east-1:*:key/*"
}
```

#### 4. Bedrock AccessDenied

**Error:**
```
User is not authorized to perform: bedrock:InvokeModel
```

**Cause:** Missing Bedrock model permission

**Solution:** Add Bedrock model resource:
```json
{
  "Effect": "Allow",
  "Action": ["bedrock:InvokeModel"],
  "Resource": "arn:aws:bedrock:*::foundation-model/us.amazon.nova-*"
}
```

### Debugging Steps

1. **Check CloudWatch Logs:**
   ```bash
   aws logs tail /aws/lambda/exec-assistant-agent-dev --follow
   ```

2. **Verify IAM Policy:**
   ```bash
   aws iam get-role-policy \
     --role-name exec-assistant-lambda-role-dev \
     --policy-name exec-assistant-lambda-policy-dev
   ```

3. **Test Permissions:**
   ```bash
   # From Lambda function context
   aws sts get-caller-identity
   ```

4. **Check Environment Variables:**
   ```bash
   aws lambda get-function-configuration \
     --function-name exec-assistant-agent-dev \
     --query 'Environment.Variables'
   ```

## Policy Updates

When updating IAM policies:

1. Update `infrastructure/api.py` - `create_lambda_policy()` function
2. Deploy with Pulumi:
   ```bash
   cd infrastructure
   source ../.venv/bin/activate
   pulumi up
   ```
3. Verify policy attached:
   ```bash
   aws iam list-role-policies --role-name exec-assistant-lambda-role-dev
   ```
4. Test Lambda function to confirm permissions work

## Compliance Notes

- **GDPR:** Personal data in DynamoDB encrypted with KMS
- **SOC 2:** CloudWatch logging enabled for audit trail
- **PCI DSS:** TLS in transit, encryption at rest for all data
- **HIPAA:** Not currently compliant - requires VPC and additional controls

## References

- AWS Lambda IAM Best Practices: https://docs.aws.amazon.com/lambda/latest/dg/lambda-permissions.html
- AWS IAM Policy Simulator: https://policysim.aws.amazon.com/
- AWS Security Best Practices: https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html
