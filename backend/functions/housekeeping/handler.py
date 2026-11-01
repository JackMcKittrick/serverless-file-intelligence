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
from datetime import datetime, timedelta, timezone

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from dynamo_client import delete_file_record

TABLE_NAME = os.environ["TABLE_NAME"]
UPLOADS_BUCKET = os.environ["UPLOADS_BUCKET"]
PROCESSED_BUCKET = os.environ["PROCESSED_BUCKET"]
STATUS_INDEX_NAME = os.environ.get("STATUS_INDEX_NAME", "StatusIndex")

table = boto3.resource("dynamodb").Table(TABLE_NAME)
s3 = boto3.client("s3")

# this function retrieves every dynanoDB reocrd with a particular processing status 
def get_records(status):
    # created global secondary index elswhere with processing status as able to be queried by
    params = {
        "IndexName": STATUS_INDEX_NAME,
        "KeyConditionExpression": Key("processingStatus").eq(status),
    }
    # loop that continues until all query pages have been retrieved
    while True:
        response = table.query(**params)
        # remember that yield from returns records one at a time
        yield from response.get("Items", [])

        # no more pages of items
        if "LastEvaluatedKey" not in response:
            break

        params["ExclusiveStartKey"] = response["LastEvaluatedKey"]

# this function converts a stored upload timestame to a datetime compared to UTC cutoff tiems
def parse_uploaded_at(value):
    uploaded_at = datetime.fromisoformat(value.replace("Z", "+00:00"))

    if uploaded_at.tzinfo is None:
        uploaded_at = uploaded_at.replace(tzinfo=timezone.utc)

    return uploaded_at

# this function performs the cleanup and returns the deletion counts
def handler(event, context):
    now = datetime.now(timezone.utc)
    # pending records uploaded before this tiem qualify for deletion
    pending_cutoff = now - timedelta(hours=2)
    # processed records uploaded before this time for deletion
    processed_cutoff = now - timedelta(days=30)
    # counters for both
    deleted_pending = 0
    deleted_processed = 0

    # loops thru all pending status records
    for item in get_records("PENDING"):
        # gets upload time and sees if older than two hours then delete
        if parse_uploaded_at(item["uploadedAt"]) < pending_cutoff:
            delete_file_record(item["userId"], item["fileId"])
            deleted_pending += 1

    # loops thru all process status records
    for item in get_records("PROCESSED"):
        # gets upload time and sees if older than 30 days
        if parse_uploaded_at(item["uploadedAt"]) < processed_cutoff:
            # we do have lifecycle policies for these but still good to include
            # deletes original uploaded file
            s3.delete_object(
                Bucket=UPLOADS_BUCKET,
                Key=item["s3Key"],
            )
            # deletes processed file
            try:
                s3.delete_object(
                    Bucket=PROCESSED_BUCKET,
                    Key=item["s3Key"],
                )
            except ClientError:
                pass
            
            # deletes dynamoDB records 
            delete_file_record(item["userId"], item["fileId"])
            deleted_processed += 1

    # returns dictionary with counters for cloduwatch logs
    return {
        "deleted_pending": deleted_pending,
        "deleted_processed": deleted_processed,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
