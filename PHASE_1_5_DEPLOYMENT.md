# Phase 1.5 Deployment Guide

This guide walks you through deploying Phase 1.5 of the Executive Assistant system, which adds authentication and a web-based chat interface.

## What's Included in Phase 1.5

- **Authentication System**: Google OAuth 2.0 login with JWT tokens
- **API Gateway**: RESTful API endpoints for authentication
- **Lambda Functions**: Serverless authentication handlers
- **Chat UI**: Simple web interface for testing the system
- **User Management**: DynamoDB-backed user storage

## Prerequisites

Before deploying Phase 1.5, ensure you have:

1. ✅ **Phase 1 deployed**: Storage foundation (DynamoDB, S3, KMS)
2. ✅ **Google Cloud Project**: With OAuth credentials
3. ✅ **AWS CLI configured**: With appropriate permissions
4. ✅ **Pulumi CLI installed**: Version 3.x or later

## Step 1: Set Up Google OAuth

### Create OAuth 2.0 Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select or create a project
3. Navigate to **APIs & Services** → **Credentials**
4. Click **Create Credentials** → **OAuth 2.0 Client ID**
5. Configure consent screen if prompted:
   - User Type: External (for testing) or Internal (for organization)
   - Add required information (app name, user support email)
   - Add scopes: `openid`, `email`, `profile`
6. Create OAuth Client ID:
   - Application type: **Web application**
   - Name: `Executive Assistant`
   - Authorized redirect URIs: `https://placeholder.com/auth/callback` (temporary, will update later)
7. Save the **Client ID** and **Client Secret**

### Enable Required APIs

Make sure these APIs are enabled:
- Google+ API (for user info)
- Google Calendar API (for Phase 2+)

## Step 2: Generate JWT Secret

Generate a secure random key for JWT signing:

```bash
openssl rand -base64 32
```

Save this key securely - you'll need it for configuration.

## Step 3: Configure Pulumi

Navigate to the infrastructure directory:

```bash
cd infrastructure
```

Set Phase 1.5 configuration:

```bash
# Enable Phase 1.5
pulumi config set exec-assistant:enable_phase_1_5 true

# Google OAuth credentials
pulumi config set --secret exec-assistant:google_oauth_client_id YOUR_CLIENT_ID_HERE
pulumi config set --secret exec-assistant:google_oauth_client_secret YOUR_CLIENT_SECRET_HERE

# JWT secret
JWT_SECRET=$(openssl rand -base64 32)
pulumi config set --secret exec-assistant:jwt_secret_key "$JWT_SECRET"

# Temporary URLs (will update after deployment)
pulumi config set exec-assistant:google_oauth_redirect_uri https://placeholder.com/auth/callback
pulumi config set exec-assistant:frontend_url https://placeholder.com
```

Verify configuration:

```bash
pulumi config
```

## Step 4: Deploy Infrastructure

Preview what will be created:

```bash
pulumi preview
```

Expected new resources:
- 1 Lambda function (auth handler)
- 1 IAM role + policies
- 1 API Gateway HTTP API
- 1 S3 bucket (UI hosting)
- 3 S3 objects (UI files)
- 1 CloudWatch log group

Deploy:

```bash
pulumi up
```

Type `yes` to confirm.

## Step 5: Update OAuth Redirect URI

After deployment, get the API endpoint:

```bash
pulumi stack output api_endpoint
```

Example output: `https://abc123.execute-api.us-east-1.amazonaws.com`

### Update Google OAuth

