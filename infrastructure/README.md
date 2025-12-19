# Infrastructure Setup

This directory contains Pulumi infrastructure as code for the Executive Assistant system.

## Prerequisites

1. **AWS Account**: Access to an AWS account with admin permissions
2. **AWS CLI**: Configured with credentials
   ```bash
   aws configure
   ```
3. **Pulumi CLI**: Installed
   ```bash
   curl -fsSL https://get.pulumi.com | sh
   ```

## Initial Setup

### 1. Login to Pulumi

Choose your backend:

**Option A: Pulumi Cloud (recommended for teams)**
```bash
pulumi login
```

**Option B: Local backend (for solo development)**
```bash
pulumi login --local
```

**Option C: S3 backend**
```bash
pulumi login s3://<your-bucket-name>
```

### 2. Create a Stack

Create a new stack for your environment:

```bash
cd infrastructure
pulumi stack init dev
```

### 3. Configure the Stack

Set required configuration values:

```bash
# Set AWS region
pulumi config set aws:region us-east-1

# Environment is already set to 'dev' in Pulumi.yaml
# But you can override it:
pulumi config set exec-assistant:environment dev

# Set Slack secrets (required for Slack bot)
pulumi config set --secret exec-assistant:slack_signing_secret your-signing-secret-here
pulumi config set --secret exec-assistant:slack_bot_token xoxb-your-bot-token-here
export PATH="$PATH:/home/vscode/.pulumi/bin"
pulumi config set --secret exec-assistant:google_oauth_client_id clientid
pulumi config set --secret exec-assistant:google_oauth_client_secret clientsecret

```

### 4. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 5. Preview Changes

Preview what will be created:

```bash
pulumi preview
```

Expected resources:
- 1 KMS key + alias
- 3 DynamoDB tables (meetings, chat-sessions, action-items)
- 2 S3 buckets (documents, sessions)
- 2 S3 bucket public access blocks

### 6. Deploy Phase 1 (Storage Foundation)

Deploy the Phase 1 infrastructure (KMS, DynamoDB, S3):

```bash
pulumi up
```

Review the changes and confirm with `yes`.

### 7. Deploy Phase 1.5 (Authentication & Chat UI)

Phase 1.5 adds authentication Lambda functions, API Gateway, and a web-based chat interface.

#### Prerequisites for Phase 1.5

