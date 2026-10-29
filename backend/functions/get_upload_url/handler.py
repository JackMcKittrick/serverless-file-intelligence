"""
backend/functions/get_upload_url/handler.py
============================================
Lambda: POST /files/upload — generate a pre-signed S3 PUT URL.

Event shape (from API Gateway):
  - Headers: Authorization: Bearer <cognito-jwt>   (validated by API GW)
  - Body (JSON): {"fileName": "report.pdf", "contentType": "application/pdf", "fileSize": 1048576}

Response (200):
  {"uploadUrl": "https://s3.amazonaws.com/...", "fileId": "<uuid>", "expiresIn": 900}

────────────────────────────────────────────────────────────────────────────────
WHAT TO BUILD — implement the handler() function below
────────────────────────────────────────────────────────────────────────────────

STEP 1 — Parse and validate the request body
  - json.loads(event["body"])
  - Required fields: fileName, contentType, fileSize
  - Raise ValidationError for missing fields
  - Raise ValidationError if fileSize > 52428800 (50 MB)
  - Allowed contentTypes: application/pdf, image/jpeg, image/png, image/webp, image/tiff
  WHY: Rejecting invalid requests before generating a URL saves the 5ms S3 call
       and provides a clear error to the frontend.

STEP 2 — Extract the userId from the JWT claims
  - user_id = extract_user_id(event)    ← from response_helpers
  WHY: The userId becomes part of the DynamoDB PK; it must match the Cognito sub
       so users can only ever access their own files.

STEP 3 — Generate a fileId and build the S3 key
  - file_id = str(uuid.uuid4())
  - s3_key = f"{user_id}/{file_id}/{file_name}"
  WHY: Prefixing with userId allows per-user IAM conditions if needed and makes
       S3 object paths human-readable in the console. Including fileId prevents
       collisions if the same user uploads two files with the same name.

STEP 4 — Create a pre-signed PUT URL (900 second TTL)
  - s3_client = boto3.client("s3")
  - url = s3_client.generate_presigned_url(
        "put_object",
        Params={"Bucket": UPLOADS_BUCKET, "Key": s3_key,
                "ContentType": content_type},
        ExpiresIn=900,
    )
  WHY: The browser PUT goes directly to S3. 900 seconds (15 min) is long enough
       for large uploads on slow connections but short enough to limit exposure.

STEP 5 — Write a PENDING record to DynamoDB
  - item = {
        "PK": PK(user_id), "SK": SK_FILE(file_id),
        "fileId": file_id, "userId": user_id,
        "fileName": file_name, "contentType": content_type,
        "fileSize": file_size, "s3Key": s3_key,
        "processingStatus": "PENDING",
        "uploadedAt": datetime.utcnow().isoformat() + "Z",
        "ttl": int(time.time()) + 86400,   # 24-hour TTL for un-confirmed uploads
    }
  - put_file(item)
  WHY: Writing PENDING before the upload means the housekeeping Lambda can detect
       uploads that started but never completed (browser crashed, timeout, etc.)
       and clean them up after 2 hours.

STEP 6 — Return the URL and fileId
  - return success({"uploadUrl": url, "fileId": file_id, "expiresIn": 900})
  WHY: The frontend needs both: the URL to PUT to, and the fileId to call
       POST /files/{fileId}/confirm once the upload completes.

ENVIRONMENT VARIABLES (set by CDK ApiStack):
  UPLOADS_BUCKET   — name of the Terraform-managed S3 uploads bucket
  TABLE_NAME       — DynamoDB table name (set in dynamo_client automatically)
"""

import json
import os
import uuid  # pythons built in module for generating unique IDs 
import time
from datetime import datetime
import boto3
from error_types import ValidationError
from response_helpers import success, error, extract_user_id
from dynamo_client import put_file, PK, SK_FILE

UPLOADS_BUCKET = os.environ["UPLOADS_BUCKET"]  # gets enviroment variable so can have prod vs dev

# TODO: implement handler(event, context)

# this is the standard handler signature for aws lambda written in python
# aws requres two parameters so although i don't use context its still needed here
# so aws will call this function when the endpoint receives a request
def handler(event, context):   
    # set of MIME types which is a standard label desecribing files format
    # set in python is {"image/png", "image/jpeg"} so individual values 
    allowed_content_types = {
        "application/pdf",
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "image/tiff",
    }

    # python lambda functinos event is a dict that aws creates and passes to your event handler
    # but the body of field of the event is still a JSON string
    try:
        # here .get("body") looks up body in the event dictionary
        # that differs than event["body"] bc .get() returns None when key is missing
        # then json.loads parses the JSON into python data
        body = json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        raise ValidationError("Request body must be valid JSON")
    # so this checks did that JSON parse into a dict object specifically
    if not isinstance(body, dict):
        raise ValidationError("Request body must be a JSON object")
    # creates a tuple and makes sure each field exists in the dict
    for field in ("fileName", "contentType", "fileSize"):
        if field not in body:
            raise ValidationError(f"Missing required field: {field}")

    # gets values from dict and gives variable names
    file_name = body["fileName"]
    content_type = body["contentType"]
    file_size = body["fileSize"]


    # next four if statements are all error checks for the values pulled from dict
    if not isinstance(file_name, str) or not file_name.strip():
        raise ValidationError("fileName must be a non-empty string")

    if (
        not isinstance(content_type, str)
        or content_type not in allowed_content_types
    ):
        raise ValidationError("Unsupported contentType")

    if (
        isinstance(file_size, bool)
        or not isinstance(file_size, int)
        or file_size <= 0
    ):
        raise ValidationError("fileSize must be a positive integer")

    if file_size > 52428800:
        raise ValidationError("File size must not exceed 50 MB")

    # get user ID using helper function I wrote
    user_id = extract_user_id(event)

    # function here helps generate a unique file ID
    file_id = str(uuid.uuid4())
    s3_key = f"{user_id}/{file_id}/{file_name}"

    # creates an object that can make API calls to s3
    s3_client = boto3.client("s3")
    # creates a signed URL authorizing s3 put_object operation
    # remember reason for presigned URLs without backend would have to receive entire file then upload to s3
    # with presigned url lambda generates then broswer can do the PUT file directly
    # this way file never goes thru lambda
    # normal person can't do this but lambda has the credentials thru IAM
    url = s3_client.generate_presigned_url(
        "put_object",
        # you supply arguments in this dict
        Params={ 
            "Bucket": UPLOADS_BUCKET,
            "Key": s3_key,
            "ContentType": content_type,
        },
        ExpiresIn=900,  # time the URL is valid for
    )

    # buids the database record
    item = {
        # two functions build the PK and SK key
        "PK": PK(user_id),  
        "SK": SK_FILE(file_id),
        "fileId": file_id,
        "userId": user_id,
        "fileName": file_name,
        "contentType": content_type,
        "fileSize": file_size,
        "s3Key": s3_key,
        "processingStatus": "PENDING",
        "uploadedAt": datetime.now(timezone.utc).isoformat(),
        "ttl": int(time.time()) + 86400,
    }
    # calls helper function I wrote to put to dynamoDB
    put_file(item) 

    # http message format
    return success({
        "uploadUrl": url,
        "fileId": file_id,
        "expiresIn": 900,
    })
