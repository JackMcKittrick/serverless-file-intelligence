import json
import os
import base64  # python module that converts bytes into text and back again
from error_types import ValidationError
from response_helpers import success, error, paginated, extract_user_id
from dynamo_client import list_user_files

# returns one page of the logged in users files
def handler(event, context):
    user_id = extract_user_id(event)  
    # so client makes http request and adds query parameters
    # API gateway receives the request and builds the lambda event
    # it puts the query parameters into queryStringParameters
    # all these handlers I am creating are seperate lambdas
    # API gateway is my traffic cop chosing which lambdas get called
    params = event.get("queryStringParameters") or {}

    # query parameters normally come as strings so gotta convert to int
    try:
        limit = int(params.get("limit", 20))
    except (ValueError, TypeError):
        raise ValidationError("limit must be a positive integer")

    if limit <= 0:
        raise ValidationError("limit must be a positive integer")

    # caps page size at 100
    limit = min(limit, 100)

    # you know if a last key was given the crab it
    last_key = None
    cursor = params.get("lastKey")

    if cursor:
        try:
            # decode Base64 string then bytes then UTF-8 string then Python dict 
            decoded_key = json.loads(
                base64.b64decode(cursor, validate=True).decode("utf-8")
            )
            # in the upload handler event["body"] contains JSON because the browser put JSON in the HTTP body
            # and API Gateway passes it through unchanged
            # HTTP GET requests practically and semantically should not have a body
            # a URL query string fundamentally is ?key=value or multiple of those
            # but you can't pass a dict thru the URL so you convert it to string representation with json.dumps()
            # giving example '{"PK":"USER#123","SK":"FILE#abc"}' then ecnode it with base64.b64encode(...)
            # to make it URL safe so from URLs perspective its just example lastKey=eyJQSyI6IlVTRVIjMTIzIiwiU0siOiJGSUxFI2FiYyJ9
            # so above I am undoing that process
            # makes sure its a dict
            if isinstance(decoded_key, dict):
                last_key = decoded_key
        except (ValueError, TypeError, UnicodeDecodeError):
            last_key = None

    # this is whats making the class out to dynamoDB
    # helper returns a list of file records and dict used for pagination
    # remember a list is an ordered mutable collection of items there can be different types can be modified and uses []
    # looks like files = ["report.pdf","image.jpg"]
    # tuple is also ordered collectino but is immutable so not changed and uses ()
    # python actually automatically creates a tuple when you return multiple values
    # return items, next_key is identical to return (items, next_key)
    items, next_key = list_user_files(user_id, limit, last_key)
    # items and next key can be changed what cant be changed is what the function after returned in its tuple
    # by doing items, next_key you unpacked creating ordinary variables

    # fields that client can receive
    public_fields = {
        "fileId",
        "fileName",
        "contentType",
        "fileSize",
        "processingStatus",
        "uploadedAt",
        "updatedAt",
    }

    # this is called a comprehension
    # normal loop python short hand is result = [num * 2 for num in nums]
    # so now you see for item in items so this is creating a brand new list 
    # for every item in items it puts something into the new list
    # this uses {} so its creating a dictionary
    # the if statement is a filter making sure the field is something to be given to the user
    items = [
        { 
            key: value
            for key, value in item.items()
            if key in public_fields
        }
        for item in items
    ]

    encoded_next_key = None

    # converts dynamoDBs next key text token to send back to front end
    if next_key:
        encoded_next_key = base64.b64encode(
            json.dumps(next_key).encode("utf-8")
        ).decode("utf-8")

    return paginated(items, last_key=encoded_next_key)