1. **Google OAuth Credentials**:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select existing project
   - Enable Google+ API
   - Go to "Credentials" → "Create Credentials" → "OAuth 2.0 Client ID"
   - Application type: "Web application"
   - Add authorized redirect URI: `https://YOUR_API_GATEWAY_URL/auth/callback` (you'll update this after first deploy)
   - Save the Client ID and Client Secret

2. **JWT Secret Key**:
   - Generate a secure random key:
   ```bash
   openssl rand -base64 32
   ```

#### Phase 1.5 Configuration

Set the required configuration values:

```bash
# Enable Phase 1.5 deployment
pulumi config set exec-assistant:enable_phase_1_5 true

# Set Google OAuth credentials
pulumi config set --secret exec-assistant:google_oauth_client_id YOUR_CLIENT_ID
pulumi config set --secret exec-assistant:google_oauth_client_secret YOUR_CLIENT_SECRET

# Generate and set JWT secret key
JWT_SECRET=$(openssl rand -base64 32)
pulumi config set --secret exec-assistant:jwt_secret_key "$JWT_SECRET"

# Set temporary redirect URI (will update after API Gateway is created)
pulumi config set exec-assistant:google_oauth_redirect_uri https://placeholder.com/auth/callback
pulumi config set exec-assistant:frontend_url https://placeholder.com
```

#### Deploy Phase 1.5

```bash
pulumi up
```

After deployment, you'll get outputs including:
- `api_endpoint`: Your API Gateway endpoint URL
- `ui_website_url`: Your S3-hosted UI URL

#### Update OAuth Redirect URI

After getting the `api_endpoint` from Pulumi outputs:

1. **Update Google OAuth settings**:
   - Go back to Google Cloud Console → Credentials
   - Edit your OAuth 2.0 Client ID
   - Add authorized redirect URI: `https://YOUR_API_GATEWAY_ID.execute-api.REGION.amazonaws.com/auth/callback`

2. **Update Pulumi config**:
   ```bash
   # Get the API endpoint from Pulumi output
   API_ENDPOINT=$(pulumi stack output api_endpoint)

   # Update config
   pulumi config set exec-assistant:google_oauth_redirect_uri "${API_ENDPOINT}/auth/callback"
   pulumi config set exec-assistant:frontend_url "$(pulumi stack output ui_website_url)"

   # Redeploy to update Lambda environment variables
   pulumi up
   ```

#### Test Phase 1.5

1. Open the UI URL from `pulumi stack output ui_website_url`
2. Click "Sign in with Google"
3. Authenticate with your Google account
4. You should be redirected back to the chat interface
5. Try sending a test message (agent integration coming in Phase 2!)

#### Phase 1.5 Resources Created

- **Lambda Functions**:
  - `exec-assistant-auth-{environment}`: Handles all authentication endpoints

- **API Gateway**:
  - HTTP API with routes:
    - `GET /auth/login`: Initiates Google OAuth flow
    - `GET /auth/callback`: Handles OAuth callback
    - `POST /auth/refresh`: Refreshes access tokens
    - `GET /auth/me`: Returns current user info

- **S3 Bucket**:
  - `exec-assistant-ui-{environment}`: Hosts static website with chat interface

- **IAM Roles & Policies**:
  - Lambda execution role with DynamoDB and KMS permissions

## Managing Stacks

### View Current Stack

```bash
pulumi stack
```

### List All Stacks

```bash
pulumi stack ls
```

### Switch Between Stacks

```bash
pulumi stack select staging
```

### Create Additional Stacks

```bash
# Create staging stack
pulumi stack init staging
pulumi config set aws:region us-east-1
pulumi config set exec-assistant:environment staging

# Create prod stack
pulumi stack init prod
pulumi config set aws:region us-east-1
pulumi config set exec-assistant:environment prod
```

## Stack Outputs

After deployment, you can view the created resources:

```bash
pulumi stack output
```

Example outputs:
- `kms_key_id`: KMS key for encryption
- `meetings_table_name`: DynamoDB meetings table name
- `documents_bucket_name`: S3 documents bucket name
- etc.

Use these outputs in your application configuration:

```bash
# Export to environment variables
export DYNAMODB_MEETINGS_TABLE=$(pulumi stack output meetings_table_name)
export S3_DOCUMENTS_BUCKET=$(pulumi stack output documents_bucket_name)
```

## Updating Infrastructure

When you modify the infrastructure code:

1. Preview changes:
   ```bash
   pulumi preview
   ```

2. Apply changes:
   ```bash
   pulumi up
   ```

## Destroying Infrastructure

**WARNING**: This will delete all resources and data!

```bash
# Preview what will be destroyed
pulumi destroy --preview

# Destroy the stack
pulumi destroy
```

## Troubleshooting

### Error: "No Pulumi.yaml project file found"

Make sure you're in the `infrastructure/` directory:
```bash
cd infrastructure
```

### Error: "Configuration key 'aws:region' ... should not define a default value"

This is fixed in the current `Pulumi.yaml`. Set the region manually:
```bash
pulumi config set aws:region us-east-1
```

### Error: "AWS credentials not found"

Configure AWS CLI:
```bash
aws configure
```

Or set environment variables:
```bash
export AWS_ACCESS_KEY_ID=your-key-id
export AWS_SECRET_ACCESS_KEY=your-secret-key
export AWS_DEFAULT_REGION=us-east-1
```

### Error: "Failed to create resource"

Check AWS permissions. Your IAM user/role needs:
- `dynamodb:*`
- `s3:*`
- `kms:*`
- `iam:GetRole`, `iam:PassRole` (for future Lambda functions)

### Preview Shows Large Changeset

If `pulumi preview` shows unexpected changes:
- Check if you switched stacks: `pulumi stack`
- Check configuration: `pulumi config`
- Review your code changes

## Cost Estimation

Estimated monthly costs (development):
- **DynamoDB**: ~$0 (on-demand, minimal usage)
- **S3**: ~$1-5 (depends on storage and requests)
- **KMS**: ~$1/month per key
- **Total**: ~$2-10/month for dev environment

Production costs will scale with usage but should stay under $50/month for typical use.

## Security Best Practices

1. **Secrets**: Always use `--secret` flag for sensitive values
   ```bash
   pulumi config set --secret exec-assistant:slack_bot_token xoxb-...
   ```

2. **State Files**: If using local backend, never commit `.pulumi/` directory

3. **IAM Roles**: Use least-privilege IAM policies (to be added in Phase 3)

4. **Encryption**: All resources use KMS encryption (already configured)

5. **VPC**: Consider adding VPC for network isolation (Phase 6+)

## Next Steps

After infrastructure is deployed:

1. **Update Application Config**: Copy stack outputs to `.env` file
2. **Test Connectivity**: Verify your app can connect to DynamoDB/S3
3. **Deploy Lambda Functions**: Phase 3 will add Lambda functions
4. **Set Up Monitoring**: Phase 6 will add CloudWatch dashboards

## File Structure

```
infrastructure/
├── README.md           # This file
├── Pulumi.yaml         # Pulumi project configuration
├── requirements.txt    # Python dependencies for Pulumi
├── __main__.py         # Main Pulumi program (orchestrates everything)
├── __init__.py         # Python package marker
└── storage.py          # DynamoDB and S3 resource definitions
```

## Resources

- [Pulumi Documentation](https://www.pulumi.com/docs/)
- [Pulumi AWS Provider](https://www.pulumi.com/registry/packages/aws/)
- [AWS DynamoDB Best Practices](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/best-practices.html)
- [AWS S3 Best Practices](https://docs.aws.amazon.com/AmazonS3/latest/userguide/security-best-practices.html)
