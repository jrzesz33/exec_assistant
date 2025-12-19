"""AWS Lambda handler for authentication endpoints.

Handles Google OAuth login, callback, token refresh, and user info endpoints.
"""

import json
import logging
import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

from exec_assistant.shared.auth import GoogleOAuthConfig, GoogleOAuthHandler
from exec_assistant.shared.jwt_handler import JWTHandler

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource("dynamodb")
secretsmanager = boto3.client("secretsmanager")

# Environment variables
USERS_TABLE_NAME = os.environ.get("USERS_TABLE_NAME", "")
GOOGLE_OAUTH_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
GOOGLE_OAUTH_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")
GOOGLE_OAUTH_REDIRECT_URI = os.environ.get("GOOGLE_OAUTH_REDIRECT_URI", "")
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "")

# Initialize handlers (will be lazy loaded)
_oauth_handler: GoogleOAuthHandler | None = None
_jwt_handler: JWTHandler | None = None


def get_oauth_handler() -> GoogleOAuthHandler:
    """Get or create OAuth handler instance.

    Returns:
        GoogleOAuthHandler instance
    """
    global _oauth_handler
    if _oauth_handler is None:
        config = GoogleOAuthConfig(
            client_id=GOOGLE_OAUTH_CLIENT_ID,
            client_secret=GOOGLE_OAUTH_CLIENT_SECRET,
            redirect_uri=GOOGLE_OAUTH_REDIRECT_URI,
        )
        _oauth_handler = GoogleOAuthHandler(config)
    return _oauth_handler


def get_jwt_handler() -> JWTHandler:
    """Get or create JWT handler instance.

    Returns:
        JWTHandler instance
    """
    global _jwt_handler
    if _jwt_handler is None:
        _jwt_handler = JWTHandler(secret_key=JWT_SECRET_KEY)
    return _jwt_handler


