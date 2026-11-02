import os
import boto3
from dynamo_client import update_file_status

UPLOADS_BUCKET = os.environ["UPLOADS_BUCKET"]
rekognition = boto3.client("rekognition")

# this function uses amazon rekognition to identify contents 
def handler(event, context):
    # remember beceause from step function no need to parse 
    user_id = event["userId"]
    file_id = event["fileId"]

    try:
        s3_key = event["s3Key"]
        # also sets status to processing
        # bc a uploaded file takes one path either process_ducment for pdfs
        # or this process image for JPEG
        update_file_status(user_id, file_id, "PROCESSING")

        response = rekognition.detect_labels(
            # tells rekognition which image to analyze by giving bucket and object key
            Image={
                "S3Object": {
                    "Bucket": UPLOADS_BUCKET,
                    "Name": s3_key,
                }
            },
            # set labels at 20 max and minimum confidence level
            MaxLabels=20,
            MinConfidence=70.0,
        )

        # loops through the returned labels and keeps their names like ["Cat", "Pet", "Animal"]
        label_names_list = [label["Name"] for label in response["Labels"]]
        return {**event, "labels": label_names_list}

    except Exception:
        update_file_status(user_id, file_id, "FAILED")
        raise
