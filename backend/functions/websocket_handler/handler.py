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

WEBSOCKET_API_ID = os.environ["WEBSOCKET_API_ID"]
WEBSOCKET_STAGE  = os.environ.get("WEBSOCKET_STAGE", "prod")

# TODO: implement handler(event, context)
def handler(event, context):
    pass
