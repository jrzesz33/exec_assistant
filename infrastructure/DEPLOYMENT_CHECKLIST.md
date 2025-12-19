# Deployment Checklist

## Fixed Issues

### 1. Missing ENV Environment Variable ✅

**Problem:** Lambda functions were missing the `ENV` environment variable, causing session manager to fail.

**Solution:** Added `ENV` environment variable to both Lambda functions:
- Auth Lambda: `ENV={environment}` (e.g., "dev", "staging", "prod")
- Agent Lambda: `ENV={environment}`

**Critical:** ENV is set to the Pulumi environment parameter, **NOT** "local". This ensures:
- `ENV=dev` → Uses `S3SessionManager` in development
- `ENV=staging` → Uses `S3SessionManager` in staging
- `ENV=prod` → Uses `S3SessionManager` in production
- `ENV=local` → **Only for local development** (uses `FileSessionManager`)

### 2. Missing AWS_REGION Environment Variable ✅

**Problem:** Lambda functions didn't have AWS_REGION set, causing boto3 client initialization errors.

**Solution:** Added `AWS_REGION=us-east-1` to both Lambda functions.

### 3. S3 Permission Error - ListBucket ✅

**Problem:**
```
AccessDenied: User is not authorized to perform: s3:ListBucket on resource:
"arn:aws:s3:::exec-assistant-sessions-dev"
```

**Root Cause:** Strands SDK's `S3SessionManager` calls `s3:ListBucket` to check if session objects exist, but the IAM policy only granted object-level permissions (`s3:GetObject`, `s3:PutObject`, `s3:DeleteObject`).

**Solution:** Added two separate S3 permission statements:
1. **Bucket-level:** `s3:ListBucket` on the bucket ARN
2. **Object-level:** `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` on `{bucket}/*`

### 4. Missing DynamoDB Table Permissions ✅

**Problem:** IAM policy only granted access to `users` and `chat_sessions` tables.

**Solution:** Added permissions for all tables:
- `meetings` table and indexes
- `action_items` table and indexes
- Added `dynamodb:DeleteItem` action

### 5. Enhanced KMS Permissions ✅

**Solution:** Added `kms:DescribeKey` action for KMS key metadata access.

### 6. Bedrock Region Wildcard ✅

**Solution:** Changed Bedrock resource ARN from `us-east-1` to `*` to support multi-region deployments.

## Current IAM Policy Summary

### DynamoDB
- ✅ GetItem, PutItem, UpdateItem, Query, Scan, DeleteItem
- ✅ All tables: users, chat_sessions, meetings, action_items
- ✅ All table indexes

### S3 (Phase 2+)
- ✅ ListBucket (bucket level)
- ✅ GetObject, PutObject, DeleteObject (object level)
- ✅ Sessions bucket

### KMS
- ✅ Decrypt, Encrypt, GenerateDataKey, DescribeKey
- ✅ Application KMS key

### Bedrock (Phase 2+)
- ✅ InvokeModel
- ✅ AWS Nova model family (all regions)

### Secrets Manager
- ✅ GetSecretValue
- ⚠️ Resource: `*` (should be narrowed in production)

## Deployment Steps

### 1. Prerequisites

Ensure you have:
- ✅ AWS CLI configured with credentials
- ✅ Pulumi CLI installed
- ✅ Python 3.13+ with virtual environment
- ✅ Required secrets configured in Pulumi

### 2. Configure Pulumi Stack

```bash
cd infrastructure
source ../.venv/bin/activate

# Set environment (dev, staging, or prod)
pulumi stack select dev  # or create: pulumi stack init dev

# Configure secrets
pulumi config set --secret google_oauth_client_id "your-client-id"
pulumi config set --secret google_oauth_client_secret "your-client-secret"
pulumi config set --secret jwt_secret_key "$(openssl rand -base64 32)"

# Configure OAuth redirect URI (will update after deployment)
pulumi config set google_oauth_redirect_uri "https://placeholder.com/auth/callback"
pulumi config set frontend_url "https://placeholder.com"

# Enable Phase 1.5 (auth + UI)
pulumi config set enable_phase_1_5 true

# Enable Phase 2 (agent chat)
pulumi config set enable_phase_2 true
```

### 3. Deploy Infrastructure

```bash
# Preview changes
pulumi preview

# Deploy
pulumi up

# Save outputs
pulumi stack output api_endpoint > ../api_endpoint.txt
pulumi stack output ui_website_url > ../ui_url.txt
```

### 4. Update OAuth Redirect URI

After deployment, update Google OAuth redirect URI:

```bash
# Get API endpoint
API_ENDPOINT=$(pulumi stack output api_endpoint)

# Update Pulumi config
pulumi config set google_oauth_redirect_uri "${API_ENDPOINT}/auth/callback"

# Update frontend URL
UI_URL=$(pulumi stack output ui_website_url)
pulumi config set frontend_url "${UI_URL}"

# Redeploy to apply new config
pulumi up
```

### 5. Verify Deployment

