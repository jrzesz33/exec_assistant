"""JWT token management for Executive Assistant.

Handles creation, verification, and refresh of JSON Web Tokens for authentication.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TokenPayload(BaseModel):
    """JWT token payload."""

    sub: str = Field(..., description="Subject (user_id)")
    exp: int = Field(..., description="Expiration time (Unix timestamp)")
    iat: int = Field(..., description="Issued at (Unix timestamp)")
    token_type: str = Field(..., description="Token type: 'access' or 'refresh'")
    email: str | None = Field(None, description="User email (optional)")


class JWTHandler:
    """Handle JWT token creation and verification.

    Uses HS256 (HMAC with SHA-256) for development.
    For production, consider using RS256 (RSA) with KMS-managed keys.
    """

    def __init__(
        self,
        secret_key: str,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 60,
        refresh_token_expire_days: int = 30,
    ) -> None:
        """Initialize JWT handler.

        Args:
            secret_key: Secret key for signing tokens
            algorithm: JWT algorithm (HS256 or RS256)
            access_token_expire_minutes: Access token expiration in minutes
            refresh_token_expire_days: Refresh token expiration in days
        """
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.access_token_expire_minutes = access_token_expire_minutes
        self.refresh_token_expire_days = refresh_token_expire_days

        # Lazy import to avoid dependency issues if PyJWT not installed
        try:
            import jwt

            self.jwt = jwt
        except ImportError as e:
            msg = "PyJWT is required for JWT handling. Install with: pip install pyjwt"
            raise ImportError(msg) from e

    def create_access_token(
        self,
        user_id: str,
        email: str | None = None,
        expires_delta: timedelta | None = None,
    ) -> str:
        """Create JWT access token.

        Args:
            user_id: User identifier
            email: User email (optional)
            expires_delta: Custom expiration time (overrides default)

        Returns:
            Encoded JWT token string
        """
        if expires_delta is None:
            expires_delta = timedelta(minutes=self.access_token_expire_minutes)

        now = datetime.now(UTC)
        expire = now + expires_delta

        payload: dict[str, Any] = {
            "sub": user_id,
            "exp": int(expire.timestamp()),
            "iat": int(now.timestamp()),
            "token_type": "access",
        }

        if email:
            payload["email"] = email

        token = self.jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

        logger.debug(
            "user_id=<%s>, expires_in=<%d> | created access token",
            user_id,
            int(expires_delta.total_seconds()),
        )

        return token

    def create_refresh_token(
        self,
        user_id: str,
        email: str | None = None,
        expires_delta: timedelta | None = None,
    ) -> str:
        """Create JWT refresh token.

        Args:
            user_id: User identifier
            email: User email (optional)
            expires_delta: Custom expiration time (overrides default)

        Returns:
            Encoded JWT token string
        """
        if expires_delta is None:
            expires_delta = timedelta(days=self.refresh_token_expire_days)

        now = datetime.now(UTC)
        expire = now + expires_delta

        payload: dict[str, Any] = {
            "sub": user_id,
            "exp": int(expire.timestamp()),
            "iat": int(now.timestamp()),
            "token_type": "refresh",
        }

        if email:
            payload["email"] = email

        token = self.jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

        logger.debug(
            "user_id=<%s>, expires_in=<%d> | created refresh token",
            user_id,
            int(expires_delta.total_seconds()),
        )

        return token

    def verify_token(self, token: str, expected_type: str | None = None) -> TokenPayload:
        """Verify and decode JWT token.

        Args:
            token: JWT token string to verify
            expected_type: Expected token type ('access' or 'refresh'), None to skip check

        Returns:
            Decoded token payload

        Raises:
            ValueError: If token is invalid, expired, or wrong type
        """
        try:
            payload = self.jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
            )

            # Validate payload structure
            token_payload = TokenPayload(**payload)

            # Check token type if specified
            if expected_type and token_payload.token_type != expected_type:
                msg = (
                    f"Invalid token type: expected {expected_type}, got {token_payload.token_type}"
                )
                logger.warning(
                    "expected_type=<%s>, actual_type=<%s> | token type mismatch",
                    expected_type,
                    token_payload.token_type,
                )
                raise ValueError(msg)

            logger.debug(
                "user_id=<%s>, token_type=<%s> | token verified successfully",
                token_payload.sub,
                token_payload.token_type,
            )

            return token_payload

        except self.jwt.ExpiredSignatureError as e:
            logger.warning("token_status=<expired> | token has expired")
            raise ValueError("Token has expired") from e

        except self.jwt.InvalidTokenError as e:
            logger.warning("token_status=<invalid> | invalid token: %s", str(e))
            raise ValueError(f"Invalid token: {e}") from e

        except Exception as e:
            logger.error("error=<%s> | failed to verify token", str(e))
            raise ValueError(f"Failed to verify token: {e}") from e

    def refresh_access_token(self, refresh_token: str) -> str:
        """Generate new access token from refresh token.

        Args:
            refresh_token: Valid refresh token

        Returns:
            New access token

        Raises:
            ValueError: If refresh token is invalid or expired
        """
        # Verify refresh token
        payload = self.verify_token(refresh_token, expected_type="refresh")

        # Create new access token
        new_access_token = self.create_access_token(
            user_id=payload.sub,
            email=payload.email,
        )

        logger.info("user_id=<%s> | refreshed access token", payload.sub)

        return new_access_token

    def get_user_id_from_token(self, token: str) -> str:
        """Extract user ID from token without full verification.

        Useful when you just need the user ID and will validate permissions separately.

        Args:
            token: JWT token

        Returns:
            User ID from token

        Raises:
            ValueError: If token cannot be decoded
        """
        try:
            # Decode without verification (just parse)
            payload = self.jwt.decode(
                token,
                options={"verify_signature": False},
            )
            return payload.get("sub", "")

        except Exception as e:
            logger.error("error=<%s> | failed to extract user id from token", str(e))
            raise ValueError(f"Failed to extract user ID: {e}") from e

    def is_token_expired(self, token: str) -> bool:
        """Check if token is expired without verifying signature.

        Args:
            token: JWT token

        Returns:
            True if token is expired
        """
        try:
            payload = self.jwt.decode(
                token,
                options={"verify_signature": False},
            )
            exp = payload.get("exp", 0)
            now = datetime.now(UTC).timestamp()
            return now > exp

        except Exception:
            # If we can't decode, consider it expired
            return True


def create_jwt_handler_from_env() -> JWTHandler:
    """Create JWT handler from environment variables.

    Returns:
        Configured JWTHandler

    Raises:
        ValueError: If required environment variables are missing
    """
    import os

    secret_key = os.environ.get("JWT_SECRET_KEY")
    if not secret_key:
        msg = "JWT_SECRET_KEY environment variable is required"
        raise ValueError(msg)

    algorithm = os.environ.get("JWT_ALGORITHM", "HS256")
    access_token_expire = int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    refresh_token_expire = int(os.environ.get("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "30"))

    return JWTHandler(
        secret_key=secret_key,
        algorithm=algorithm,
        access_token_expire_minutes=access_token_expire,
        refresh_token_expire_days=refresh_token_expire,
    )
