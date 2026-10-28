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

# honestly haven't written in python in a while so going to note take syntax
# class defines a new class, SFIError is the class name, (Exception) means it inherits from pythons class
# : starts the class body
# SFIError behaves like an Exception bc it has all its features
class SFIError(Exception):
    """Base exception for errors that handlers can return to API clients."""

    # def defines a function
    # __init__ is a special method in python to initialize a newly created object
    # the ( starts its parameters
    # self refers to the specific object currently being created and python programmers use self
    # in an instance method you gotta have a first parameter that refers to the object being worked on 
    # :str is a type hint so tells programmers and tools variable is expected to be a string but python doesnt enforce them
    # the reason python does this is bc its meant to be flexible at runtime unlike C which meant to catch mistakes before program runs
    # for example a + b with type hints would then work for numbers strings etc
    # by definition python is a dynamically typed language so types are determined at runtime
  
    def __init__(
        self,
        message: str,
        status_code: int = 500,     # = 500 sets 500 as default if caller doesn't include
        error_code: str = "INTERNAL_ERROR",   # creates a default like above
    ) -> None:      # -> none is a return type meaning the method returns no meaningful value and : starts method body
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code

        # super() calls the init from the inherited Exception
        # then other lines allow values to be stored on object

    def to_dict(self) -> dict[str, str]:
        """Return the public error code and message."""
        return {
            "error": self.error_code,
            "message": self.message,
        }

    # -> dict[str, str] is a return type hint similar to the parameter type hint but for return
    # return is whats sent back to caller and the {} creates a dictionary
    # a dictionary stores key value pairs
    # dictionaries are good bc can be easily converted to JSON
    # dict[str, str] doesn't put a limit on the amount of key value pairs its hinting the types of the key value pair
    # because you could have key value pair with like string then int

# ok below we have subclasses of SFIError which are specific types of errors having their own 
# status code and error code, message is still given
# the to_dict() as I know inheritance works is a part of all these classes

class ValidationError(SFIError):
    """The request contains missing or invalid input."""

    # that line above is a docstring and its placed immediately in a class or method
    # its purpose is to explain whatever its inside of class or method
    # python will actually store it and you can assess with object.__doc__ or with help()

    def __init__(self, message: str) -> None:
        super().__init__(
            message=message,
            status_code=400,
            error_code="VALIDATION_ERROR",
        )


class NotFoundError(SFIError):
    """The requested resource does not exist."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message=message,
            status_code=404,
            error_code="NOT_FOUND",
        )


class AuthorizationError(SFIError):
    """The caller does not have permission to access the resource."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message=message,
            status_code=403,
            error_code="FORBIDDEN",
        )


class ConflictError(SFIError):
    """The operation conflicts with the resource's current state."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message=message,
            status_code=409,
            error_code="CONFLICT",
        )


class ProcessingError(SFIError):
    """The file could not be processed."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message=message,
            status_code=422,
            error_code="PROCESSING_FAILED",
        )

  # just note method is a function that belongs to a class
  # function is defined outside of a class, and its scope is the file/namespace
  # only can access its paramters and variables it can reach
  # methods are called through an object so can access data stored on object
  # functions obviously dont use self because theres no object associated with it
  # @staticmethod in a method makes it behave much more like a normal function that just happens to be inside a class

