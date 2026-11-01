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

# this function gets one files database record and its AI results
# if processing is complete it creates a temporary URL to download the processed results from s3
def handler(event, context):
    user_id = extract_user_id(event)

    # ive learned how to get event info from POST with body
    # and how to get queryparameters from GET
    # this is different bc of pathParameters 
    # traditional website GET /about would return HTML About US for example
    # different paths often meant different page
    # for REST API server returns JSON so the path is identifying a piece of data not a web page
    # in my application front end is a single webpage so its calling my API
    # broswer doesn't know what to do from URL alone its what caused request and what comes back
    # for example if server responds with content type text/html then itll load the page
    # but if its application/json then browser says thats not a webpage ill give data back to the javascript that requested it
    # so over http body is just raw text bytes and API gateway puts into the event as a string which is in json
    # then you do the json.loads to get into dict
    # whereas in this case API gateway can actually parse for you and already sends it to you as a dict
    # query parameters would have actually behaved this way if it was normal but we were querying with dicts that can't be passed normally like paths are
    path_params = event.get("pathParameters") or {}
    file_id = path_params.get("fileId")

    if not isinstance(file_id, str) or not file_id.strip():
        raise ValidationError("fileId is required")

    # gets file from dynamoDB
    item = get_file(user_id, file_id)

    # if the record has been processed then we can continue to download process
    if item.get("processingStatus") == "PROCESSED":
        s3_client = boto3.client("s3")  
        # calls the url generation method
        item["downloadUrl"] = s3_client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": PROCESSED_BUCKET,
                "Key": item["s3Key"],  # s3 object location
            },
            ExpiresIn=60,
        ) # doesn't download it grants frontend permission to

    internal_fields = {"PK", "SK", "s3Key", "userId", "ttl"}

    # creates a new dict by filtering what was given by dynamDB
    result = {
        key: value
        for key, value in item.items()
        if key not in internal_fields
    }

    return success(result)
