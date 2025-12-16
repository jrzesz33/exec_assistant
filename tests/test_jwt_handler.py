"""Unit tests for JWT token handler."""

import time
from datetime import timedelta

import pytest

from exec_assistant.shared.jwt_handler import JWTHandler, TokenPayload


class TestJWTHandler:
    """Tests for JWTHandler."""

    @pytest.fixture
    def handler(self) -> JWTHandler:
        """Create test JWT handler."""
        return JWTHandler(
            secret_key="test-secret-key-12345",
            algorithm="HS256",
            access_token_expire_minutes=60,
            refresh_token_expire_days=30,
        )

    def test_create_access_token(self, handler: JWTHandler) -> None:
        """Test creating access token."""
        token = handler.create_access_token(
            user_id="user-123",
            email="test@example.com",
        )

        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_refresh_token(self, handler: JWTHandler) -> None:
        """Test creating refresh token."""
        token = handler.create_refresh_token(
            user_id="user-456",
            email="user@example.com",
        )

        assert isinstance(token, str)
        assert len(token) > 0

    def test_verify_access_token(self, handler: JWTHandler) -> None:
        """Test verifying access token."""
        token = handler.create_access_token(
            user_id="user-789",
            email="verify@example.com",
        )

        payload = handler.verify_token(token, expected_type="access")

        assert payload.sub == "user-789"
        assert payload.email == "verify@example.com"
        assert payload.token_type == "access"

    def test_verify_refresh_token(self, handler: JWTHandler) -> None:
        """Test verifying refresh token."""
        token = handler.create_refresh_token(
            user_id="user-999",
            email="refresh@example.com",
        )

        payload = handler.verify_token(token, expected_type="refresh")

        assert payload.sub == "user-999"
        assert payload.email == "refresh@example.com"
        assert payload.token_type == "refresh"

    def test_verify_token_without_type_check(self, handler: JWTHandler) -> None:
        """Test verifying token without checking type."""
        access_token = handler.create_access_token(user_id="user-abc")
        refresh_token = handler.create_refresh_token(user_id="user-xyz")

        # Both should verify without type check
        payload1 = handler.verify_token(access_token)
        payload2 = handler.verify_token(refresh_token)

        assert payload1.sub == "user-abc"
        assert payload2.sub == "user-xyz"

    def test_verify_token_wrong_type_raises_error(self, handler: JWTHandler) -> None:
        """Test verifying token with wrong type raises error."""
        access_token = handler.create_access_token(user_id="user-123")

        # Try to verify access token as refresh token
        with pytest.raises(ValueError, match="Invalid token type"):
            handler.verify_token(access_token, expected_type="refresh")

    def test_verify_expired_token(self, handler: JWTHandler) -> None:
        """Test verifying expired token."""
        # Create token that expires immediately
        token = handler.create_access_token(
            user_id="user-expired",
            expires_delta=timedelta(milliseconds=1),
        )

        # Wait for token to expire
        time.sleep(0.01)

        # Should raise error for expired token
        with pytest.raises(ValueError, match="Token has expired"):
            handler.verify_token(token)

    def test_verify_invalid_token(self, handler: JWTHandler) -> None:
        """Test verifying invalid token."""
        with pytest.raises(ValueError, match="Invalid token"):
            handler.verify_token("not-a-valid-token")

    def test_verify_token_with_wrong_secret(self, handler: JWTHandler) -> None:
        """Test verifying token with wrong secret."""
        # Create token with one secret
        token = handler.create_access_token(user_id="user-123")

        # Try to verify with different secret
        handler2 = JWTHandler(secret_key="different-secret")

        with pytest.raises(ValueError):
            handler2.verify_token(token)

    def test_refresh_access_token(self, handler: JWTHandler) -> None:
        """Test refreshing access token from refresh token."""
        # Create refresh token
        refresh_token = handler.create_refresh_token(
            user_id="user-refresh",
            email="refresh@example.com",
        )

        # Use it to get new access token
        new_access_token = handler.refresh_access_token(refresh_token)

        # Verify new access token
        payload = handler.verify_token(new_access_token, expected_type="access")

        assert payload.sub == "user-refresh"
        assert payload.email == "refresh@example.com"
        assert payload.token_type == "access"

    def test_refresh_access_token_with_wrong_token_type(
        self,
        handler: JWTHandler,
    ) -> None:
        """Test refreshing with access token (should fail)."""
        # Create access token (not refresh)
        access_token = handler.create_access_token(user_id="user-123")

        # Try to use it as refresh token
        with pytest.raises(ValueError, match="Invalid token type"):
            handler.refresh_access_token(access_token)

    def test_get_user_id_from_token(self, handler: JWTHandler) -> None:
        """Test extracting user ID from token."""
        token = handler.create_access_token(user_id="user-extract")

        user_id = handler.get_user_id_from_token(token)

        assert user_id == "user-extract"

    def test_get_user_id_from_invalid_token(self, handler: JWTHandler) -> None:
        """Test extracting user ID from invalid token."""
        with pytest.raises(ValueError):
            handler.get_user_id_from_token("invalid-token")

    def test_is_token_expired_false(self, handler: JWTHandler) -> None:
        """Test checking if token is expired (not expired)."""
        token = handler.create_access_token(user_id="user-123")

        is_expired = handler.is_token_expired(token)

        assert is_expired is False

    def test_is_token_expired_true(self, handler: JWTHandler) -> None:
        """Test checking if token is expired (expired)."""
        # Create token that expires immediately
        token = handler.create_access_token(
            user_id="user-expired",
            expires_delta=timedelta(milliseconds=1),
        )

        # Wait for expiration
        time.sleep(0.01)

        is_expired = handler.is_token_expired(token)

        assert is_expired is True

    def test_token_payload_model(self) -> None:
        """Test TokenPayload model."""
        payload = TokenPayload(
            sub="user-123",
            exp=1234567890,
            iat=1234567800,
            token_type="access",
            email="test@example.com",
        )

        assert payload.sub == "user-123"
        assert payload.token_type == "access"
        assert payload.email == "test@example.com"


