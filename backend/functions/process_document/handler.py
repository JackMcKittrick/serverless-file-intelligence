"""
backend/functions/process_document/handler.py
==============================================
Lambda: Step Functions task — run Textract + Comprehend on a PDF/document.

Input (from Step Functions, passed directly as the event):
  {
    "fileId": "...", "userId": "...", "s3Key": "...", "contentType": "application/pdf"
  }

Output (returned to Step Functions, becomes input to the next state):
  {
    "fileId": "...", "userId": "...", "s3Key": "...",
    "extractedText": "full text from Textract",
    "entities": [{"Text": "...", "Type": "PERSON|ORG|...", "Score": 0.99}, ...]
  }

────────────────────────────────────────────────────────────────────────────────
WHAT TO BUILD
────────────────────────────────────────────────────────────────────────────────
NOTE: This function runs INSIDE Step Functions, not API Gateway. There is no
      HTTP response shape. Return a plain dict or raise an exception.

STEP 1 — Update DynamoDB status to PROCESSING
  - update_file_status(user_id, file_id, "PROCESSING")
  WHY: The frontend polls GET /files/{id} and shows a spinner while status
       is PROCESSING. Set this immediately so the user gets feedback.

STEP 2 — Run Textract detect_document_text (synchronous)
  - textract = boto3.client("textract")
  - response = textract.detect_document_text(
        Document={"S3Object": {"Bucket": UPLOADS_BUCKET, "Name": s3_key}}
    )
  - Extract all LINE blocks: blocks where Type == "LINE"
  - Join their Text values with "\n" to build extracted_text
  WHY: detect_document_text is synchronous for documents up to 5 pages.
       For longer documents you would use start_document_text_detection (async).
       For a portfolio project, synchronous is fine.

STEP 3 — Run Comprehend detect_entities on the extracted text
  - comprehend = boto3.client("comprehend")
  - response = comprehend.detect_entities(Text=extracted_text[:5000], LanguageCode="en")
  - Truncate to first 5000 chars (Comprehend limit is 5000 UTF-8 bytes)
  - Filter entities with Score >= 0.80
  WHY: Comprehend identifies people, organizations, locations, dates —
       richer context than raw text alone.

STEP 4 — Return the enriched event dict (Step Functions continues with this)
  return {
    **event,
    "extractedText": extracted_text,
    "entities": entities,
  }
  WHY: Step Functions passes this dict as input to the next state (ai_summarize).

STEP 5 — Error handling
  - Wrap Steps 2-4 in try/except
  - On any exception: update_file_status(user_id, file_id, "FAILED")
  - Re-raise (Step Functions catches the exception and routes to the Catch state)
  WHY: Always update DynamoDB before re-raising so the user sees FAILED, not
       stuck PROCESSING, even if Step Functions retries.

ENVIRONMENT VARIABLES:
  UPLOADS_BUCKET, TABLE_NAME
"""

import os
import boto3
from dynamo_client import update_file_status

UPLOADS_BUCKET = os.environ["UPLOADS_BUCKET"]

# TODO: implement handler(event, context)
def handler(event, context):
    pass