def create_response(
    status_code: int,
    body: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Create API Gateway response.

    Args:
        status_code: HTTP status code
        body: Response body (will be JSON encoded)
        headers: Optional additional headers

    Returns:
        API Gateway response dictionary
    """
    default_headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": FRONTEND_URL or "*",
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    }

    if headers:
        default_headers.update(headers)

    return {
        "statusCode": status_code,
        "headers": default_headers,
        "body": json.dumps(body),
    }


def get_or_create_user(
    google_id: str,
    email: str,
    name: str,
    picture: str | None = None,
) -> dict[str, Any]:
    """Get existing user or create new user in DynamoDB.

    Args:
        google_id: Google user ID
        email: User email
        name: User display name
        picture: Profile picture URL

    Returns:
        User data dictionary
    """
    users_table = dynamodb.Table(USERS_TABLE_NAME)

    try:
        # Try to find user by Google ID
        response = users_table.query(
            IndexName="GoogleIdIndex",
            KeyConditionExpression="google_id = :google_id",
            ExpressionAttributeValues={":google_id": google_id},
        )

        if response["Items"]:
            user = response["Items"][0]
            logger.info("user_id=<%s>, email=<%s> | existing user found", user["user_id"], email)
            return user

        # Create new user
        import uuid
        from datetime import datetime, timezone

        user_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        user = {
            "user_id": user_id,
            "google_id": google_id,
            "email": email,
            "name": name,
            "picture": picture,
            "created_at": now,
            "updated_at": now,
        }

        users_table.put_item(Item=user)

        logger.info("user_id=<%s>, email=<%s> | new user created", user_id, email)
        return user

    except ClientError as e:
        logger.error("error=<%s> | failed to get or create user", str(e))
        raise


def handle_login(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Handle /auth/login endpoint.

    Generates Google OAuth authorization URL and redirects user.

    Args:
        event: API Gateway event
        context: Lambda context

    Returns:
        API Gateway response
    """
    logger.info("path=</auth/login> | handling login request")

    try:
        oauth_handler = get_oauth_handler()

        # Generate state parameter for CSRF protection
        import secrets

        state = secrets.token_urlsafe(32)

        # Get authorization URL
        auth_url = oauth_handler.get_authorization_url(state=state)

        # Return redirect response
        return {
            "statusCode": 302,
            "headers": {
                "Location": auth_url,
                "Access-Control-Allow-Origin": FRONTEND_URL or "*",
            },
            "body": "",
        }

    except Exception as e:
        logger.error("error=<%s> | login failed", str(e))
        return create_response(
            500,
            {"error": "Internal server error", "message": str(e)},
        )


def handle_callback(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Handle /auth/callback endpoint.

    Exchanges OAuth code for tokens, verifies user, creates/updates user record.

    Args:
        event: API Gateway event
        context: Lambda context

    Returns:
        API Gateway response
    """
    logger.info("path=</auth/callback> | handling oauth callback")

    try:
        # Get authorization code from query params
        query_params = event.get("queryStringParameters", {}) or {}
        code = query_params.get("code")

        if not code:
            logger.warning("callback_error=<missing_code> | no authorization code provided")
            return create_response(400, {"error": "Missing authorization code"})

        oauth_handler = get_oauth_handler()
        jwt_handler = get_jwt_handler()

        # Exchange code for tokens
        tokens = oauth_handler.exchange_code_for_tokens(code)

        # Get user info
        id_token = tokens.get("id_token")
        if id_token:
            user_info = oauth_handler.verify_id_token(id_token)
        else:
            # Fallback to access token
            access_token = tokens.get("access_token", "")
            user_info = oauth_handler.get_user_info(access_token)

        # Create or update user in database
        user = get_or_create_user(
            google_id=user_info.google_id,
            email=user_info.email,
            name=user_info.name,
            picture=user_info.picture,
        )

        # Create JWT tokens
        access_token_jwt = jwt_handler.create_access_token(
            user_id=user["user_id"],
            email=user["email"],
        )

        refresh_token_jwt = jwt_handler.create_refresh_token(
            user_id=user["user_id"],
            email=user["email"],
        )

        # Redirect to frontend with tokens
        frontend_redirect = f"{FRONTEND_URL}?access_token={access_token_jwt}&refresh_token={refresh_token_jwt}"

        return {
            "statusCode": 302,
            "headers": {
                "Location": frontend_redirect,
                "Access-Control-Allow-Origin": FRONTEND_URL or "*",
            },
            "body": "",
        }

    except Exception as e:
        logger.error("error=<%s> | callback failed", str(e))

        # Redirect to frontend with error
        error_redirect = f"{FRONTEND_URL}?error={str(e)}"
        return {
            "statusCode": 302,
            "headers": {
                "Location": error_redirect,
                "Access-Control-Allow-Origin": FRONTEND_URL or "*",
            },
            "body": "",
        }


def handle_refresh(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Handle /auth/refresh endpoint.

    Refreshes access token using refresh token.

    Args:
        event: API Gateway event
        context: Lambda context

    Returns:
        API Gateway response
    """
    logger.info("path=</auth/refresh> | handling token refresh")

    try:
        # Get refresh token from body
        body = json.loads(event.get("body", "{}"))
        refresh_token = body.get("refresh_token")

        if not refresh_token:
            return create_response(400, {"error": "Missing refresh_token"})

        jwt_handler = get_jwt_handler()

        # Create new access token
        new_access_token = jwt_handler.refresh_access_token(refresh_token)

        return create_response(
            200,
            {
                "access_token": new_access_token,
                "token_type": "Bearer",
            },
        )

    except ValueError as e:
        logger.warning("error=<%s> | token refresh failed", str(e))
        return create_response(401, {"error": "Invalid or expired refresh token"})

    except Exception as e:
        logger.error("error=<%s> | refresh failed", str(e))
        return create_response(500, {"error": "Internal server error"})


def handle_me(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Handle /auth/me endpoint.

    Returns current user information from JWT token.

    Args:
        event: API Gateway event
        context: Lambda context

    Returns:
        API Gateway response
    """
    logger.info("path=</auth/me> | handling user info request")

    try:
        # Get access token from Authorization header
        headers = event.get("headers", {})
        auth_header = headers.get("authorization") or headers.get("Authorization", "")

        if not auth_header or not auth_header.startswith("Bearer "):
            return create_response(401, {"error": "Missing or invalid Authorization header"})

        access_token = auth_header.replace("Bearer ", "")

        jwt_handler = get_jwt_handler()

        # Verify token
        payload = jwt_handler.verify_token(access_token, expected_type="access")

        # Get user from database
        users_table = dynamodb.Table(USERS_TABLE_NAME)
        response = users_table.get_item(Key={"user_id": payload.sub})

        if "Item" not in response:
            logger.warning("user_id=<%s> | user not found", payload.sub)
            return create_response(404, {"error": "User not found"})

        user = response["Item"]

        # Return user info (excluding sensitive fields)
        return create_response(
            200,
            {
                "user_id": user["user_id"],
                "email": user["email"],
                "name": user["name"],
                "picture": user.get("picture"),
                "created_at": user["created_at"],
            },
        )

    except ValueError as e:
        logger.warning("error=<%s> | token verification failed", str(e))
        return create_response(401, {"error": "Invalid or expired token"})

    except Exception as e:
        logger.error("error=<%s> | get user info failed", str(e))
        return create_response(500, {"error": "Internal server error"})


def handle_options(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Handle OPTIONS requests for CORS preflight.

    Args:
        event: API Gateway event
        context: Lambda context

    Returns:
        API Gateway response
    """
    return create_response(200, {})


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Main Lambda handler for auth endpoints.

    Routes requests to appropriate handler based on path and method.

    Args:
        event: API Gateway event
        context: Lambda context

    Returns:
        API Gateway response
    """
    # Support both API Gateway v1 (REST API) and v2 (HTTP API) event formats
    # v1: event["httpMethod"], event["path"]
    # v2: event["requestContext"]["http"]["method"], event["rawPath"]
    request_context = event.get("requestContext", {})
    http_context = request_context.get("http", {})

    method = event.get("httpMethod") or http_context.get("method", "")
    path = event.get("path") or event.get("rawPath", "")

    logger.info("method=<%s>, path=<%s> | processing request", method, path)

    # Handle CORS preflight
    if method == "OPTIONS":
        return handle_options(event, context)

    # Route to appropriate handler
    if path == "/auth/login" and method == "GET":
        return handle_login(event, context)
    elif path == "/auth/callback" and method == "GET":
        return handle_callback(event, context)
    elif path == "/auth/refresh" and method == "POST":
        return handle_refresh(event, context)
    elif path == "/auth/me" and method == "GET":
        return handle_me(event, context)
    else:
        return create_response(404, {"error": "Not found"})
