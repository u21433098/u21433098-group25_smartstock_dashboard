"""Errors raised by the services layer.

Every error is a ValueError, so existing `except ValueError` code keeps working.
Each one also carries the HTTP status an API should answer with, and (for bad
input) the name of the field that was wrong, so one central error handler can
turn any of them into a consistent JSON error.
"""


class ServiceError(ValueError):
    """Base class. `status` is the matching HTTP status code."""
    status = 400

    def __init__(self, message, field=None):
        super().__init__(message)
        self.message = message
        self.field = field

    def to_dict(self):
        error = {"status": self.status, "message": self.message}
        if self.field:
            error["field"] = self.field
        return error


class ValidationError(ServiceError):
    """The input was missing, the wrong type, or out of range."""
    status = 400


class NotFoundError(ServiceError):
    """The machine, product, user or stock row does not exist."""
    status = 404


class PermissionDenied(ServiceError):
    """The logged-in user's role does not allow this action."""
    status = 403


class ConflictError(ServiceError):
    """The change clashes with existing data (e.g. an email that is already taken)."""
    status = 409
