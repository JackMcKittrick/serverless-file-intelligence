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

textract = boto3.client("textract")
comprehend = boto3.client("comprehend")

# this function extracts text from an uploaded document using Textract
# then it uses Comprehend to identify entities such as people, orgs, and locations
# it passes the text and entities to the next Step Functions step
def handler(event, context):

    # previous files ive written lamdba was built by API gateway bc called was HTTP request
    # here the caller is Step Functions and it can pass whatever JSON it wants to the next lambda
    # therefore the variables are very easily accessed
    user_id = event["userId"]
    file_id = event["fileId"]
    s3_key = event["s3Key"]


    try:
        # updates dynamoDB record to show that processing has begun
        update_file_status(user_id, file_id, "PROCESSING")

        # remember clients made outside handler
        # call textract the response is a dict stored in response variable
        response = textract.detect_document_text(
            # tells textract where to find the document
            Document={
                "S3Object": {
                    "Bucket": UPLOADS_BUCKET,
                    "Name": s3_key,
                }
            }
        )

        # textract pulls the words off a document scanned PDF photo or image and gives them back to you as text 
        extracted_text = "\n".join(   # join takes all the strings and glues them together
            # for example [ "John Smith",  "Software Engineer"] becomes "John Smith\nSoftware Engineer" 
            block["Text"]  # extras the text from the line
            for block in response.get("Blocks", [])   # uses an empty list if the key is missing so the loop runs zero times
            # empty list if "Blocks" is missing from response
            if block.get("BlockType") == "LINE"     # keeps blocks whos type is line
        )

        entity_text = (
            extracted_text[:5000]   # take a most the first 5000 characters
            .encode("utf-8")[:5000]       # convert the string to bytes bc service like comphreend has limits in bytes not characters
            .decode("utf-8", errors="ignore")   # converts back into text 
        )

        entities = []   

        # comprehend reads text and tells you whats in it by labeling it not changeing the text
        # entities for example "John Smith" = PERSON, "Acme Corp" = ORGANIZATION
        # key phrases for example "great service"
        if entity_text.strip():
            # asks to identify entities
            response = comprehend.detect_entities(
                Text=entity_text,
                LanguageCode="en",
            )

            # builds a list of entities from comprehends responses
            entities = [
                {
                    "Text": entity["Text"],
                    "Type": entity["Type"],
                    "Score": entity["Score"],
                }
                for entity in response.get("Entities", [])
                if entity["Score"] >= 0.80   # enforce a minimum confidence score
            ]

        return {
            **event,  
            "extractedText": extracted_text,
            "entities": entities,
        }

    # ** has several uses in Python:#
    # first is unpack a dictionary into a new dictionary
    # so new_dict = {**event, "status": "PROCESSING"} which would copies events entries and then adds or updates "status"
    # note is a shallow copy meaning dicts and lists inside still refer to same objects
    # second unpack a dictionary into named function arguments
    # for example if options = {"name": "Alex", "age": 25} then greet(**options) is equivalent to greet(name="Alex", age=25)
    # third named arguments in a function definition so 
    # if theres def greet(**kwargs): print(kwargs)
    # then alling greet(name="Alex", age=25) collects those arguments into kwargs as {"name": "Alex", "age": 25} and thats whats printed

    except Exception:
        update_file_status(user_id, file_id, "FAILED")
        raise
