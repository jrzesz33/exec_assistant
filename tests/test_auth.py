"""Unit tests for authentication handlers."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from exec_assistant.shared.auth import (
    GoogleOAuthConfig,
    GoogleOAuthHandler,
    GoogleUserInfo,
)


class TestGoogleOAuthConfig:
    """Tests for GoogleOAuthConfig model."""

    def test_create_config(self) -> None:
        """Test creating OAuth config."""
        config = GoogleOAuthConfig(
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://app.example.com/auth/callback",
        )
        assert config.client_id == "test-client-id"
        assert config.client_secret == "test-secret"
        assert config.redirect_uri == "https://app.example.com/auth/callback"
        assert "openid" in config.scopes

    def test_config_with_custom_scopes(self) -> None:
        """Test config with custom scopes."""
        config = GoogleOAuthConfig(
            client_id="client",
            client_secret="secret",
            redirect_uri="https://app.com/callback",
            scopes=["openid", "email", "calendar"],
        )
        assert len(config.scopes) == 3
        assert "calendar" in config.scopes


class TestGoogleUserInfo:
    """Tests for GoogleUserInfo model."""

    def test_parse_user_info(self) -> None:
        """Test parsing user info from Google response."""
        data = {
            "sub": "google-123",
            "email": "user@example.com",
            "email_verified": True,
            "name": "Test User",
            "picture": "https://example.com/photo.jpg",
            "given_name": "Test",
            "family_name": "User",
            "locale": "en",
        }
        user_info = GoogleUserInfo(**data)

        assert user_info.google_id == "google-123"
        assert user_info.email == "user@example.com"
        assert user_info.email_verified is True
        assert user_info.name == "Test User"


class TestGoogleOAuthHandler:
    """Tests for GoogleOAuthHandler."""

    @pytest.fixture
    def config(self) -> GoogleOAuthConfig:
        """Create test config."""
        return GoogleOAuthConfig(
            client_id="test-client-id",
            client_secret="test-client-secret",
            redirect_uri="https://app.example.com/auth/callback",
        )

    @pytest.fixture
    def handler(self, config: GoogleOAuthConfig) -> GoogleOAuthHandler:
        """Create test OAuth handler."""
        return GoogleOAuthHandler(config)

    def test_get_authorization_url(self, handler: GoogleOAuthHandler) -> None:
        """Test generating authorization URL."""
        url = handler.get_authorization_url()

        assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth")
        assert "client_id=test-client-id" in url
        assert "redirect_uri=" in url
        assert "scope=" in url
        assert "access_type=offline" in url

    def test_get_authorization_url_with_state(
        self,
        handler: GoogleOAuthHandler,
    ) -> None:
        """Test authorization URL with state parameter."""
        url = handler.get_authorization_url(state="random-state-123")

        assert "state=random-state-123" in url

    @patch("requests.post")
    def test_exchange_code_for_tokens_success(
        self,
        mock_post: MagicMock,
        handler: GoogleOAuthHandler,
    ) -> None:
        """Test successful token exchange."""
        # Mock successful response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "test-access-token",
            "refresh_token": "test-refresh-token",
            "token_type": "Bearer",
            "expires_in": 3600,
            "id_token": "test-id-token",
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        tokens = handler.exchange_code_for_tokens("auth-code-123")

        assert tokens["access_token"] == "test-access-token"
        assert tokens["refresh_token"] == "test-refresh-token"
        assert "id_token" in tokens

    @patch("requests.post")
    def test_exchange_code_for_tokens_failure(
        self,
        mock_post: MagicMock,
        handler: GoogleOAuthHandler,
    ) -> None:
        """Test failed token exchange."""
        mock_post.side_effect = requests.RequestException("Network error")

        with pytest.raises(ValueError, match="Failed to exchange authorization code"):
            handler.exchange_code_for_tokens("bad-code")

    @patch("requests.get")
    def test_verify_id_token_success(
        self,
        mock_get: MagicMock,
        handler: GoogleOAuthHandler,
    ) -> None:
        """Test successful ID token verification."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "sub": "google-user-123",
            "email": "user@example.com",
            "email_verified": True,
            "name": "Test User",
            "aud": "test-client-id",  # Matches our config
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        user_info = handler.verify_id_token("test-id-token")

        assert user_info.google_id == "google-user-123"
        assert user_info.email == "user@example.com"
        assert user_info.email_verified is True

    @patch("requests.get")
    def test_verify_id_token_wrong_audience(
        self,
        mock_get: MagicMock,
        handler: GoogleOAuthHandler,
    ) -> None:
        """Test ID token verification with wrong audience."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "sub": "google-user-123",
            "email": "user@example.com",
            "email_verified": True,
            "name": "Test User",
            "aud": "wrong-client-id",  # Wrong audience!
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        with pytest.raises(ValueError, match="Invalid token audience"):
            handler.verify_id_token("test-id-token")

    @patch("requests.get")
    def test_get_user_info(
        self,
        mock_get: MagicMock,
        handler: GoogleOAuthHandler,
    ) -> None:
        """Test fetching user info with access token."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "sub": "google-456",
            "email": "test@example.com",
            "email_verified": True,
            "name": "Another User",
            "picture": "https://example.com/pic.jpg",
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        user_info = handler.get_user_info("access-token-123")

        assert user_info.google_id == "google-456"
        assert user_info.email == "test@example.com"
        assert user_info.picture == "https://example.com/pic.jpg"

    @patch("requests.post")
    def test_refresh_access_token(
        self,
        mock_post: MagicMock,
        handler: GoogleOAuthHandler,
    ) -> None:
        """Test refreshing access token."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "new-access-token",
            "token_type": "Bearer",
            "expires_in": 3600,
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        tokens = handler.refresh_access_token("refresh-token-123")

        assert tokens["access_token"] == "new-access-token"
        assert tokens["token_type"] == "Bearer"

    @patch("requests.post")
    def test_revoke_token_success(
        self,
        mock_post: MagicMock,
        handler: GoogleOAuthHandler,
    ) -> None:
        """Test successfully revoking token."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        result = handler.revoke_token("token-to-revoke")

        assert result is True

    @patch("requests.post")
    def test_revoke_token_failure(
        self,
        mock_post: MagicMock,
        handler: GoogleOAuthHandler,
    ) -> None:
        """Test failed token revocation."""
        mock_post.side_effect = requests.RequestException("Error")

        result = handler.revoke_token("bad-token")

        assert result is False


