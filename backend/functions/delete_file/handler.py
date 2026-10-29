"""
backend/functions/delete_file/handler.py
=========================================
Lambda: DELETE /files/{fileId} — delete a file from S3 and DynamoDB.

Path param: fileId

Response (200): {"message": "File deleted successfully"}

────────────────────────────────────────────────────────────────────────────────
WHAT TO BUILD
────────────────────────────────────────────────────────────────────────────────

STEP 1 — Extract userId and fileId
  - user_id = extract_user_id(event)
  - file_id = event["pathParameters"]["fileId"]

STEP 2 — Fetch the item to verify ownership and get the S3 key
  - item = get_file(user_id, file_id)   ← raises NotFoundError if missing
  WHY: You must fetch before deleting to get the s3Key (needed to delete from S3)
       AND to verify the authenticated user owns this file. Never delete by
       file_id alone — that allows any user to delete any file.

STEP 3 — Delete from S3 (uploads bucket, raw file)
  - s3.delete_object(Bucket=UPLOADS_BUCKET, Key=item["s3Key"])
  WHY: Delete the raw file first. If the DynamoDB delete then fails, the file is
       gone from S3 but the DynamoDB record is still there — housekeeping can clean
       that up. The reverse (DDB first) leaves an orphaned S3 object.

STEP 4 — Delete from S3 (processed bucket, results JSON) — best-effort
  - Try to delete the same key from PROCESSED_BUCKET
  - Catch and ignore NoSuchKey — the file may not have been processed yet
  WHY: Processed results must also be cleaned up to avoid paying for storage
       of results whose parent file no longer exists.

STEP 5 — Delete from DynamoDB
  - delete_file_record(user_id, file_id)

STEP 6 — Return success
  - return success({"message": "File deleted successfully"})

ENVIRONMENT VARIABLES:
  UPLOADS_BUCKET, PROCESSED_BUCKET
"""

import os
import boto3
from error_types import ValidationError, NotFoundError
from response_helpers import success, error, extract_user_id
from dynamo_client import get_file, delete_file_record

UPLOADS_BUCKET = os.environ["UPLOADS_BUCKET"]
PROCESSED_BUCKET = os.environ["PROCESSED_BUCKET"]

# TODO: implement handler(event, context)

# but the client before the handler because it lets lambda create the client once then reuse it for multiple requests
# if it were inside then a new object created for each request made by client
s3 = boto3.client("s3")

# this function verifies that user owns file then deletes original file and its results and its db record
def handler(event, context):

    user_id = extract_user_id(event)
    # the delete route is DELETE /files/{fileId}
    # which means files is fixed and {fileId} is the path parameter
    # so API Gateway treats only {fileId} as a path parameter
    # API Gateway uses the HTTP method and URL path to select a Lambda:
    # GET /files/abc123 will get results Lambda and DELETE /files/abc123 will get delete file Lambda etc
    # if user did PUT /files/abc123 it would be rejected because this method/route isn't configured in API gateway
    path_params = event.get("pathParameters") or {}
    file_id = path_params.get("fileId")
    # mind you above is same as file_id = event["pathParameters"]["fileId"] with better error handling

    # gets file informatino from dynamoDB
    item = get_file(user_id, file_id)
    s3_key = item["s3Key"]
    # uses the s3 key to delete the bucket with this api call
    s3.delete_object(Bucket=UPLOADS_BUCKET, Key=s3_key)

    # processed results might not exist yet so NoSuchKey is caught and function continues
    try:
        s3.delete_object(Bucket=PROCESSED_BUCKET, Key=s3_key)
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "NoSuchKey":
            raise
    # deletes from dynamoDB
    delete_file_record(user_id, file_id)

    return success({"message": "File deleted successfully"})
