"""
backend/layers/shared/python/error_types.py
============================================
Custom exception hierarchy for the SFI platform.

Import in every Lambda handler:
  from error_types import SFIError, ValidationError, NotFoundError, ...

────────────────────────────────────────────────────────────────────────────────
WHAT TO BUILD — implement each class below:
────────────────────────────────────────────────────────────────────────────────

STEP 1 — Base class: SFIError(Exception)
  Fields:  message: str, status_code: int = 500, error_code: str = "INTERNAL_ERROR"
  Method:  to_dict() → {"error": self.error_code, "message": self.message}
  WHY: Every Lambda catch block needs a single exception type it can safely
       serialize to an API Gateway response without leaking stack traces.

STEP 2 — ValidationError(SFIError)
  status_code = 400, error_code = "VALIDATION_ERROR"
  WHY: Bad request bodies (missing fields, wrong types) are common; a dedicated
       subclass lets callers catch only validation failures when needed.

STEP 3 — NotFoundError(SFIError)
  status_code = 404, error_code = "NOT_FOUND"
  WHY: DynamoDB get_item returning no Item is a normal state, not an exception —
       but raising NotFoundError lets the handler stay flat (no nested if-blocks).

STEP 4 — AuthorizationError(SFIError)
  status_code = 403, error_code = "FORBIDDEN"
  WHY: User A must never read User B's files. Raise this when the userId in the
       JWT claim doesn't match the resource owner extracted from DynamoDB.

STEP 5 — ConflictError(SFIError)
  status_code = 409, error_code = "CONFLICT"
  WHY: Trying to confirm an upload that is already PROCESSED or FAILED needs its
       own status code so the frontend can show the right message.

STEP 6 — ProcessingError(SFIError)
  status_code = 422, error_code = "PROCESSING_FAILED"
  WHY: Textract/Rekognition errors during Step Functions execution are unrecoverable
       by the caller; 422 signals the file is bad, not the request.
"""

# TODO: implement SFIError and all subclasses described above
