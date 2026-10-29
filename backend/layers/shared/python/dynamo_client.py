import os
import boto3

import os  # python library to read enviroment varaibles
# python code reads the Lambda runtime environment variables that 
# terraform created and populated when the Lambda was deployed
# a lambda function has its own set of enviroment variables attached to its config
from datetime import datetime, timezone
# lets you work with times

import boto3  # this is AWSs python SDK which is the library my python code uses to interact with AWS services
# it imports the whole boto3 module to use something from it do boto3.blahblah
from boto3.dynamodb.conditions import Attr, Key   
from botocore.exceptions import ClientError
# these from and import lines mean go there and import only those 
# so instead of boto3.dynamodb.conditions.Attr("status") you can do Attr("status")
# for most python code the from and import removes the prefix thatd be required

# botocore.exceptions is a file in the python library just like error_types is a file in this directory
from error_types import NotFoundError, ValidationError

TABLE_NAME = os.environ["TABLE_NAME"]  # reads an enviroment variable from lambda confg

_dynamodb = boto3.resource("dynamodb") # creates a Boto3 resource for interacting with dynamoDB
# note that in python leading _ means private by convention its not enforce
_table = _dynamodb.Table(TABLE_NAME)
# creates an object representing the table NOT a new table

# these functions are really just key builders that generate standardized DynamoDB key strings 
def PK(user_id: str) -> str:
    return f"USER#{user_id}"

def SK_FILE(file_id: str) -> str:
    return f"FILE#{file_id}"

def SK_CONN(connection_id: str) -> str:
    return f"CONN#{connection_id}"


# this function gets one file from teh dynamoDB table
# the table has a composite key PK and SK
# PK are how items are grpued together and SK is how items are distinguished with that group
def get_file(user_id: str, file_id: str) -> dict:
    response = _table.get_item(
        Key={
            "PK": PK(user_id),
            "SK": SK_FILE(file_id),
        }
    ) 
    # calls dynamoDB to retreive a record and stores it in response

    item = response.get("Item")
    # DynamoDB's response is a dictionary when a record is found its under item
    # so .get() can look for without raising a KeyError if absent

    if item is None:
        raise NotFoundError(f"File {file_id} not found")

    return item


# gets one page of file records 
def list_user_files(
    user_id: str,
    limit: int = 20,
    last_key=None,
) -> tuple[list, dict | None]:  # tuples are ordered meaning in place inserted that does not mean sorted by something 
    # and they are uneditable
    # could look like ("Jack", 25)
    # first element is a list and the second element is a dict or nothing
    query_args = {   # dictionary with arguments to pass to dynamoDB 
        "KeyConditionExpression": (
            Key("PK").eq(PK(user_id))  # PK key must equal users key
            & Key("SK").begins_with("FILE#")    # SK must start with FILE#
        ),
        "Limit": limit,   # gives requested limit to dynamoDB
    }

    # add starting point to query arguments if exists
    if last_key is not None:
        query_args["ExclusiveStartKey"] = last_key

    # **query_args here unpacks the dictionary into named arguments 
    # from query_args = {"Limit": 20} to Limit=20
    response = _table.query(**query_args)

    return (
        response.get("Items", []),   # "Items" in dynamo DB is a list
        response.get("LastEvaluatedKey"),    # the dict in the tuple
    )


# put file record into dynamoDB table
# this dict will have to include everything needed to make the put like SK and PK and file name
def put_file(item: dict) -> None:
    _table.put_item(Item=item)


# can update a dynamoDB file record without replacing item
def update_file_status(
    user_id: str,
    file_id: str,
    status: str,
    **extra_attrs, # collect any extra keyword arguments into a dictionary.
) -> None:
    # want to control changes to these fields
    protected_fields = {
        "PK",
        "SK",
        "userId",
        "fileId",
        "processingStatus",
        "updatedAt",
    }
  # intersection checks extra_attrs' dictionary keys for protected names
    if protected_fields.intersection(extra_attrs):
        raise ValidationError(
            "Extra attributes cannot override keys, identity, "
            "processingStatus, or updatedAt"
        )

    # builds update values
    updates = {
        "processingStatus": status,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        **extra_attrs,  # because its in a dictionary literal the key value pairs become dict entries 
    }

    # used to build a dynamoDB update expression
    expression_names = {}
    expression_values = {}
    assignments = []

    # .items() on a dict turns each dict entry into a 2 element tuple
    # enumerate() wraps each of those 2 element tuples into a new tuple with an index
    # (0, ("firstName", "Jack"))
    # for each iteration of the loop python unpacks it so 
    # index name and value all have a value
    for index, (name, value) in enumerate(updates.items()):

        name_placeholder = f"#attr{index}" 
        value_placeholder = f":value{index}" 
        # this are both dicts so creates the key values 
        expression_names[name_placeholder] = name  
        expression_values[value_placeholder] = value
   
        assignments.append(
            f"{name_placeholder} = {value_placeholder}"
        )
        # assignments doesn't need real values it builds template string that dynamoDB interprets
        # after first iteration
        # expression_names = {"#attr0": "name"}
        # expression_values = { ":value0": "Jack"}
        # assignments = ["#attr0 = :value0"] 
        # note that assignments contain placeholders not the actual data
        # dynamoDB receives all three pieces and reads it as SET name = "Jack"
        # this is done so dynamoDB can safely substitute them 

    try:
        _table.update_item(
            Key={
                "PK": PK(user_id),
                "SK": SK_FILE(file_id),
            },  # identifies the record telling which row to update
            # below produces "#attr0 = :value0, #attr1 = :value1" for example
            # actual update instructino dynamoDB executes
            UpdateExpression="SET " + ", ".join(assignments),
            # below lines tell dynamoDB that if expression_names = {"#attr0": "filename", "#attr1": "status"}
            # then #attr0 means filename and attr1 means status
            # same logic for attribute values
            ExpressionAttributeNames=expression_names, 
            ExpressionAttributeValues=expression_values,
            # itll resolve to something like SET filename = "report.pdf", statusus = "COMPLETE"
            ConditionExpression=Attr("PK").exists(), # safety check that means only perform update if the item already exists
        )
    except ClientError as exc:  # if aws throws ClientError catch it and exc is the error object
        # checks whether the error happneed because the existence condition wasnt satisfied 
        if (
            exc.response["Error"]["Code"]
            == "ConditionalCheckFailedException"
        ):    # throw homemade error bc more meaningful
            raise NotFoundError(
                f"File {file_id} not found"
            ) from exc  # raises exception but remember the original AWS exception that caused it

        # preserve other AWS errors for the caller to handle.
        raise


# delete dynamnoDB record from table remember s3 deletion is different
def delete_file_record(user_id: str, file_id: str) -> None:
    _table.delete_item(
        Key={
            "PK": PK(user_id),
            "SK": SK_FILE(file_id),
        }
    )   # similar to get_file 