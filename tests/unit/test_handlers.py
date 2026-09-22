"""
tests/unit/test_handlers.py
============================
Unit tests for all Lambda handlers using moto (AWS service mocks).

Run with:  pytest tests/unit/ -v

────────────────────────────────────────────────────────────────────────────────
WHAT TO BUILD — write one test class per Lambda, covering happy path + key errors
────────────────────────────────────────────────────────────────────────────────

SETUP PATTERN (use for every test class):
  @pytest.fixture(autouse=True)
  def aws_setup(self):
      with mock_aws():                        ← moto mock for S3, DynamoDB, etc.
          # Create the DynamoDB table
          ddb = boto3.resource("dynamodb", region_name="us-east-1")
          ddb.create_table(TableName="sfi-files-test", ...)
          # Create S3 buckets
          s3 = boto3.client("s3", region_name="us-east-1")
          s3.create_bucket(Bucket="test-uploads-bucket")
          yield

  Set env vars in conftest.py or setUp:
    os.environ["TABLE_NAME"] = "sfi-files-test"
    os.environ["UPLOADS_BUCKET"] = "test-uploads-bucket"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

MOCK JWT EVENT HELPER:
  def make_api_event(method, path, body=None, path_params=None, user_id="user-123"):
      return {
          "httpMethod": method,
          "path": path,
          "pathParameters": path_params or {},
          "queryStringParameters": {},
          "body": json.dumps(body) if body else None,
          "requestContext": {
              "authorizer": {
                  "claims": {"sub": user_id, "email": "test@example.com"}
              }
          }
      }

────────────────────────────────────────────────────────────────────────────────
TEST CASES TO WRITE:
────────────────────────────────────────────────────────────────────────────────

class TestGetUploadUrl:
  test_success_pdf():
    POST /files/upload with valid PDF body
    → 200, response has "uploadUrl" and "fileId"
    → DynamoDB has a PENDING record for the fileId

  test_success_image():
    Same but contentType = "image/jpeg"
    → 200

  test_missing_filename():
    POST with body missing "fileName"
    → 400, error code "VALIDATION_ERROR"

  test_file_too_large():
    POST with fileSize = 60_000_000 (> 50 MB limit)
    → 400

  test_invalid_content_type():
    POST with contentType = "application/exe"
    → 400


class TestListFiles:
  test_empty_list():
    GET /files with no files in DynamoDB
    → 200, {"items": [], "count": 0}

  test_returns_users_files_only():
    Insert 2 files for user-123, 1 file for user-456
    GET /files as user-123
    → 200, items has 2 entries, none from user-456

  test_pagination():
    Insert 25 files for user-123
    GET /files?limit=10
    → 200, 10 items, "lastKey" present
    GET /files?limit=10&lastKey=<previous lastKey>
    → 200, next 10 items


class TestGetFileResults:
  test_pending_file():
    Insert a PENDING file in DynamoDB
    GET /files/<fileId>
    → 200, processingStatus = "PENDING", no downloadUrl

  test_processed_file_has_download_url():
    Insert a PROCESSED file with extractedText, summary
    GET /files/<fileId>
    → 200, response has "downloadUrl" (pre-signed S3 URL), "summary", "extractedText"

  test_not_found():
    GET /files/nonexistent-id
    → 404

  test_wrong_user_cannot_access():
    Insert file owned by user-123
    GET as user-456
    → 404  (not 403 — don't reveal the file exists)


class TestDeleteFile:
  test_success():
    Insert file in DynamoDB, put object in S3
    DELETE /files/<fileId>
    → 200
    → DynamoDB record gone
    → S3 object deleted

  test_not_found():
    DELETE /files/nonexistent-id
    → 404

  test_wrong_user_cannot_delete():
    File owned by user-123, delete attempt by user-456
    → 404


class TestHousekeeping:
  test_deletes_stuck_pending():
    Insert PENDING file with uploadedAt 3 hours ago
    Call handler directly
    → DynamoDB record deleted

  test_keeps_recent_pending():
    Insert PENDING file with uploadedAt 30 minutes ago
    Call handler directly
    → DynamoDB record still there

  test_deletes_old_processed():
    Insert PROCESSED file with uploadedAt 31 days ago
    Call handler directly
    → DynamoDB record deleted, S3 objects deleted
"""

import json
import os
import pytest
import boto3
from moto import mock_aws

# TODO: implement the test cases described above
# Import your handlers:
# from backend.functions.get_upload_url.handler import handler as get_upload_url
# from backend.functions.list_files.handler import handler as list_files
# etc.
