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

from error_types import SFIError, ValidationError
# from ... import ... imports specifici names from a module
# in python a python file is just called a module

# this creates a variable named CORS_HEADERS and assigns a dictionary to it
# my backend will need to attach these headers to its responses

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",  # any origin can read the response, not ideal gonna be changed
    "Access-Control-Allow-Headers": "Content-Type,Authorization",   
    "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS", 
    # OPTIONS is used for preflight aka prelimiary requests mentioned below
    # a browser might not immediately send certain cross-origin requests for like PUT/DELETE requests
    # the browser might send out a preflight OPTIONS request that asks the server which methods and request headers are allowed
    # the server will then respond with Access-Control-Allow-Methods and Access-Control-Allow-Headers
    # a good browser will look at these and only send if allowed
    "Content-Type": "application/json",  # tells client that http repsonse bodies contains JSON
    # content type is not specific to CORS thats for general http headers
}
# CORS stands for cross origin resource sharing and remember that browsers enforce the same origin policy
# thatll block JavaScript from reading a response from a different origin unless explicit permission is granted through CORS
# to have same orgin URLs must have the same protocol, host, and port 
# CORS uses HTTP headers to allow a server to tell the browser which origins are allowed to read its responses it goes out with the response
# CORS is enforced by the browser using the destination server's response headers
# so say someone is on a malicious site and it requests an API then that API should only allow its trusted frontend's origin
# so the browser will block the malicious sites JavaScript from reading the response
# in the other scenario where a frontend requests a malicious server,
# that server will prolly allow any origin so CORS won't protect the frontend
# from trusting it basically the frontend must choose which servers to contact and what data to send them to keep safe
# CORS isn't authentication so other origins can contact the backend
# For a cross origin PUT or DELETE a trustworthy browser first sends an OPTIONS preflight request unless one is cached 
# if allowed it sends the actual request but a malicious browser would skip this check
# when someone is logged into a website their browser may already have a session cookie that authenticates requests to that website
# thats when if they visit a malicious site a trustworthy browser security protections matter
# a malicious browser can ignore CORS so the backend must also check authentication and authorization regardless of browser thats whats stops requests from flying in
# but remember a malicious browser could misuse a logged-in user's session or credentials already in that browser.
# the fundamental limit for the server is once a server sends information to a user's browser it cant guarantee that a malicious browser will keep that information private
# CORS protects browser users and authentication and authorization protect the data on the server.
# the frontend is the HTML, CSS, and JavaScript the browser loads to display and run the website.
# its whats returned normally from the initial HTTP request 

# the functions below sit between my lamabda handlers and the outside world
# in this case lambda handler is the main function that aws lambda runs when a request comes in
# basically its the entry point of your lambda function when aws receives the request it starts by calling the handler
# the response of the lambda handler is to receive the request/event then run log, and return a result
# the outside world is anything outside of the lambda function

# success sits between lambda handler and outside world bc now lambda handlers do the work and this function
# then translates the results into a format that API gateway and frontend can understand
def success(body: dict, status_code: int = 200) -> dict:
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS.copy(),  # use .copy() here so not a reference to memory that could later be changed
        "body": json.dumps(body), # json.dumps() converts a python obj into a JSON stirng
    }

    # In C, assignment usually makes a copy automatically for ordinary values 
    # like int a = 5 then int b = a then b = 10 so a = 5 still so you don't need .copy()
    # obviously C has pointer logic which i understand
    # Python is different because everything is an object and variables are references to objects
    # in C variable x literally stores integer value 5 if you do int y = x now variable y literally stores 5
    # in python variables dont hold the value itself instead a python integer object is created somewhere in memory
    # so variable x stores a reference to integer object 5 so int y = x, variable y stores reference to that same integer 5 object


# this function takes one of the application exceptions and turns it into a front end response
def error(sfi_error: SFIError) -> dict:
    return success(  
        body=sfi_error.to_dict(),
        status_code=sfi_error.status_code,
    )  # formatted ready for front end

# say frontend requests 20 files dynamoDB returns those 20 files and a continuation key for where it stopped
# if the frontend wants the next 20 files then it can send the key back to the lambda handler which passes it to 
# dynanmoDB so the query can continue from that point
# the lambda handler calls paginated() on the way out back to the frontend after fetching dynamoDB records
# **extra is pythons way of sayin accept any addition named arguments and put them into a dictionary
# remember *args f(1,2,3) printing args would output (1,2,3)
# so **extra collects key,value arguments if not raises error
def paginated(items: list, last_key=None, **extra) -> dict:
    body = {
        "items": items,
        "count": len(items), # counts the fetched records
    }

    if last_key is not None:
        body["lastKey"] = last_key

    # dictionary syntax is dictionary[key] = value so 
    # "lastKey" : {"fileID": def456} for example is added to body

    body.update(extra) # like a for loop adding key value pairs
    # if key already exists the value is overriden
    return success(body)  # formatted ready for front end

# unlike ones above this is called near beginning of handler when request initiated
# event is the request information API gateway passes to lambda
def extract_user_id(event: dict) -> str:
    try: # thers a nested path trying to get to "sub" which is authenticated users identifier
        user_id = event["requestContext"]["authorizer"]["claims"]["sub"]
    except (KeyError, TypeError):  # except catches the lookup error and raise throws my error
        raise ValidationError("Missing user identity") from None

    # string is required and contains something beside whitespace
    # in python if "": always evaluates as false so its block never runs therefore we use not
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValidationError("Missing user identity")

    return user_id