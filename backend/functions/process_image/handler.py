"""
backend/functions/process_image/handler.py
==========================================
Lambda: Step Functions task — run Rekognition label detection on an image.

Input (from Step Functions):
  {"fileId": "...", "userId": "...", "s3Key": "...", "contentType": "image/jpeg"}

Output (to Step Functions):
  {**event, "labels": [{"Name": "Cat", "Confidence": 99.1}, ...]}

────────────────────────────────────────────────────────────────────────────────
WHAT TO BUILD
────────────────────────────────────────────────────────────────────────────────

STEP 1 — Update DynamoDB status to PROCESSING
  - update_file_status(user_id, file_id, "PROCESSING")

STEP 2 — Run Rekognition detect_labels
  - rekognition = boto3.client("rekognition")
  - response = rekognition.detect_labels(
        Image={"S3Object": {"Bucket": UPLOADS_BUCKET, "Name": s3_key}},
        MaxLabels=20,
        MinConfidence=70.0,
    )
  - labels = [{"Name": l["Name"], "Confidence": round(l["Confidence"], 1)}
               for l in response["Labels"]]
  WHY: MaxLabels=20 and MinConfidence=70 avoid noise while returning enough
       labels to build a meaningful description of the image.

STEP 3 — Return enriched event
  return {**event, "labels": labels}

STEP 4 — Error handling
  - On any exception: update_file_status(user_id, file_id, "FAILED"), re-raise

ENVIRONMENT VARIABLES: UPLOADS_BUCKET, TABLE_NAME
"""

import os
import boto3
from dynamo_client import update_file_status

UPLOADS_BUCKET = os.environ["UPLOADS_BUCKET"]

# TODO: implement handler(event, context)
def handler(event, context):
    pass
