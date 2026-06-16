#!/usr/bin/env bash
set -euo pipefail

: "${API_URL:?Set API_URL from the CloudFormation output}"
: "${TOKEN:?Set TOKEN to a Cognito IdToken}"

response=$(curl -s -X POST "$API_URL/snippets" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"smoke","lang":"bash","content":"echo smoke"}')

echo "POST response: $response"
snippet_id=$(python -c 'import json,sys; print(json.load(sys.stdin)["snippetId"])' <<< "$response")

curl -fsS "$API_URL/snippets" -H "Authorization: Bearer $TOKEN"
echo

curl -fsS "$API_URL/snippets/$snippet_id" -H "Authorization: Bearer $TOKEN"
echo

curl -fsS -X DELETE "$API_URL/snippets/$snippet_id" -H "Authorization: Bearer $TOKEN" -o /dev/null

echo "Smoke test passed for snippet $snippet_id"