1. Go back to [Google Cloud Console](https://console.cloud.google.com/) → Credentials
2. Click on your OAuth 2.0 Client ID
3. Under **Authorized redirect URIs**, add:
   ```
   https://YOUR_API_ID.execute-api.REGION.amazonaws.com/auth/callback
   ```
4. Click **Save**

### Update Pulumi Config

```bash
# Get outputs
API_ENDPOINT=$(pulumi stack output api_endpoint)
UI_URL=$(pulumi stack output ui_website_url)

# Update config
pulumi config set exec-assistant:google_oauth_redirect_uri "${API_ENDPOINT}/auth/callback"
pulumi config set exec-assistant:frontend_url "http://${UI_URL}"

# Redeploy to update Lambda environment variables
pulumi up
```

## Step 6: Test the Deployment

### Open the UI

```bash
# Get UI URL
pulumi stack output ui_website_url

# Open in browser (macOS)
open "http://$(pulumi stack output ui_website_url)"

# Or manually copy the URL and paste in browser
```

### Test Authentication Flow

1. Click **"Sign in with Google"** button
2. You'll be redirected to Google login
3. Authenticate with your Google account
4. Grant permissions when prompted
5. You should be redirected back to the chat interface
6. Verify your name, email, and avatar appear in the UI

### Test the API Directly

```bash
# Get your access token from localStorage in browser dev tools
# Then test the /auth/me endpoint

API_ENDPOINT=$(pulumi stack output api_endpoint)
ACCESS_TOKEN="your-token-here"

curl "${API_ENDPOINT}/auth/me" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}"
```

## Step 7: Verify Resources

Check that all resources were created:

```bash
# List all stack outputs
pulumi stack output

# Check Lambda function
aws lambda get-function --function-name exec-assistant-auth-dev

# Check API Gateway
API_ID=$(pulumi stack output api_id)
aws apigatewayv2 get-api --api-id $API_ID

# Check S3 bucket
UI_BUCKET=$(pulumi stack output ui_bucket_name)
aws s3 ls s3://$UI_BUCKET/

# Check DynamoDB users table
aws dynamodb describe-table --table-name exec-assistant-users-dev
```

## Troubleshooting

### Issue: "Redirect URI mismatch"

**Symptom**: Error when clicking "Sign in with Google"

**Solution**:
- Verify the redirect URI in Google Cloud Console matches exactly: `https://YOUR_API_ID.execute-api.REGION.amazonaws.com/auth/callback`
- Check that you updated the Pulumi config and redeployed

### Issue: "Invalid or expired token"

**Symptom**: Can't access /auth/me endpoint

**Solution**:
- Clear browser localStorage
- Log out and log back in
- Verify JWT_SECRET_KEY is set correctly in Pulumi config

### Issue: Lambda function errors

**Symptom**: 500 errors from API

**Solution**:
```bash
# Check Lambda logs
aws logs tail /aws/lambda/exec-assistant-auth-dev --follow

# Common issues:
# - Missing environment variables
# - DynamoDB permissions
# - KMS encryption permissions
```

### Issue: CORS errors in browser

**Symptom**: Browser console shows CORS policy errors

**Solution**:
- Verify FRONTEND_URL matches the S3 website URL
- Check API Gateway CORS configuration
- Redeploy after updating config

## Cost Estimation

Phase 1.5 adds minimal costs:

- **Lambda**: ~$0 (first 1M requests free)
- **API Gateway**: ~$0 (first 1M requests ~$1)
- **S3 UI Hosting**: ~$0.50/month
- **CloudWatch Logs**: ~$0.50/month

**Total**: ~$1-2/month for dev environment

## Next Steps

After Phase 1.5 is deployed:

1. **Test authentication** with your Google account
2. **Invite team members** to test the UI
3. **Prepare for Phase 2**: First agent deployment (Meeting Coordinator)
4. **Review security**: Consider adding VPC, WAF, or other security measures for production

## Security Considerations

For **production deployment**, consider:

1. **Custom Domain**: Use CloudFront + Route53 instead of S3 website hosting
2. **HTTPS**: S3 website hosting doesn't support HTTPS natively
3. **OAuth Scopes**: Review and minimize requested scopes
4. **JWT Expiration**: Consider shorter access token lifetime
5. **Rate Limiting**: Add API Gateway throttling
6. **Monitoring**: Set up CloudWatch alarms for errors
7. **Audit Logging**: Enable CloudTrail for API Gateway

## Clean Up

To remove Phase 1.5 resources:

```bash
# Disable Phase 1.5
pulumi config set exec-assistant:enable_phase_1_5 false

# Destroy Phase 1.5 resources
pulumi up
```

Or to destroy everything:

```bash
pulumi destroy
```

## Support

If you encounter issues:

1. Check the [infrastructure README](infrastructure/README.md)
2. Review [Pulumi AWS documentation](https://www.pulumi.com/registry/packages/aws/)
3. Check AWS CloudWatch logs for Lambda errors
4. Open an issue in the project repository

---

**Congratulations!** You've successfully deployed Phase 1.5 of the Executive Assistant system. You now have a working authentication system and chat UI ready for Phase 2 agent integration.
