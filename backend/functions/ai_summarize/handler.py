"""
backend/functions/ai_summarize/handler.py
==========================================
Lambda: Step Functions task — call Bedrock to generate a plain-language summary.

Input (from Step Functions, after process_document OR process_image):
  {
    "fileId": "...", "userId": "...", "s3Key": "...", "contentType": "...",
    "extractedText": "..." OR "labels": [...],   ← one or the other, not both
    "entities": [...],                            ← present for documents
  }

Output (to Step Functions):
  {**event, "summary": "Plain English summary of the file."}

────────────────────────────────────────────────────────────────────────────────
WHAT TO BUILD
────────────────────────────────────────────────────────────────────────────────

STEP 1 — Build the prompt based on file type
  If contentType starts with "image/":
    prompt = f"You are analyzing an image. Rekognition detected these labels:
               {json.dumps(labels)}. Write a 2-3 sentence description of what
               this image likely shows, in plain English."
  Else (document):
    prompt = f"Summarize the following document in 3-5 sentences for a
               non-technical reader. Focus on the main topic and key facts.
               Document text (first 3000 chars):
               {extracted_text[:3000]}"
  WHY: Different input shapes need different prompts. Images have labels; docs
       have raw text. Truncating to 3000 chars stays well within Bedrock's
       context window for Claude Haiku and keeps costs low.

STEP 2 — Call Bedrock Claude Haiku (or Nova Micro)
  bedrock = boto3.client("bedrock-runtime", region_name=os.environ["AWS_REGION"])
  body = {
    "anthropic_version": "bedrock-2023-05-31",
    "max_tokens": 500,
    "messages": [{"role": "user", "content": prompt}],
  }
  response = bedrock.invoke_model(
      modelId=MODEL_ID,      ← read from env var, default "anthropic.claude-haiku-20240307-v1:0"
      body=json.dumps(body),
      contentType="application/json",
      accept="application/json",
  )
  result = json.loads(response["body"].read())
  summary = result["content"][0]["text"].strip()
  WHY: Claude Haiku is the cheapest Claude model (~$0.00025 per invocation at
       500 output tokens). Nova Micro is cheaper still if you prefer Amazon models.

STEP 3 — Write final results to DynamoDB (status → PROCESSED)
  update_file_status(user_id, file_id, "PROCESSED",
      summary=summary,
      extractedText=event.get("extractedText"),
      labels=event.get("labels"),
      entities=event.get("entities"),
  )
  WHY: This is the LAST step in the pipeline. Setting PROCESSED here means the
       GET /files/{id} endpoint will now return the full enriched record.

STEP 4 — Return enriched event
  return {**event, "summary": summary}

STEP 5 — Error handling
  - On exception: update_file_status(..., "FAILED"), re-raise

ENVIRONMENT VARIABLES: TABLE_NAME, BEDROCK_MODEL_ID (default claude-haiku)
"""

import os
import json
import boto3
from dynamo_client import update_file_status

MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-haiku-20240307-v1:0")

# TODO: implement handler(event, context)
def handler(event, context):
    pass
