"""
backend/functions/websocket_handler/handler.py
===============================================
Lambda: WebSocket API Gateway — handle $connect, $disconnect, DynamoDB Stream.

This single Lambda handles THREE trigger sources:

  A. WebSocket $connect   (event["requestContext"]["eventType"] == "CONNECT")
  B. WebSocket $disconnect (eventType == "DISCONNECT")
  C. DynamoDB Stream      (event.get("Records") and Records[0]["eventSource"] == "aws:dynamodb")

────────────────────────────────────────────────────────────────────────────────
WHAT TO BUILD
────────────────────────────────────────────────────────────────────────────────

── Route A: WebSocket $connect ──────────────────────────────────────────────────

STEP A1 — Extract connectionId and userId
  - connection_id = event["requestContext"]["connectionId"]
  - user_id = event["queryStringParameters"].get("userId")
    ↳ The frontend appends ?userId=<cognito-sub> when opening the WebSocket.
       In production you would validate a token here instead.
  - Raise ValidationError if userId missing

STEP A2 — Store connection in DynamoDB (SK = CONN#<connectionId>)
  - item = {
        "PK": PK(user_id),
        "SK": SK_CONN(connection_id),
        "connectionId": connection_id,
        "userId": user_id,
        "connectedAt": now,
        "ttl": int(time.time()) + 7200,   ← 2-hour TTL: stale connections auto-delete
    }
  - put connection record
  WHY: DynamoDB TTL cleans up connections that never received $disconnect
       (browser crashed, network drop, etc.).

STEP A3 — Return {"statusCode": 200}  ← WebSocket connect response must be 200

── Route B: WebSocket $disconnect ───────────────────────────────────────────────

STEP B1 — Delete the connection record
  - Extract connectionId from event["requestContext"]["connectionId"]
  - Query DynamoDB to find the matching CONN# record (you need to know the PK,
    which means you need the userId — store it in the connection record so you
    can look it up here, or use a GSI on connectionId)
  WHY: Clean up immediately on disconnect; don't wait for TTL expiry.

STEP B2 — Return {"statusCode": 200}

── Route C: DynamoDB Stream (file status changed → push to WebSocket) ───────────

STEP C1 — Filter for relevant events
  - Loop over event["Records"]
  - Skip if eventName == "REMOVE" (connection TTL cleanup — ignore)
  - Skip if NewImage's SK doesn't start with "FILE#" (ignore connection records)
  - Skip if processingStatus didn't change (compare OldImage vs NewImage)
  WHY: The stream fires for every DynamoDB change; filtering prevents sending
       a WebSocket push for connection record TTL deletes.

STEP C2 — Extract the userId from NewImage["PK"]
  - user_id = NewImage["PK"]["S"].replace("USER#", "")

STEP C3 — Find all active WebSocket connections for this userId
  - Query DynamoDB: PK=USER#<userId>, SK begins_with "CONN#"
  - Returns a list of connectionId values

STEP C4 — Push status update to each connection via API Gateway Management API
  - apigw = boto3.client("apigatewaymanagementapi",
                         endpoint_url=f"https://{WEBSOCKET_API_ID}.execute-api.{region}.amazonaws.com/{STAGE}")
  - For each connection:
      try:
          apigw.post_to_connection(
              ConnectionId=conn_id,
              Data=json.dumps({"fileId": file_id, "status": new_status}).encode()
          )
      except apigw.exceptions.GoneException:
          # Stale connection — delete the record
          delete_connection_record(user_id, conn_id)
  WHY: GoneException means the client disconnected without sending $disconnect.
       Clean up immediately instead of letting TTL do it.

ENVIRONMENT VARIABLES:
  TABLE_NAME, WEBSOCKET_API_ID, WEBSOCKET_STAGE
"""

import os
import json
import time
import boto3
from dynamo_client import PK, SK_CONN, put_file

TABLE_NAME = os.environ["TABLE_NAME"]