```bash
# Check Lambda function configuration
aws lambda get-function-configuration \
  --function-name exec-assistant-agent-dev \
  --query 'Environment.Variables'

# Expected output should include:
# {
#   "CHAT_SESSIONS_TABLE_NAME": "exec-assistant-chat-sessions-dev",
#   "SESSIONS_BUCKET_NAME": "exec-assistant-sessions-dev",
#   "ENV": "dev",                    ← NOT "local"
#   "AWS_REGION": "us-east-1",      ← Should be present
#   "JWT_SECRET_KEY": "***"
# }

# Check IAM policy
aws iam get-role-policy \
  --role-name exec-assistant-lambda-role-dev \
  --policy-name exec-assistant-lambda-policy-dev \
  --query 'PolicyDocument.Statement[?contains(Action, `s3:ListBucket`)]'

# Expected: Should return statement with s3:ListBucket action
```

### 6. Test Agent Endpoint

```bash
# Get API endpoint
API_ENDPOINT=$(pulumi stack output api_endpoint)

# Test health (after implementing health endpoint)
curl "${API_ENDPOINT}/health"

# Or test via UI
UI_URL=$(pulumi stack output ui_website_url)
echo "Open browser to: ${UI_URL}"
```

## Environment Variables Checklist

### Auth Lambda
- [x] `USERS_TABLE_NAME`
- [x] `GOOGLE_OAUTH_CLIENT_ID`
- [x] `GOOGLE_OAUTH_CLIENT_SECRET`
- [x] `GOOGLE_OAUTH_REDIRECT_URI`
- [x] `JWT_SECRET_KEY`
- [x] `FRONTEND_URL`
- [x] `ENV` (dev/staging/prod)
- [x] `AWS_REGION`

### Agent Lambda (Phase 2)
- [x] `CHAT_SESSIONS_TABLE_NAME`
- [x] `MEETINGS_TABLE_NAME`
- [x] `SESSIONS_BUCKET_NAME`
- [x] `JWT_SECRET_KEY`
- [x] `ENV` (dev/staging/prod)
- [x] `AWS_REGION`

## Troubleshooting

### Issue: S3 ListBucket AccessDenied

**Check policy has bucket-level permission:**
```bash
aws iam get-role-policy \
  --role-name exec-assistant-lambda-role-dev \
  --policy-name exec-assistant-lambda-policy-dev \
  | jq '.PolicyDocument.Statement[] | select(.Action[] | contains("s3:ListBucket"))'
```

**Should return:**
```json
{
  "Effect": "Allow",
  "Action": ["s3:ListBucket"],
  "Resource": "arn:aws:s3:::exec-assistant-sessions-dev"
}
```

### Issue: ENV is still "local"

**Check Lambda environment:**
```bash
aws lambda get-function-configuration \
  --function-name exec-assistant-agent-dev \
  | jq '.Environment.Variables.ENV'
```

**Should return:** `"dev"`, `"staging"`, or `"prod"` - **NOT** `"local"`

**If wrong, redeploy:**
```bash
pulumi up --refresh
```

### Issue: Bedrock AccessDenied

**Check Bedrock permission in policy:**
```bash
aws iam get-role-policy \
  --role-name exec-assistant-lambda-role-dev \
  --policy-name exec-assistant-lambda-policy-dev \
  | jq '.PolicyDocument.Statement[] | select(.Action[] | contains("bedrock"))'
```

**Should include:**
```json
{
  "Effect": "Allow",
  "Action": ["bedrock:InvokeModel"],
  "Resource": "arn:aws:bedrock:*::foundation-model/us.amazon.nova-*"
}
```

### Issue: CloudWatch Logs Not Appearing

**Check basic execution role attached:**
```bash
aws iam list-attached-role-policies \
  --role-name exec-assistant-lambda-role-dev \
  | jq '.AttachedPolicies[] | select(.PolicyName | contains("Lambda"))'
```

**Should include:** `AWSLambdaBasicExecutionRole`

## Post-Deployment Steps

1. **Update Google OAuth Console:**
   - Add redirect URI: `{api_endpoint}/auth/callback`
   - Add authorized origin: `{ui_url}`

2. **Test Authentication Flow:**
   - Navigate to UI URL
   - Click "Login with Google"
   - Complete OAuth flow
   - Verify JWT token received

3. **Test Agent Chat:**
   - Send test message: "Hello, I need help with meeting prep"
   - Verify agent responds
   - Check CloudWatch logs for any errors

4. **Monitor Costs:**
   ```bash
   # Check Bedrock usage
   aws bedrock list-model-invocations --region us-east-1

   # Check S3 storage
   aws s3 ls s3://exec-assistant-sessions-dev/ --recursive | wc -l
   ```

## Rollback Procedure

If deployment fails:

```bash
# Rollback to previous stack
pulumi stack export > backup.json
pulumi cancel
pulumi refresh
pulumi up --target-dependents

# Or destroy and redeploy
pulumi destroy
pulumi up
```

## Security Hardening for Production

Before going to production:

1. **Narrow Secrets Manager permission** - Change `Resource: "*"` to specific secret ARNs
2. **Add VPC configuration** - Deploy Lambdas in private subnets
3. **Enable CloudTrail** - Log all API and IAM activity
4. **Add WAF rules** - Protect API Gateway from attacks
5. **Enable GuardDuty** - Threat detection
6. **Add CloudWatch Alarms** - Alert on errors and unauthorized access
7. **Implement rate limiting** - Prevent abuse
8. **Use secrets rotation** - Rotate JWT keys and OAuth credentials

## References

- See `IAM_PERMISSIONS.md` for detailed IAM documentation
- See `../TESTING_GUIDE.md` for local testing workflow
- See `../CLAUDE.md` for development patterns
