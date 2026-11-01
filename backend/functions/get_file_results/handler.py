import os
import boto3
from error_types import ValidationError, NotFoundError, AuthorizationError
from response_helpers import success, error, extract_user_id
from dynamo_client import get_file

PROCESSED_BUCKET = os.environ["PROCESSED_BUCKET"]

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
