"""
backend/functions/list_files/handler.py
========================================
Lambda: GET /files — list all files for the authenticated user.

Query params (optional):
  ?limit=20          default 20, max 100
  ?lastKey=<token>   base64-encoded DynamoDB pagination cursor from previous response

Response (200):
  {"items": [...], "count": 20, "lastKey": "<token or omitted>"}

Each item in "items":
  {"fileId", "fileName", "contentType", "fileSize", "processingStatus", "uploadedAt"}

────────────────────────────────────────────────────────────────────────────────
WHAT TO BUILD
────────────────────────────────────────────────────────────────────────────────

STEP 1 — Extract userId and pagination params
  - user_id = extract_user_id(event)
  - params = event.get("queryStringParameters") or {}
  - limit = min(int(params.get("limit", 20)), 100)
  - Decode lastKey: base64.b64decode(params["lastKey"]) → json.loads → dict
    (handle missing/invalid key gracefully — default to None)
  WHY: Capping limit at 100 prevents a single call from scanning the whole table.

STEP 2 — Query DynamoDB
  - items, next_key = list_user_files(user_id, limit, last_key)
  WHY: list_user_files() queries PK=USER#<id> AND SK begins_with "FILE#"
       which returns only file records, not WebSocket connection records.

STEP 3 — Strip internal fields before returning
  - For each item, keep only: fileId, fileName, contentType, fileSize,
    processingStatus, uploadedAt, updatedAt (omit PK, SK, s3Key, userId, ttl)
  WHY: PK/SK are DynamoDB implementation details; s3Key is internal; userId
       is already known to the caller.

STEP 4 — Encode nextKey for the response
  - If next_key: base64.b64encode(json.dumps(next_key).encode()).decode()
  - Pass as lastKey to paginated()
  WHY: DynamoDB LastEvaluatedKey is a dict — clients shouldn't parse it.
       Base64 encoding makes it opaque and safe to pass as a query param.

STEP 5 — Return paginated response
  - return paginated(items, last_key=encoded_next_key)
"""

import json
import os
import base64
from error_types import ValidationError
from response_helpers import success, error, paginated, extract_user_id
from dynamo_client import list_user_files

# TODO: implement handler(event, context)
def handler(event, context):
    pass