class TestCreateJWTHandlerFromEnv:
    """Tests for create_jwt_handler_from_env helper."""

    def test_create_from_env_success(self) -> None:
        """Test creating handler from environment variables."""
        import os

        # Set environment variables
        os.environ["JWT_SECRET_KEY"] = "env-secret-key"
        os.environ["JWT_ALGORITHM"] = "HS256"
        os.environ["JWT_ACCESS_TOKEN_EXPIRE_MINUTES"] = "120"
        os.environ["JWT_REFRESH_TOKEN_EXPIRE_DAYS"] = "60"

        from exec_assistant.shared.jwt_handler import create_jwt_handler_from_env

        handler = create_jwt_handler_from_env()

        assert handler.secret_key == "env-secret-key"
        assert handler.algorithm == "HS256"
        assert handler.access_token_expire_minutes == 120
        assert handler.refresh_token_expire_days == 60

        # Cleanup
        del os.environ["JWT_SECRET_KEY"]
        del os.environ["JWT_ALGORITHM"]
        del os.environ["JWT_ACCESS_TOKEN_EXPIRE_MINUTES"]
        del os.environ["JWT_REFRESH_TOKEN_EXPIRE_DAYS"]

    def test_create_from_env_missing_secret(self) -> None:
        """Test error when JWT_SECRET_KEY is missing."""
        from exec_assistant.shared.jwt_handler import create_jwt_handler_from_env

        with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
            create_jwt_handler_from_env()

    def test_create_from_env_with_defaults(self) -> None:
        """Test creating handler with default values."""
        import os

        # Only set required variable
        os.environ["JWT_SECRET_KEY"] = "test-secret"

        from exec_assistant.shared.jwt_handler import create_jwt_handler_from_env

        handler = create_jwt_handler_from_env()

        # Should use defaults
        assert handler.algorithm == "HS256"
        assert handler.access_token_expire_minutes == 60
        assert handler.refresh_token_expire_days == 30

        # Cleanup
        del os.environ["JWT_SECRET_KEY"]


class TestJWTIntegration:
    """Integration tests for JWT token workflow."""

    def test_full_auth_workflow(self) -> None:
        """Test complete authentication workflow."""
        handler = JWTHandler(secret_key="integration-test-secret")

        # 1. User logs in, get tokens
        access_token = handler.create_access_token(
            user_id="user-workflow",
            email="workflow@example.com",
        )
        refresh_token = handler.create_refresh_token(
            user_id="user-workflow",
            email="workflow@example.com",
        )

        # 2. Verify access token
        access_payload = handler.verify_token(access_token, expected_type="access")
        assert access_payload.sub == "user-workflow"

        # 3. Access token expires (simulate)
        # Create expired access token
        expired_access = handler.create_access_token(
            user_id="user-workflow",
            expires_delta=timedelta(milliseconds=1),
        )
        time.sleep(0.01)

        # 4. Try to use expired token (should fail)
        with pytest.raises(ValueError, match="expired"):
            handler.verify_token(expired_access)

        # 5. Use refresh token to get new access token
        new_access_token = handler.refresh_access_token(refresh_token)

        # 6. Verify new access token works
        new_payload = handler.verify_token(new_access_token, expected_type="access")
        assert new_payload.sub == "user-workflow"
