import json
import os
from typing import Any, Dict

import boto3
from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.metrics import MetricUnit

logger = Logger()
tracer = Tracer()
metrics = Metrics(namespace="CapstoneSnippets")

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["TABLE_NAME"])


@logger.inject_lambda_context
@tracer.capture_lambda_handler
def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    processed = 0
    for record in event.get("Records", []):
        message = json.loads(record.get("Sns", {}).get("Message", "{}"))
        if message.get("eventType") != "new-snippet":
            continue
        table.update_item(
            Key={"PK": "COUNTER#snippets", "SK": "TOTAL"},
            UpdateExpression="ADD #count :one SET #type = :type",
            ExpressionAttributeNames={"#count": "count", "#type": "type"},
            ExpressionAttributeValues={":one": 1, ":type": "counter"},
        )
        processed += 1

    metrics.add_metric(name="SnippetEventsCounted", unit=MetricUnit.Count, value=processed)
    logger.info("counter processed SNS records", extra={"processed": processed})
    return {"processed": processed}
# force redeploy Tue Jun 16 02:37:15 PM UTC 2026
# direct repair Tue Jun 16 02:41:35 PM UTC 2026
