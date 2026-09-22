"""
tests/integration/test_pipeline.py
====================================
Integration tests — test the full processing pipeline end-to-end.

IMPORTANT: These tests require real AWS credentials and a deployed dev environment.
           They are NOT run in CI on every push — run manually after a deploy:
             pytest tests/integration/ -v --timeout=120

Set these environment variables before running:
  API_URL       = "<your deployed API Gateway URL>/dev"
  WS_URL        = "<your deployed WebSocket API URL>/dev"
  TEST_EMAIL    = "your-test-user@example.com"
  TEST_PASSWORD = "YourTestPassword123!"
  (The test user must already exist in Cognito — create via AWS console or CLI)

────────────────────────────────────────────────────────────────────────────────
WHAT TO BUILD
────────────────────────────────────────────────────────────────────────────────

SETUP:
  @pytest.fixture(scope="module")
  def auth_token():
      Authenticate against real Cognito using USER_PASSWORD_AUTH
      (boto3 cognito_idp.initiate_auth)
      Return the access token for use in API calls

  @pytest.fixture
  def api(auth_token):
      Return a helper object / requests.Session with:
        base_url = API_URL
        headers = {"Authorization": f"Bearer {auth_token}"}
        default timeout = 30

TESTS TO WRITE:

  test_full_pdf_pipeline(api):
    1. POST /files/upload with a small test PDF (create a minimal valid PDF in-memory)
    2. PUT the PDF bytes to the uploadUrl
    3. Poll GET /files/{fileId} every 2 seconds for up to 120 seconds
    4. Assert final status == "PROCESSED"
    5. Assert response has non-empty "summary" and "extractedText"
    WHY: End-to-end validates the entire chain:
         S3 → EventBridge → SQS → Step Functions → Textract → Comprehend → Bedrock → DynamoDB

  test_full_image_pipeline(api):
    Same as above but with a real JPEG image (small test image)
    Assert final status == "PROCESSED"
    Assert response has non-empty "labels" and "summary"

  test_list_shows_uploaded_file(api):
    Upload a file
    GET /files
    Assert the uploaded fileId appears in the list

  test_delete_removes_file(api):
    Upload a file
    Wait for PROCESSED
    DELETE /files/{fileId}
    GET /files/{fileId} → assert 404

  test_unauthorized_access_rejected():
    GET /files without Authorization header
    Assert 401 response
    WHY: Verifies the Cognito authorizer is wired up correctly in API Gateway.

HELPERS:
  def wait_for_status(api, file_id, target_status, timeout=120, interval=3):
    Poll until processingStatus == target_status or timeout exceeded
    Raise TimeoutError if not reached
"""

import os
import time
import json
import pytest
import requests

API_URL = os.environ.get("API_URL", "")
WS_URL  = os.environ.get("WS_URL", "")

# TODO: implement the fixtures and test cases described above
