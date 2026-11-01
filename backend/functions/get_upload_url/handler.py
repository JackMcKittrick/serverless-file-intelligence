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
