"""
backend/layers/shared/python/dynamo_client.py
=============================================
Singleton DynamoDB resource + typed helper functions shared by every Lambda.

Import in handlers:
  from dynamo_client import get_file, list_user_files, put_file, update_file_status

────────────────────────────────────────────────────────────────────────────────
WHAT TO BUILD
────────────────────────────────────────────────────────────────────────────────

STEP 1 — Module-level setup
  - Read TABLE_NAME from os.environ["TABLE_NAME"]
  - Create a module-level boto3 DynamoDB resource (not client) — reuse across
    Lambda invocations: `_dynamodb = boto3.resource("dynamodb")`
  - Create `_table = _dynamodb.Table(TABLE_NAME)` at module level
  WHY: boto3 resource initialization takes ~50ms. Keeping it at module level
       means it is created once per container, not once per invocation.

STEP 2 — Key helpers (lambdas or functions)
  PK(user_id)  → f"USER#{user_id}"
  SK_FILE(id)  → f"FILE#{id}"
  SK_CONN(id)  → f"CONN#{id}"
  WHY: Centralizing key construction prevents typos and makes key patterns
       immediately obvious when reading any DynamoDB call.

STEP 3 — get_file(user_id: str, file_id: str) → dict
  Call _table.get_item(Key={"PK": PK(user_id), "SK": SK_FILE(file_id)})
  If Item is missing, raise NotFoundError(f"File {file_id} not found")
  Return item["Item"]
  WHY: All read handlers need a single function that either returns a complete
       file record or raises NotFoundError — no nested if-blocks in handlers.

STEP 4 — list_user_files(user_id: str, limit: int = 20, last_key=None) → tuple[list, dict|None]
  Query with KeyConditionExpression: PK = PK(user_id) and SK begins_with "FILE#"
  Pass ExclusiveStartKey=last_key if provided, Limit=limit
  Return (items, response.get("LastEvaluatedKey"))
  WHY: Returns (items, next_cursor) so the handler can build a paginated response.

STEP 5 — put_file(item: dict) → None
  Call _table.put_item(Item=item)
  The caller is responsible for building the full item dict including PK, SK,
  fileId, userId, fileName, contentType, fileSize, processingStatus, uploadedAt.
  WHY: A thin wrapper that keeps the raw boto3 call out of handler code.

STEP 6 — update_file_status(user_id, file_id, status, **extra_attrs) → None
  Build an UpdateExpression that sets processingStatus=status, updatedAt=now,
  and any extra_attrs (e.g. extractedText, summary, labels).
  Use ConditionExpression to ensure the item exists (attribute_exists(PK)).
  WHY: Step Functions uses this to write back Textract/Rekognition results
       and status changes without overwriting the entire item.

STEP 7 — delete_file_record(user_id: str, file_id: str) → None
  Call _table.delete_item(Key={"PK": PK(user_id), "SK": SK_FILE(file_id)})
  WHY: Separating the DynamoDB delete from the S3 delete makes both operations
       independently testable.
"""

import os
import boto3
# TODO: implement all helpers described above
