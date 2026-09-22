"""
backend/layers/shared/python/response_helpers.py
=================================================
HTTP response factory functions used by every Lambda handler.
API Gateway requires a specific dict shape; these helpers enforce it consistently.

Import in every handler:
  from response_helpers import success, error, paginated

────────────────────────────────────────────────────────────────────────────────
WHAT TO BUILD
────────────────────────────────────────────────────────────────────────────────

STEP 1 — Define CORS_HEADERS dict
  {
    "Access-Control-Allow-Origin": "*",        ← tighten to CloudFront URL later
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
    "Content-Type": "application/json",
  }
  WHY: Every response must carry these headers or the browser will refuse to
       read it. Define once here so no handler can forget them.

STEP 2 — success(body: dict, status_code: int = 200) → dict
  Returns:
    {
      "statusCode": status_code,
      "headers": CORS_HEADERS,
      "body": json.dumps(body),
    }
  WHY: API Gateway reads "statusCode", "headers", and "body" (as a JSON string).
       This wrapper enforces the shape and always serializes the body.

STEP 3 — error(message: str, status_code: int = 500, error_code: str = "ERROR") → dict
  Returns the same shape as success() but body is:
    {"error": error_code, "message": message}
  WHY: Consistent error shape lets the frontend parse a single error format
       regardless of which endpoint failed.

STEP 4 — paginated(items: list, last_key=None, **extra) → dict
  Returns success() with body:
    {"items": items, "count": len(items), "lastKey": last_key, **extra}
  Omit "lastKey" from the body if last_key is None (don't send null to clients).
  WHY: The list_files endpoint pages through DynamoDB. This helper ensures the
       pagination envelope is consistent across all list endpoints.

STEP 5 — extract_user_id(event: dict) → str
  Reads event["requestContext"]["authorizer"]["claims"]["sub"]
  Raises ValidationError("Missing user identity") if the path doesn't exist.
  WHY: Every authenticated endpoint needs the Cognito sub as the userId.
       Centralizing the extraction means one fix if the claim path ever changes.
"""

import json
# TODO: implement CORS_HEADERS, success(), error(), paginated(), extract_user_id()