# in lambda you dont need to create session manually if you do boto3.client("s3") 
# then boto3 will auto use the lambda execution role creds 
# this gives object that represents current aws login credentials and region config
# then you can create clients from it like s3 = session.client("s3")
# session = boto3.session.Session() but not going to use this method as we havenet been earlier
# terraform uses var.aws_region such as "us-east-1" and deploys your Lambda function into that region
# when AWS starts the function Lambda automatically adds AWS_REGION=us-east-1 to its environment
# and the python code reads that value like this AWS_REGION = os.environ["AWS_REGION"]

AWS_REGION = os.environ["AWS_REGION"]

# normally HTTP broswer sends server request then server sends broswer response and the underlying TCP connection closes
# websocket does one handshake then keeps connection open letting data flow both ways until you close it
# in my app processing might take serveral seconds so front end could poll with http messages asking done yet
# or use websockets to let backend notify the frontend
# so say javascript front end creates new WebSocket the broswer contacts API gateway and triggers connect lambda
# store the connections in dynamoDB so taht later when need to send a message you know what connection belongs to which user
# API gateway will accept the connection after the lambda returns
# note lambda is not holding the socket open the broswer makes its websocket connection to API gateway 

WEBSOCKET_API_ID = os.environ["WEBSOCKET_API_ID"]
WEBSOCKET_STAGE  = os.environ.get("WEBSOCKET_STAGE", "prod")

table = boto3.resource("dynamodb").Table(TABLE_NAME)

# deletes a known connection from the dynamoDB table
def delete_connection_record(user_id, connection_id):
    table.delete_item(
        Key={"PK": PK(user_id), "SK": SK_CONN(connection_id)}
    )

# queries dynamoDB for a connectino uses the users key and the SK key starting with CONN#
# im using one websocket connection per open broswer tab to receive status updates for all that users files not for each api call
def get_connections(user_id):
    params = {
        "KeyConditionExpression": (
            Key("PK").eq(PK(user_id))
            & Key("SK").begins_with("CONN#")
        )
    }
    # one query may return only part of the results so the while loop continues until no pages left
    # thats why loop is always True and ends on a break
    while True:   # **params unpacks into named arguments
        response = table.query(**params)
        # remember dynamoDB returns a dict like { "Items": ["PK": "USER#123", "SK": "CONN#abc", "connectionId": "abc"}}
        # response has matching items and a lastevaluatedkey if more pages remain
        # return gives back a value and ends the function
        # but here yield gives back a value without ending the function
        # the function pauses until the caller asks for another value
        yield from response.get("Items", []) # remember the [] means give me empty list if not items

        if "LastEvaluatedKey" not in response:
            break
        # updates query to start at new location
        # dynamoDB doesnt literally have pages its really just continue after last element you gave
        params["ExclusiveStartKey"] = response["LastEvaluatedKey"]


def disconnect(connection_id):
    params = {
        # only keep items who SK equals "CONN#abc123" for example
        "FilterExpression": Attr("SK").eq(SK_CONN(connection_id)),
        "ProjectionExpression": "PK, SK",  # dont reutrn entire item just these attributes bc thats needed for deletion
    }

    while True:
        # in my table the combination of PK and SK is unique
        # PK can repeat think of as folder name and SK as item name inside folder
        # DynamoDB's rule is a query must reqire the partition key of the table
        # so we use scan to find all elements with the SK
        response = table.scan(**params)

        # below same format as get connections to instead delete each item
        for item in response.get("Items", []):
            table.delete_item(
                Key={"PK": item["PK"], "SK": item["SK"]}
            )

        if "LastEvaluatedKey" not in response:
            break

        params["ExclusiveStartKey"] = response["LastEvaluatedKey"]

