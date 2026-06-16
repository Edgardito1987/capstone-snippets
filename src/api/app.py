import base64
import json
import os
import time
import uuid
from decimal import Decimal
from typing import Any, Dict, Optional

import boto3
from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.metrics import MetricUnit
from botocore.exceptions import ClientError

logger = Logger()
tracer = Tracer()
metrics = Metrics(namespace="CapstoneSnippets")

dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")
sns = boto3.client("sns")

TABLE_NAME = os.environ["TABLE_NAME"]
BUCKET_NAME = os.environ["BUCKET_NAME"]
TOPIC_ARN = os.environ["TOPIC_ARN"]

table = dynamodb.Table(TABLE_NAME)


def _json_response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {
            "content-type": "application/json",
            "cache-control": "no-store",
        },
        "body": json.dumps(body, default=str),
    }


def _empty_response(status_code: int = 204) -> Dict[str, Any]:
    return {"statusCode": status_code, "headers": {}, "body": ""}


def _claims(event: Dict[str, Any]) -> Dict[str, Any]:
    return (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("jwt", {})
        .get("claims", {})
    )


def _current_user_sub(event: Dict[str, Any]) -> str:
    sub = _claims(event).get("sub")
    if not sub:
        raise PermissionError("Missing Cognito sub claim")
    return sub


def _request_json(event: Dict[str, Any]) -> Dict[str, Any]:
    raw_body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw_body = base64.b64decode(raw_body).decode("utf-8")
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise ValueError("Request body must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object")
    return payload


def _route(event: Dict[str, Any]) -> tuple[str, str, Optional[str]]:
    method = event.get("requestContext", {}).get("http", {}).get("method", "")
    path = event.get("rawPath", "")
    snippet_id = None
    if path.startswith("/snippets/"):
        snippet_id = path.rsplit("/", 1)[-1]
    return method.upper(), path, snippet_id


@tracer.capture_method
def create_snippet(event: Dict[str, Any]) -> Dict[str, Any]:
    user_sub = _current_user_sub(event)
    payload = _request_json(event)

    content = payload.get("content")
    if not isinstance(content, str) or not content.strip():
        return _json_response(400, {"message": "content is required"})

    title = str(payload.get("title") or "untitled")[:120]
    lang = str(payload.get("lang") or "text")[:40]
    snippet_id = str(uuid.uuid4())
    created_at = int(time.time())
    encoded = content.encode("utf-8")
    s3_key = f"snippets/{user_sub}/{snippet_id}.txt"

    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=s3_key,
        Body=encoded,
        ContentType="text/plain; charset=utf-8",
        Metadata={"snippet-id": snippet_id, "owner-sub": user_sub},
    )

    item = {
        "PK": f"SNIP#{snippet_id}",
        "SK": "META",
        "GSI1PK": f"USER#{user_sub}",
        "GSI1SK": f"SNIP#{created_at}#{snippet_id}",
        "type": "snippet",
        "snippetId": snippet_id,
        "ownerSub": user_sub,
        "title": title,
        "lang": lang,
        "size": Decimal(len(encoded)),
        "s3Key": s3_key,
        "createdAt": Decimal(created_at),
    }
    table.put_item(Item=item)

    sns.publish(
        TopicArn=TOPIC_ARN,
        Subject="new-snippet",
        Message=json.dumps({"eventType": "new-snippet", "snippetId": snippet_id, "ownerSub": user_sub}),
    )

    metrics.add_metric(name="SnippetCreated", unit=MetricUnit.Count, value=1)
    return _json_response(201, {"snippetId": snippet_id, "s3Key": s3_key})


@tracer.capture_method
def list_snippets(event: Dict[str, Any]) -> Dict[str, Any]:
    user_sub = _current_user_sub(event)
    result = table.query(
        IndexName="GSI1",
        KeyConditionExpression="GSI1PK = :pk",
        ExpressionAttributeValues={":pk": f"USER#{user_sub}"},
        ScanIndexForward=False,
        Limit=50,
    )
    items = result.get("Items", [])
    snippets = [
        {
            "snippetId": item["snippetId"],
            "title": item.get("title"),
            "lang": item.get("lang"),
            "size": int(item.get("size", 0)),
            "createdAt": int(item.get("createdAt", 0)),
        }
        for item in items
    ]
    return _json_response(200, {"items": snippets})


@tracer.capture_method
def get_snippet_url(event: Dict[str, Any], snippet_id: str) -> Dict[str, Any]:
    user_sub = _current_user_sub(event)
    item = _get_authorized_snippet(snippet_id, user_sub)
    if not item:
        return _json_response(404, {"message": "snippet not found"})

    url = s3.generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": BUCKET_NAME, "Key": item["s3Key"]},
        ExpiresIn=300,
    )
    return _json_response(200, {"url": url, "expiresIn": 300})


@tracer.capture_method
def delete_snippet(event: Dict[str, Any], snippet_id: str) -> Dict[str, Any]:
    user_sub = _current_user_sub(event)
    item = _get_authorized_snippet(snippet_id, user_sub)
    if not item:
        return _json_response(404, {"message": "snippet not found"})

    s3.delete_object(Bucket=BUCKET_NAME, Key=item["s3Key"])
    table.delete_item(Key={"PK": f"SNIP#{snippet_id}", "SK": "META"})
    metrics.add_metric(name="SnippetDeleted", unit=MetricUnit.Count, value=1)
    return _empty_response(204)


def _get_authorized_snippet(snippet_id: str, user_sub: str) -> Optional[Dict[str, Any]]:
    result = table.get_item(Key={"PK": f"SNIP#{snippet_id}", "SK": "META"})
    item = result.get("Item")
    if not item or item.get("ownerSub") != user_sub:
        return None
    return item


@logger.inject_lambda_context
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    logger.info("request received", extra={"event": event})
    try:
        method, path, snippet_id = _route(event)
        if method == "POST" and path == "/snippets":
            return create_snippet(event)
        if method == "GET" and path == "/snippets":
            return list_snippets(event)
        if method == "GET" and snippet_id:
            return get_snippet_url(event, snippet_id)
        if method == "DELETE" and snippet_id:
            return delete_snippet(event, snippet_id)
        return _json_response(404, {"message": "route not found"})
    except PermissionError as exc:
        logger.warning("unauthorized request", extra={"error": str(exc)})
        return _json_response(401, {"message": "unauthorized"})
    except ValueError as exc:
        logger.warning("bad request", extra={"error": str(exc)})
        return _json_response(400, {"message": str(exc)})
    except ClientError as exc:
        logger.exception("aws client error")
        return _json_response(500, {"message": "aws client error", "code": exc.response.get("Error", {}).get("Code")})
    except Exception:
        logger.exception("unhandled error")
        raise
# force redeploy Tue Jun 16 02:37:15 PM UTC 2026
# direct repair Tue Jun 16 02:41:35 PM UTC 2026
