# Runbook

## Symptom: latency spike on `POST /snippets`

1. Open CloudWatch dashboard `capstone-snippets` and check HTTP API p95 latency first.
2. Check API Lambda p95 duration and errors.
3. Use X-Ray service map to see whether latency is coming from Lambda execution, DynamoDB `PutItem`, S3 `PutObject`, or SNS `Publish`.
4. Open Lambda Logs Insights and filter for the request id from API Gateway access logs.
5. Check DynamoDB `ThrottledRequests` and consumed write capacity. The table uses on-demand capacity, so sustained throttling usually points to hot keys or account-level limits.
6. If S3 latency dominates, validate object size and regional AWS health.

## Symptom: 5xx error storm

1. Confirm the failing route in API Gateway access logs.
2. Check API Lambda `Errors` and recent deployment time.
3. If this happened during canary deployment, confirm the CloudWatch alarm state and CodeDeploy deployment status.
4. Manual rollback option:

```bash
aws lambda list-versions-by-function --function-name capstone-snippets-api
aws lambda update-alias \
  --function-name capstone-snippets-api \
  --name live \
  --function-version <previous-good-version>
```

5. If the stack is unstable after a failed deployment, redeploy the previous known-good commit:

```bash
git checkout <previous-good-commit>
sam build
sam deploy --parameter-overrides EnableCanaryDeploy=true
```

## Symptom: cost spiked yesterday

1. Check CloudWatch dashboard for API request count, Lambda invocations/duration, and DynamoDB capacity.
2. In Cost Explorer, group by service for the date of the spike: Lambda, API Gateway, DynamoDB, S3, CloudWatch, KMS, SNS.
3. Check S3 bucket size and object count:

```bash
aws s3 ls s3://<bucket-name>/snippets/ --recursive --summarize
```

4. Check CloudWatch Logs ingestion and retention. All created log groups should be set to 30 days.
5. Check for test loops or unauthenticated retry storms in API Gateway access logs.

## Canary rollback test

1. Deploy a healthy version with canary enabled.
2. Introduce a temporary exception in `src/api/app.py`, for example inside `lambda_handler`.
3. Deploy again with `EnableCanaryDeploy=true`.
4. Trigger the route until the Lambda error alarm enters `ALARM`.
5. Confirm CodeDeploy rolls the alias back to the previous Lambda version.
6. Revert the broken commit and redeploy.