# this functino finds file states changes in dynamoDB stream reocrds and sends to users connected broswer
# records is a list of database changes from handler
def process_stream(records):
    apigw = None
    # loops thru all the db changes
    for record in records:
        # make sure from dynamoDB
        if record.get("eventSource") != "aws:dynamodb":
            continue
        # we dont want to send status updates for deleted files only existing
        if record.get("eventName") == "REMOVE":
            continue

        # images is the dynamoDB specific part of the record 
        images = record.get("dynamodb", {})
        # new image is item after the change
        # old image is item before change
        new_image = images.get("NewImage", {})
        old_image = images.get("OldImage", {})

        # dynamoDB stream record reporesent string attributes like this "SK": {"S": "FILE#abc"}
        sk = new_image.get("SK", {}).get("S", "")
        # skip items whos SK dont start with FILE
        if not sk.startswith("FILE#"):
            continue

        # read the status after and before the change
        new_status = new_image.get("processingStatus", {}).get("S")
        old_status = old_image.get("processingStatus", {}).get("S")

        # skips if no new status or status is the same
        if new_status is None or new_status == old_status:
            continue

        # skip if PK is not in right format
        pk = new_image.get("PK", {}).get("S", "")
        if not pk.startswith("USER#"):
            continue

        # removes prefixes so function knows whose connections to find and the file changed
        user_id = pk[len("USER#"):]
        file_id = sk[len("FILE#"):]

        # converts to json then bytes for sending
        payload = json.dumps(
            {"fileId": file_id, "status": new_status}
        ).encode("utf-8")

        # loops thru all of users saved connections
        for connection in get_connections(user_id):
            connection_id = connection["connectionId"]
            # creates aws client to send messages to existing websocket connection
            if apigw is None:
                apigw = boto3.client(
                    "apigatewaymanagementapi",
                    endpoint_url=(
                        f"https://{WEBSOCKET_API_ID}.execute-api."
                        f"{AWS_REGION}.amazonaws.com/"
                        f"{WEBSOCKET_STAGE}"
                    ),
                )
            # sends the message
            try:
                apigw.post_to_connection(
                    ConnectionId=connection_id,   # which broswer connectino receives it
                    Data=payload,  # data containing the bytes
                )
            except apigw.exceptions.GoneException:
                # if connection no longer exists then we gotta delete dynamo DB record
                delete_connection_record(user_id, connection_id)


# TODO: implement handler(event, context)

# this function identifies whether a lambda received a websocket connection disconnection or dynamoDB changes 
# and chooses the appropriate code to run
def handler(event, context):
    # api gateway creates event and puts info about websocket request into a requestConext field
    request_context = event.get("requestContext") or {}
    event_type = request_context.get("eventType")

    # api gateway either gets a connect or disconnect request so two if statements
    if event_type == "CONNECT":
        # reads teh unique connection ID API gateway assigned to the convo
        connection_id = request_context["connectionId"]
        # gets userID from connection URL query parameters
        user_id = (
            event.get("queryStringParameters") or {}
        ).get("userId")
        # ensure user ID is valid
        if not isinstance(user_id, str) or not user_id.strip():
            raise ValidationError("userId is required")

        # dynamoDB call to save connection record
        table.put_item(
            Item={
                "PK": PK(user_id),
                "SK": SK_CONN(connection_id),
                "connectionId": connection_id,
                "userId": user_id,
                "connectedAt": datetime.now(timezone.utc).isoformat(),
                "ttl": int(time.time()) + 7200,
            }
        )
        # success allowing websocket connection to be established
        return {"statusCode": 200}

    # calls disconnect() helper to delete dynamoDB record after readiing closed connection ID
    if event_type == "DISCONNECT":
        disconnect(request_context["connectionId"])
        return {"statusCode": 200}

    # the third scenario this lambda handles is dynamoDB status updates
    records = event.get("Records") or []

    # check to see if dynamoDB stream event and call helper
    if records and records[0].get("eventSource") == "aws:dynamodb":
        process_stream(records)
        return {"statusCode": 200}

    return {"statusCode": 400}
