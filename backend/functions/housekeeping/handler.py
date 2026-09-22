"""
backend/functions/housekeeping/handler.py
==========================================
Lambda: EventBridge Scheduler — nightly cleanup of stale/old records.

Triggered by: EventBridge Scheduler at 02:00 UTC daily (rate expression in CDK)
No HTTP response shape — return a plain dict summary.

────────────────────────────────────────────────────────────────────────────────
WHAT TO BUILD
────────────────────────────────────────────────────────────────────────────────

STEP 1 — Find stuck PENDING uploads (> 2 hours old)
  - Query the StatusIndex GSI: processingStatus = "PENDING"
  - Filter client-side: uploadedAt < (now - 2 hours)
  WHY: A file stuck in PENDING means the browser got the pre-signed URL but
       never completed the upload (or the user closed the tab). There is no S3
       object to clean up — just delete the orphan DynamoDB record.

STEP 2 — Delete stuck PENDING records
  - For each stuck item: delete_file_record(user_id, file_id)
  WHY: DynamoDB TTL (24h) would also catch these eventually, but TTL can lag
       up to 48 hours. Explicit cleanup keeps the table clean.

STEP 3 — Find old PROCESSED records (> 30 days)
  - Query the StatusIndex GSI: processingStatus = "PROCESSED"
  - Filter client-side: uploadedAt < (now - 30 days)
  WHY: Processed results (Textract JSON, Rekognition labels, Bedrock summaries)
       are stored in the DynamoDB item and in the processed S3 bucket.
       After 30 days these are unlikely to be needed — clean up both.

STEP 4 — Delete old PROCESSED files (S3 uploads + processed + DynamoDB)
  - For each old item:
      s3.delete_object(Bucket=UPLOADS_BUCKET, Key=item["s3Key"])
      s3.delete_object(Bucket=PROCESSED_BUCKET, Key=item["s3Key"])  ← best-effort
      delete_file_record(user_id, file_id)

STEP 5 — Return a summary dict (Lambda response, not HTTP)
  return {
    "deleted_pending": count_pending_deleted,
    "deleted_processed": count_processed_deleted,
    "timestamp": datetime.utcnow().isoformat(),
  }
  WHY: CloudWatch captures Lambda return values. The summary makes it easy to
       see housekeeping activity in logs without parsing through DynamoDB queries.

ENVIRONMENT VARIABLES:
  TABLE_NAME, UPLOADS_BUCKET, PROCESSED_BUCKET, STATUS_INDEX_NAME
"""

import os
from datetime import datetime, timedelta
import boto3
from dynamo_client import delete_file_record

UPLOADS_BUCKET    = os.environ["UPLOADS_BUCKET"]
PROCESSED_BUCKET  = os.environ["PROCESSED_BUCKET"]
STATUS_INDEX_NAME = os.environ.get("STATUS_INDEX_NAME", "StatusIndex")

# TODO: implement handler(event, context)
def handler(event, context):
    pass
