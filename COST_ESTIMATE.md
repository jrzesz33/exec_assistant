# Cost Estimate - Executive Assistant System

## Current Deployment (Phase 1.5)

### Monthly Cost Breakdown for 2 Users (Low Usage)

Assuming **low usage**: ~100 requests/month per user (200 total)

| Service | Configuration | Monthly Cost | Notes |
|---------|--------------|--------------|-------|
| **DynamoDB** | 4 tables, on-demand | **$0** | Free tier: 25GB storage, 25 WCU, 25 RCU |
| **S3** | 3 buckets (~100MB total) | **$0.02** | $0.023/GB storage + minimal requests |
| **KMS** | 1 key | **$1.00** | $1/month per key |
| **Lambda** | Auth function, 200 invocations | **$0** | Free tier: 1M requests, 400K GB-seconds |
| **API Gateway** | HTTP API, 200 requests | **$0** | Free tier: 1M requests |
| **CloudWatch Logs** | 7-day retention, ~50MB | **$0.01** | $0.50/GB ingested |
| **Data Transfer** | Minimal outbound | **$0.02** | First 100GB free/month |
| | | |
| **TOTAL** | | **~$1.05/month** | |

### Most Expensive Service

**KMS (AWS Key Management Service)** is currently the most expensive at **$1/month**.

**Cost Optimization Options:**
1. **Use AWS-managed keys instead of customer-managed KMS keys**
   - Savings: $1/month
   - Trade-off: Less control over key rotation and access policies
   - Recommendation: For dev environment, use AWS-managed keys

2. **Consolidate to single KMS key**
   - Currently using 1 key for all encryption
   - Already optimized ✓

3. **Reduce CloudWatch log retention**
   - Currently: 7 days
   - Could reduce to: 1-3 days for dev
   - Savings: Negligible (~$0.01)

### Cost at Scale

**10 Users (1,000 requests/month):**
- Same cost: **~$1.05/month** (all within free tier)

**100 Users (10,000 requests/month):**
- DynamoDB: $0 (still free tier)
- S3: $0.05
- Lambda: $0 (free tier)
- API Gateway: $0.01
- Other: $1.03
- **Total: ~$1.10/month**

**Production (500 users, 50K requests/month):**
- DynamoDB: $2.50 (on-demand pricing)
- S3: $0.50
- Lambda: $0.20
- API Gateway: $0.05
- KMS: $1.00
- CloudWatch: $1.00
- Data Transfer: $2.00
- **Total: ~$7.25/month**

## Future Phase Costs

### Phase 2: First Agent (Meeting Coordinator)
- **Amazon Bedrock**: Claude Sonnet 3.5
  - Input: $3 per 1M tokens
  - Output: $15 per 1M tokens
  - Estimated: **$5-10/month** for 2 users (10 agent conversations)
- **S3 (Session Storage)**: +$0.02
- **Total Phase 2 increase**: **~$5-10/month**

### Phase 3-7: Full System
- **Bedrock (9 agents)**: $25-50/month for 2 users
- **Step Functions**: $0.50
- **EventBridge**: $0.10
- **Additional Lambda**: $0.20
- **Total Full System**: **~$27-52/month** for 2 users

## Cost Reduction Recommendations

### For Development (2 users, low usage)

**Option 1: Use AWS-Managed Keys (Recommended)**
```python
# In storage.py, change:
server_side_encryption=aws.dynamodb.TableServerSideEncryptionArgs(
    enabled=True,
    # Remove kms_key_arn to use AWS-managed keys
),
```
**Savings: $1/month (reduce to ~$0.05/month)**

**Option 2: Reduce Log Retention**
```python
# In api.py:
retention_in_days=1,  # Instead of 7
```
**Savings: $0.01/month**

**Option 3: Use Free Tier Only**
- Current setup already optimized for free tier
- All compute/storage within limits ✓

### For Production

1. **Use Reserved Capacity** for DynamoDB (if consistent usage)
   - Savings: 30-50% on DynamoDB costs
2. **S3 Intelligent-Tiering** for documents
   - Savings: 20-30% on storage
3. **CloudWatch Logs Insights** instead of storing all logs
   - Savings: 40-60% on logging costs

## Summary

**Current Cost (2 users, Phase 1.5)**: **$1.05/month**
- Most expensive: KMS at $1/month
- Optimization: Use AWS-managed keys → **$0.05/month**

**With First Agent (Phase 2)**: **$6-11/month**
- Bedrock AI costs dominate

**Full System (Phase 7)**: **$27-52/month**
- Primarily Bedrock API usage
- Scales linearly with usage

**Recommendation**: For development with 2 users, switch to AWS-managed encryption keys to reduce costs to ~$0.05/month.
