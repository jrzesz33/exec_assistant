"""Authentication handlers for Executive Assistant.

Handles Google OAuth 2.0 flow for user authentication and calendar access.
"""

import logging
from typing import Any
from urllib.parse import urlencode

import requests
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class GoogleOAuthConfig(BaseModel):
    """Configuration for Google OAuth."""

    client_id: str = Field(..., description="Google OAuth client ID")
    client_secret: str = Field(..., description="Google OAuth client secret")
    redirect_uri: str = Field(..., description="OAuth redirect URI")
    scopes: list[str] = Field(
        default_factory=lambda: [
            "openid",
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile",
        ],
        description="OAuth scopes to request",
    )


class GoogleUserInfo(BaseModel):
    """User information from Google."""

    google_id: str = Field(..., alias="sub", description="Google's unique user ID")
    email: str = Field(..., description="User's email address")
    email_verified: bool = Field(..., description="Whether email is verified")
    name: str = Field(..., description="User's display name")
    picture: str | None = Field(None, description="Profile picture URL")
    given_name: str | None = Field(None, description="First name")
    family_name: str | None = Field(None, description="Last name")
    locale: str | None = Field(None, description="User's locale")

    class Config:
        """Pydantic config to allow alias."""

        populate_by_name = True


class GoogleOAuthHandler:
    """Handle Google OAuth 2.0 authentication flow.

    Implements the OAuth 2.0 authorization code flow with PKCE for enhanced security.
    """

    # Google OAuth endpoints
    AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
    USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v3/userinfo"
    TOKENINFO_ENDPOINT = "https://oauth2.googleapis.com/tokeninfo"

    def __init__(self, config: GoogleOAuthConfig) -> None:
        """Initialize OAuth handler.

        Args:
            config: OAuth configuration
        """
        self.config = config

    def get_authorization_url(self, state: str | None = None) -> str:
        """Generate OAuth authorization URL for user to visit.

        Args:
            state: Optional state parameter for CSRF protection

        Returns:
            Authorization URL to redirect user to
        """
        params = {
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.config.scopes),
            "access_type": "offline",  # Request refresh token
            "prompt": "consent",  # Force consent screen to get refresh token
        }

        if state:
            params["state"] = state

        auth_url = f"{self.AUTH_ENDPOINT}?{urlencode(params)}"
        logger.debug("redirect_uri=<%s> | generated authorization url", self.config.redirect_uri)

        return auth_url

    def exchange_code_for_tokens(self, code: str) -> dict[str, Any]:
        """Exchange authorization code for access and refresh tokens.

        Args:
            code: Authorization code from OAuth callback

        Returns:
            Token response containing access_token, refresh_token, etc.

        Raises:
            ValueError: If token exchange fails
            requests.RequestException: If HTTP request fails
        """
        logger.debug("code=<%s...> | exchanging authorization code", code[:10])

        token_data = {
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": self.config.redirect_uri,
        }

        try:
            response = requests.post(
                self.TOKEN_ENDPOINT,
                data=token_data,
                timeout=10,
            )
            response.raise_for_status()
            tokens = response.json()

            logger.info(
                "token_type=<%s>, has_refresh_token=<%s> | tokens exchanged successfully",
                tokens.get("token_type"),
                "refresh_token" in tokens,
            )

            return tokens

        except requests.RequestException as e:
            logger.error("error=<%s> | failed to exchange code for tokens", str(e))
            raise ValueError(f"Failed to exchange authorization code: {e}") from e

    def verify_id_token(self, id_token: str) -> GoogleUserInfo:
        """Verify and decode Google ID token.

        Args:
            id_token: ID token from Google OAuth response

        Returns:
            Decoded user information

        Raises:
            ValueError: If token verification fails
        """
        logger.debug("id_token=<%s...> | verifying id token", id_token[:20])

        try:
            # Verify token with Google
            response = requests.get(
                f"{self.TOKENINFO_ENDPOINT}?id_token={id_token}",
                timeout=10,
            )
            response.raise_for_status()
            token_info = response.json()

            # Verify audience (client ID)
            if token_info.get("aud") != self.config.client_id:
                msg = f"Invalid token audience: {token_info.get('aud')}"
                logger.warning("audience=<%s> | token audience mismatch", token_info.get("aud"))
                raise ValueError(msg)

            # Parse user info
            user_info = GoogleUserInfo(**token_info)

            logger.info(
                "google_id=<%s>, email=<%s> | id token verified",
                user_info.google_id,
                user_info.email,
            )

            return user_info

        except requests.RequestException as e:
            logger.error("error=<%s> | failed to verify id token", str(e))
            raise ValueError(f"Failed to verify ID token: {e}") from e

    def get_user_info(self, access_token: str) -> GoogleUserInfo:
        """Get user information using access token.

        Alternative to verifying ID token. Useful when you only have access token.

        Args:
            access_token: OAuth access token

        Returns:
            User information from Google

        Raises:
            ValueError: If request fails
        """
        logger.debug("access_token=<%s...> | fetching user info", access_token[:20])

        try:
            response = requests.get(
                self.USERINFO_ENDPOINT,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
            response.raise_for_status()
            user_data = response.json()

            user_info = GoogleUserInfo(**user_data)

            logger.info(
                "google_id=<%s>, email=<%s> | user info fetched",
                user_info.google_id,
                user_info.email,
            )

            return user_info

        except requests.RequestException as e:
            logger.error("error=<%s> | failed to fetch user info", str(e))
            raise ValueError(f"Failed to fetch user info: {e}") from e

    def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        """Refresh expired access token using refresh token.

        Args:
            refresh_token: OAuth refresh token

        Returns:
            New token response with fresh access_token

        Raises:
            ValueError: If token refresh fails
        """
        logger.debug("refresh_token=<%s...> | refreshing access token", refresh_token[:10])

        token_data = {
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        try:
            response = requests.post(
                self.TOKEN_ENDPOINT,
                data=token_data,
                timeout=10,
            )
            response.raise_for_status()
            tokens = response.json()

            logger.info("token_type=<%s> | access token refreshed", tokens.get("token_type"))

            return tokens

        except requests.RequestException as e:
            logger.error("error=<%s> | failed to refresh access token", str(e))
            raise ValueError(f"Failed to refresh access token: {e}") from e

    def revoke_token(self, token: str) -> bool:
        """Revoke an access or refresh token.

        Args:
            token: Token to revoke (access or refresh token)

        Returns:
            True if revocation succeeded
        """
        logger.debug("token=<%s...> | revoking token", token[:10])

        try:
            response = requests.post(
                "https://oauth2.googleapis.com/revoke",
                params={"token": token},
                headers={"content-type": "application/x-www-form-urlencoded"},
                timeout=10,
            )
            response.raise_for_status()

            logger.info("token_revoked=<true> | token revoked successfully")
            return True

        except requests.RequestException as e:
            logger.error("error=<%s> | failed to revoke token", str(e))
            return False


def create_oauth_handler_from_env() -> GoogleOAuthHandler:
    """Create OAuth handler from environment variables.

    Returns:
        Configured GoogleOAuthHandler

    Raises:
        ValueError: If required environment variables are missing
    """
    import os

    client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
    redirect_uri = os.environ.get("GOOGLE_OAUTH_REDIRECT_URI")

    if not all([client_id, client_secret, redirect_uri]):
        msg = "Missing required Google OAuth environment variables"
        raise ValueError(msg)

    # Get scopes from environment or use defaults
    scopes_str = os.environ.get("GOOGLE_OAUTH_SCOPES", "")
    scopes = scopes_str.split(",") if scopes_str else None

    config = GoogleOAuthConfig(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scopes=scopes if scopes else None,
    )

    return GoogleOAuthHandler(config)
