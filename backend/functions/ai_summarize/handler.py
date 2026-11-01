import os
import json
import boto3
from dynamo_client import update_file_status

MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-haiku-20240307-v1:0")

bedrock = boto3.client("bedrock-runtime")
dynamodb = boto3.resource("dynamodb")

def handler(event, context):
    user_id = event["userId"]
    file_id = event["fileId"]

    try:
        # sees if the event has extractedtext and if None of empty uses empty string
        if "extractedText" in event:
            extracted_text = event.get("extractedText") or ""
            # builds instructions to send to the model
            # this is the prompt for the textract output
            prompt = (
                # parenthesis let you split a long string across multiple lines
                "Summarize the following document in 3-5 sentences for a "
                "non-technical reader. Focus on the main topic and key facts.\n"
                f"Document text (first 3000 chars):\n{extracted_text[:3000]}"
            )
        elif "labels" in event:
            # rekognition output is a python lists whereas textracts was already a string thats why json.dumps here
            labels_text = json.dumps(event.get("labels") or [])[:3000]
            # this is the prompt for the rekognition output
            prompt = (
                "You are analyzing an image. Rekognition detected these labels:\n"
                f"{labels_text}\n"
                "Write a 2-3 sentence description of what this image likely "
                "shows, in plain English."
            )
        else:
            raise ValueError("Event must contain extractedText or labels")

        # creates dict containing instructions for model
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 500,
            "messages": [{"role": "user", "content": prompt}],
        }
        # role user identifies it as a user message 

        # calls the model and stores response
        # MODEL ID tells bedrock which AI model do I want to run
        # athropic version tells antropic/bedrock which request/response API format and I using
        # its the versino of JSON contract between your code and anthropic
        response = bedrock.invoke_model(
            modelId=MODEL_ID,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
        # response["body"] isnt actual text yet its a stream object which basically a file youre reading from
        # so .read() lets you read all the bytes from the stream
        result = json.loads(response["body"].read())
        summary = result["content"][0]["text"].strip()
        # content block is always a list for consistency even if just one text block
        # but a response could contain multiple I chose the first each time

        update_file_status(
            user_id,
            file_id,
            "PROCESSED",
            summary=summary,
            extractedText=event.get("extractedText"),
            labels=event.get("labels"),
            entities=event.get("entities"),
        )

        return {**event, "summary": summary}

    except Exception:
        update_file_status(user_id, file_id, "FAILED")
        raise
