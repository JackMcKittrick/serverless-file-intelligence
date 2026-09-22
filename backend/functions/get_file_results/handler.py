"""
backend/functions/get_file_results/handler.py
==============================================
Lambda: GET /files/{fileId} — return a single file record plus its AI results.

Path param: fileId (from event["pathParameters"]["fileId"])

Response (200):
  {
    "fileId", "fileName", "contentType", "fileSize",
    "processingStatus",   ← PENDING | PROCESSING | PROCESSED | FAILED
    "uploadedAt", "updatedAt",
    "extractedText",      ← present if PROCESSED and document
    "summary",            ← present if PROCESSED
    "labels",             ← present if PROCESSED and image
    "entities",           ← present if PROCESSED
    "downloadUrl",        ← pre-signed GET URL (60-second TTL), only if PROCESSED
  }

────────────────────────────────────────────────────────────────────────────────
WHAT TO BUILD
────────────────────────────────────────────────────────────────────────────────

STEP 1 — Extract userId and fileId
  - user_id = extract_user_id(event)
  - file_id = event["pathParameters"]["fileId"]
  - Raise ValidationError if file_id is missing
  WHY: fileId comes from the URL path, not the body.

STEP 2 — Fetch the file record from DynamoDB
  - item = get_file(user_id, file_id)
    ↳ raises NotFoundError automatically if not found
  WHY: get_file() also verifies the PK matches the authenticated user,
       so User A cannot read User B's files.

STEP 3 — Optionally generate a download URL
  - Only if item["processingStatus"] == "PROCESSED":
    url = s3.generate_presigned_url("get_object",
              Params={"Bucket": PROCESSED_BUCKET, "Key": item["s3Key"]},
              ExpiresIn=60)
    item["downloadUrl"] = url
  WHY: 60 seconds is enough for a redirect; the processed results file
       is stored separately in the processed bucket, not the uploads bucket.
  NOTE: The s3Key stored in DynamoDB points to the UPLOADS bucket for raw files.
        The processed results (JSON from Textract/Rekognition) are in PROCESSED_BUCKET
        at the same key path. Generate the GET URL against PROCESSED_BUCKET.

STEP 4 — Strip internal DynamoDB fields and return
  - Remove PK, SK, userId, ttl from item before returning
  - return success(item)

ENVIRONMENT VARIABLES:
  PROCESSED_BUCKET  — name of the Terraform-managed processed-results bucket
  TABLE_NAME        — set automatically by dynamo_client
"""

import os
import boto3
from error_types import ValidationError, NotFoundError, AuthorizationError
from response_helpers import success, error, extract_user_id
from dynamo_client import get_file

PROCESSED_BUCKET = os.environ["PROCESSED_BUCKET"]

# TODO: implement handler(event, context)
def handler(event, context):
    pass
