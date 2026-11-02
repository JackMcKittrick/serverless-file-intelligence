import os
import boto3
from error_types import ValidationError, NotFoundError
from response_helpers import success, error, extract_user_id
from dynamo_client import get_file, delete_file_record

UPLOADS_BUCKET = os.environ["UPLOADS_BUCKET"]
PROCESSED_BUCKET = os.environ["PROCESSED_BUCKET"]

# but the client before the handler because it lets lambda create the client once then reuse it for multiple requests
# if it were inside then a new object created for each request made by client
s3 = boto3.client("s3")

# this function verifies that user owns file then deletes original file and its results and its db record
def handler(event, context):

    user_id = extract_user_id(event)
    # the delete route is DELETE /files/{fileId}
    # which means files is fixed and {fileId} is the path parameter
    # so API Gateway treats only {fileId} as a path parameter
    # API Gateway uses the HTTP method and URL path to select a Lambda:
    # GET /files/abc123 will get results Lambda and DELETE /files/abc123 will get delete file Lambda etc
    # if user did PUT /files/abc123 it would be rejected because this method/route isn't configured in API gateway
    path_params = event.get("pathParameters") or {}
    file_id = path_params.get("fileId")
    # mind you above is same as file_id = event["pathParameters"]["fileId"] with better error handling

    # gets file informatino from dynamoDB
    item = get_file(user_id, file_id)
    s3_key = item["s3Key"]
    # uses the s3 key to delete the bucket with this api call
    s3.delete_object(Bucket=UPLOADS_BUCKET, Key=s3_key)

    # processed results might not exist yet so NoSuchKey is caught and function continues
    try:
        s3.delete_object(Bucket=PROCESSED_BUCKET, Key=s3_key)
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "NoSuchKey":
            raise
    # deletes from dynamoDB
    delete_file_record(user_id, file_id)

    return success({"message": "File deleted successfully"})
