# wallet/exceptions.py
from rest_framework import status
from rest_framework.exceptions import APIException

class CustomValidationError(APIException):
    """Custom exception for validation errors with a consistent detail format."""
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = {"detail": "An error occurred"}

    def __init__(self, detail):
        """
        Initialize with a custom error message.

        Args:
            detail (str): The error message to include in the response.
        """
        self.detail = {"detail": str(detail)}