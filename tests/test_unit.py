import importlib
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("AWS_DEFAULT_REGION", "eu-west-1")
os.environ.setdefault("AWS_EC2_METADATA_DISABLED", "true")
os.environ.setdefault("TABLE_NAME", "unit-test-table")
os.environ.setdefault("BUCKET_NAME", "unit-test-bucket")
os.environ.setdefault("TOPIC_ARN", "arn:aws:sns:eu-west-1:123456789012:unit-test")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "api"))

app = importlib.import_module("app")


def test_json_response_shape():
    response = app._json_response(200, {"ok": True})
    assert response["statusCode"] == 200
    assert response["headers"]["content-type"] == "application/json"
    assert json.loads(response["body"]) == {"ok": True}


def test_current_user_sub_from_http_api_jwt_claims():
    event = {
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": "user-123"
                    }
                }
            }
        }
    }
    assert app._current_user_sub(event) == "user-123"


def test_route_parsing_for_snippet_id():
    event = {
        "rawPath": "/snippets/abc-123",
        "requestContext": {"http": {"method": "GET"}},
    }
    assert app._route(event) == ("GET", "/snippets/abc-123", "abc-123")
