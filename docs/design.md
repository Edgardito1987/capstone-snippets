# Design Decisions

## DynamoDB single-table model

Table keys:

| Entity | PK | SK | GSI1PK | GSI1SK | Purpose |
|---|---|---|---|---|---|
| Snippet metadata | `SNIP#<snippetId>` | `META` | `USER#<cognito-sub>` | `SNIP#<createdAt>#<snippetId>` | Direct lookup by id and Query-based list by user |
| Counter | `COUNTER#snippets` | `TOTAL` | n/a | n/a | SNS subscriber increments total upload count |

Access patterns:

1. Create snippet: `PutItem` metadata and `PutObject` raw body.
2. List current user's snippets: `Query` GSI1 where `GSI1PK = USER#<sub>`.
3. Get snippet URL: `GetItem` by `PK=SNIP#id, SK=META`, verify `ownerSub`, then return a 300-second S3 pre-signed URL.
4. Delete snippet: `GetItem`, verify `ownerSub`, then `DeleteObject` and `DeleteItem`.
5. Count uploads: SNS event triggers counter Lambda and executes `UpdateItem ADD count :one`.

## Security decisions

- API Gateway HTTP API uses a Cognito JWT authorizer.
- Snippet bodies are stored in S3 under `snippets/<cognito-sub>/<snippet-id>.txt`.
- The S3 bucket blocks public access, denies non-TLS requests, and uses SSE-KMS with a customer-managed KMS key.
- Lambda policies are scoped to the DynamoDB table/index, SNS topic, KMS key, and S3 object prefix used by the application.
- The application validates ownership after reading metadata, so one authenticated user cannot fetch or delete another user's snippet.