class TestCreateOAuthHandlerFromEnv:
    """Tests for create_oauth_handler_from_env helper."""

    def test_create_from_env_success(self) -> None:
        """Test creating handler from environment variables."""
        import os

        # Set environment variables
        os.environ["GOOGLE_OAUTH_CLIENT_ID"] = "env-client-id"
        os.environ["GOOGLE_OAUTH_CLIENT_SECRET"] = "env-secret"
        os.environ["GOOGLE_OAUTH_REDIRECT_URI"] = "https://app.com/callback"

        from exec_assistant.shared.auth import create_oauth_handler_from_env

        handler = create_oauth_handler_from_env()

        assert handler.config.client_id == "env-client-id"
        assert handler.config.client_secret == "env-secret"

        # Cleanup
        del os.environ["GOOGLE_OAUTH_CLIENT_ID"]
        del os.environ["GOOGLE_OAUTH_CLIENT_SECRET"]
        del os.environ["GOOGLE_OAUTH_REDIRECT_URI"]

    def test_create_from_env_missing_vars(self) -> None:
        """Test error when environment variables are missing."""
        from exec_assistant.shared.auth import create_oauth_handler_from_env

        with pytest.raises(ValueError, match="Missing required Google OAuth"):
            create_oauth_handler_from_env()
