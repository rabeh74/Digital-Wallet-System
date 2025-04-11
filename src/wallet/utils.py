from django.core.cache import cache
from rest_framework.exceptions import ValidationError
import logging
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)

class IdempotencyChecker:
    """Utility to enforce idempotency using a client-provided Idempotency-Key header."""
    
    CACHE_TIMEOUT = 24 * 60 * 60  # 24 hours
    CACHE_PREFIX = "idempotency_"
    HEADER_NAME = "Idempotency_Key"

    @staticmethod
    def get_key(request):
        """
        Retrieve and validate the idempotency key from the request header.
        
        Args:
            request: HTTP request object.
        
        Returns:
            str: Idempotency key with prefix.
        
        Raises:
            ValidationError: If header is missing or invalid.
        """
        idempotency_key = request.headers.get(IdempotencyChecker.HEADER_NAME)
        if not idempotency_key:
            raise ValidationError({"detail": f"{IdempotencyChecker.HEADER_NAME} header is required"})
        if len(idempotency_key) > 128:  # Arbitrary max length
            raise ValidationError({"detail": f"{IdempotencyChecker.HEADER_NAME} exceeds 128 characters"})
        return f"{IdempotencyChecker.CACHE_PREFIX}{idempotency_key}"

    @staticmethod
    def is_processed(idempotency_key):
        """
        Check if the idempotency key has been processed.
        
        Args:
            idempotency_key: Unique key to check.
        
        Returns:
            bool: True if already processed, False otherwise.
        """
        return cache.get(idempotency_key) is not None

    @staticmethod
    def mark_processed(idempotency_key, response_data):
        """
        Mark the idempotency key as processed, storing the response data.
        
        Args:
            idempotency_key: Unique key to mark.
            response_data: Response data to store (must be serializable).
        """
        try:
            cache.set(idempotency_key, response_data, timeout=IdempotencyChecker.CACHE_TIMEOUT)
            logger.info(f"Marked idempotency key as processed: {idempotency_key}")
        except Exception as e:
            logger.error(f"Failed to cache idempotency key: {str(e)}", exc_info=True)
            raise

    @staticmethod
    def get_processed_response(idempotency_key):
        """
        Retrieve stored response data for a processed key.
        
        Args:
            idempotency_key: Unique key to check.
        
        Returns:
            dict: Stored response data or None if not found.
        """
        return cache.get(idempotency_key)


class IdempotencyMixin:
    """Mixin to enforce idempotency for API views."""

    def enforce_idempotency(self, request, process_func, *args, **kwargs):
        """
        Enforce idempotency for a request, calling the process function if not processed.
        
        Args:
            request: HTTP request object.
            process_func: Function to process the request if not already processed.
            *args, **kwargs: Arguments to pass to process_func.
        
        Returns:
            Response: Either cached response or new response from process_func.
        """
        idempotency_key = IdempotencyChecker.get_key(request)
        
        if IdempotencyChecker.is_processed(idempotency_key):
            stored_response = IdempotencyChecker.get_processed_response(idempotency_key)
            return Response(stored_response, status=status.HTTP_200_OK)
        
        response = process_func(request, *args, **kwargs)
        IdempotencyChecker.mark_processed(idempotency_key, response.data)
        return response