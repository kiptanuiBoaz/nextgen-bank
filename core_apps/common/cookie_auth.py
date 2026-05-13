from typing import Optional, Tuple

from django.conf import settings
from loguru import logger
from rest_framework.request import Request
from rest_framework_simplejwt.authentication import AuthUser, JWTAuthentication
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import Token


class CookieAuthentication(JWTAuthentication):
    """
    Custom JWT authentication class that supports authentication
    using either:
    1. Authorization header (default JWT behavior)
    2. HTTP-only cookie fallback
    """

    def authenticate(self, request: Request) -> Optional[Tuple[AuthUser, Token]]:
        """
        Attempt to authenticate the request using a JWT token.

        Priority:
        1. Authorization header
        2. Cookie-based token

        Returns:
            Tuple[AuthUser, Token] if authentication succeeds,
            otherwise None.
        """

        # Extract Authorization header if present
        header = self.get_header(request)

        # Default token value
        raw_token = None

        # Try getting token from Authorization header
        if header is not None:
            raw_token = self.get_raw_token(header)

        # Fallback to cookie-based authentication
        elif settings.COOKIE_NAME in request.COOKIES:
            raw_token = request.COOKIES.get(settings.COOKIE_NAME)

        # Validate token if one was found
        if raw_token is not None:
            try:
                # Decode and validate JWT token
                validated_token = self.get_validated_token(raw_token)

                # Return authenticated user and validated token
                return self.get_user(validated_token), validated_token

            except TokenError as e:
                # Log invalid/expired token errors for debugging
                logger.error(f"Token validation error: {str(e)}")

        # No valid authentication credentials found
        return None
