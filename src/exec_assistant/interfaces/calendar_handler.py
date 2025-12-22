"""Calendar authentication handler Lambda.

This Lambda handles Google Calendar OAuth flow:
- GET /calendar/auth - Initiate OAuth flow (JWT required)
- GET /calendar/callback - Handle OAuth callback from Google (public)
- POST /calendar/disconnect - Disconnect calendar (JWT required)

Security:
- JWT authentication required for auth and disconnect endpoints
- State parameter used for CSRF protection in OAuth flow
- Proper input validation on all endpoints
- Sensitive data never logged or exposed

Flow:
    1. User calls /calendar/auth with JWT
    2. Handler generates Google OAuth URL with state=user_id
    3. User redirects to Google
    4. User authorizes
    5. Google redirects to /calendar/callback?code=XXX&state=user_id
    6. Handler validates state, exchanges code for tokens
    7. Handler stores tokens in Secrets Manager
    8. Handler updates user record in DynamoDB
    9. Handler returns success HTML page
"""

import json
import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

from exec_assistant.shared.calendar import CalendarClient, CalendarError, OAuthError
from exec_assistant.shared.jwt_handler import JWTHandler
from exec_assistant.shared.logging import get_logger
from exec_assistant.shared.models import User

logger = get_logger(__name__)

# Global clients (initialized once per Lambda container)
_dynamodb = None
_jwt_handler = None


def get_dynamodb():
    """Get DynamoDB resource (cached).

    Returns:
        DynamoDB resource instance
    """
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb", region_name=os.environ["AWS_REGION"])
    return _dynamodb


def get_jwt_handler():
    """Get JWT handler (cached).

    Returns:
        JWTHandler instance
    """
    global _jwt_handler
    if _jwt_handler is None:
        _jwt_handler = JWTHandler(secret_key=os.environ["JWT_SECRET_KEY"])
    return _jwt_handler


def create_response(
    status_code: int,
    body: dict | str,
    content_type: str = "application/json",
) -> dict[str, Any]:
    """Create HTTP response.

    Args:
        status_code: HTTP status code
        body: Response body (dict for JSON, str for HTML)
        content_type: Content type header

    Returns:
        API Gateway response dict
    """
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": content_type,
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        },
        "body": json.dumps(body) if isinstance(body, dict) else body,
    }


def create_error_response(status_code: int, message: str) -> dict[str, Any]:
    """Create error response.

    Args:
        status_code: HTTP status code
        message: User-friendly error message

    Returns:
        API Gateway error response
    """
    return create_response(status_code, {"error": message})


def extract_token_from_header(headers: dict[str, str]) -> str | None:
    """Extract JWT token from Authorization header.

    Args:
        headers: Request headers dict

    Returns:
        JWT token or None if not found
    """
    auth_header = headers.get("authorization") or headers.get("Authorization")
    if not auth_header:
        return None

    # Handle "Bearer <token>" format
    if auth_header.startswith("Bearer "):
        return auth_header[7:]

    return auth_header


def get_user_from_db(user_id: str) -> User | None:
    """Load user from DynamoDB.

    Args:
        user_id: User ID to load

    Returns:
        User object or None if not found
    """
    dynamodb = get_dynamodb()
    users_table = dynamodb.Table(os.environ["USERS_TABLE_NAME"])

    try:
        response = users_table.get_item(Key={"user_id": user_id})

        if "Item" not in response:
            logger.warning("user_id=<%s> | user not found in database", user_id)
            return None

        return User.from_dynamodb(response["Item"])

    except ClientError as e:
        logger.error(
            "user_id=<%s>, error=<%s> | failed to load user from database",
            user_id,
            str(e),
            exc_info=True,
        )
        raise


def update_user_calendar_status(
    user_id: str,
    connected: bool,
    refresh_token: str | None = None,
) -> None:
    """Update user's calendar connection status in DynamoDB.

    Args:
        user_id: User ID to update
        connected: Whether calendar is connected
        refresh_token: Refresh token (if connecting)
    """
    user = get_user_from_db(user_id)

    if not user:
        logger.error("user_id=<%s> | cannot update calendar status, user not found", user_id)
        raise ValueError(f"User {user_id} not found")

    if connected:
        if not refresh_token:
            raise ValueError("refresh_token required when connecting calendar")
        user.connect_calendar(refresh_token)
    else:
        user.disconnect_calendar()

    # Save to DynamoDB
    dynamodb = get_dynamodb()
    users_table = dynamodb.Table(os.environ["USERS_TABLE_NAME"])

    users_table.put_item(Item=user.to_dynamodb())

    logger.info(
        "user_id=<%s>, connected=<%s> | updated user calendar status",
        user_id,
        connected,
    )


def handle_calendar_auth(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Handle GET /calendar/auth - Initiate OAuth flow.

    This endpoint generates a Google OAuth authorization URL for the user.

    Args:
        event: API Gateway event
        context: Lambda context

    Returns:
        Response with authorization_url
    """
    try:
        # Extract and validate JWT token
        jwt_handler = get_jwt_handler()
        token = extract_token_from_header(event.get("headers", {}))

        if not token:
            logger.warning("missing authorization token")
            return create_error_response(401, "Missing authorization token")

        try:
            user_id = jwt_handler.verify_token(token)
        except Exception as e:
            logger.warning("token=<%s...>, error=<%s> | invalid token", token[:20], str(e))
            return create_error_response(401, "Invalid authorization token")

        # Verify user exists
        user = get_user_from_db(user_id)
        if not user:
            logger.warning("user_id=<%s> | user not found", user_id)
            return create_error_response(404, "User not found")

        # Create calendar client
        try:
            client = CalendarClient(
                user_id=user_id,
                client_id=os.environ["GOOGLE_CALENDAR_CLIENT_ID"],
                client_secret=os.environ["GOOGLE_CALENDAR_CLIENT_SECRET"],
                redirect_uri=os.environ["GOOGLE_CALENDAR_REDIRECT_URI"],
            )
        except ValueError as e:
            logger.error("user_id=<%s>, error=<%s> | invalid user_id format", user_id, str(e))
            return create_error_response(400, "Invalid user ID format")

        # Generate authorization URL
        try:
            authorization_url = client.get_authorization_url(state=user_id)
        except OAuthError as e:
            logger.error(
                "user_id=<%s>, error=<%s> | failed to generate authorization url",
                user_id,
                str(e),
                exc_info=True,
            )
            return create_error_response(500, "Failed to generate authorization URL")

        logger.info("user_id=<%s> | generated calendar authorization url", user_id)

        return create_response(
            200,
            {
                "authorization_url": authorization_url,
                "provider": "google",
                "status": "redirect_required",
            },
        )

    except Exception as e:
        logger.error(
            "error=<%s> | unexpected error in calendar auth",
            str(e),
            exc_info=True,
        )
        return create_error_response(500, "Internal server error")


def handle_calendar_callback(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Handle GET /calendar/callback - OAuth callback from Google.

    This endpoint:
    1. Validates code and state parameters
    2. Exchanges authorization code for tokens
    3. Stores tokens in Secrets Manager
    4. Updates user record in DynamoDB
    5. Returns HTML success/error page

    Note: This endpoint is PUBLIC (no JWT required) as Google redirects here.
    Security is provided by state parameter validation.

    Args:
        event: API Gateway event
        context: Lambda context

    Returns:
        HTML response (success or error page)
    """
    try:
        # Extract query parameters
        params = event.get("queryStringParameters") or {}
        code = params.get("code")
        state = params.get("state")  # Contains user_id
        error = params.get("error")  # Google OAuth error

        # Handle OAuth errors from Google
        if error:
            error_description = params.get("error_description", "Unknown error")
            logger.warning(
                "oauth_error=<%s>, description=<%s> | google oauth error",
                error,
                error_description,
            )

            return create_response(
                400,
                f"""
                <html>
                <head><title>Calendar Connection Failed</title></head>
                <body>
                    <h1>Calendar Connection Failed</h1>
                    <p>Error: {error}</p>
                    <p>Description: {error_description}</p>
                    <p><a href="/">Return to application</a></p>
                </body>
                </html>
                """,
                content_type="text/html",
            )

        # Validate required parameters
        if not code:
            logger.warning("missing authorization code in callback")
            return create_response(
                400,
                """
                <html>
                <head><title>Invalid Request</title></head>
                <body>
                    <h1>Invalid Request</h1>
                    <p>Missing authorization code.</p>
                    <p><a href="/">Return to application</a></p>
                </body>
                </html>
                """,
                content_type="text/html",
            )

        if not state:
            logger.warning("missing state parameter in callback")
            return create_response(
                400,
                """
                <html>
                <head><title>Invalid Request</title></head>
                <body>
                    <h1>Invalid Request</h1>
                    <p>Missing state parameter (CSRF protection).</p>
                    <p><a href="/">Return to application</a></p>
                </body>
                </html>
                """,
                content_type="text/html",
            )

        user_id = state

        # Create calendar client
        try:
            client = CalendarClient(
                user_id=user_id,
                client_id=os.environ["GOOGLE_CALENDAR_CLIENT_ID"],
                client_secret=os.environ["GOOGLE_CALENDAR_CLIENT_SECRET"],
                redirect_uri=os.environ["GOOGLE_CALENDAR_REDIRECT_URI"],
            )
        except ValueError as e:
            logger.error(
                "user_id=<%s>, error=<%s> | invalid user_id in state parameter",
                user_id,
                str(e),
            )
            return create_response(
                400,
                """
                <html>
                <head><title>Invalid Request</title></head>
                <body>
                    <h1>Invalid Request</h1>
                    <p>Invalid user ID in state parameter.</p>
                    <p><a href="/">Return to application</a></p>
                </body>
                </html>
                """,
                content_type="text/html",
            )

        # Handle OAuth callback (exchange code for tokens)
        try:
            result = client.handle_oauth_callback(code=code, state=state)
        except OAuthError as e:
            logger.error(
                "user_id=<%s>, error=<%s> | oauth callback failed",
                user_id,
                str(e),
                exc_info=True,
            )
            return create_response(
                500,
                """
                <html>
                <head><title>Connection Failed</title></head>
                <body>
                    <h1>Calendar Connection Failed</h1>
                    <p>Failed to exchange authorization code for tokens.</p>
                    <p>Please try again or contact support.</p>
                    <p><a href="/">Return to application</a></p>
                </body>
                </html>
                """,
                content_type="text/html",
            )
        except ValueError as e:
            # State validation failed (CSRF attack attempt)
            logger.error(
                "user_id=<%s>, error=<%s> | state validation failed",
                user_id,
                str(e),
                exc_info=True,
            )
            return create_response(
                403,
                """
                <html>
                <head><title>Security Error</title></head>
                <body>
                    <h1>Security Error</h1>
                    <p>State parameter validation failed (CSRF protection).</p>
                    <p>Please try connecting again.</p>
                    <p><a href="/">Return to application</a></p>
                </body>
                </html>
                """,
                content_type="text/html",
            )

        # Update user record in DynamoDB
        try:
            # Note: We don't store the actual refresh token in the user record
            # It's stored securely in Secrets Manager by CalendarClient
            # We just set the calendar_connected flag
            update_user_calendar_status(
                user_id=user_id,
                connected=True,
                refresh_token="stored_in_secrets_manager",  # Placeholder
            )
        except Exception as e:
            logger.error(
                "user_id=<%s>, error=<%s> | failed to update user record",
                user_id,
                str(e),
                exc_info=True,
            )
            # Continue anyway - tokens are stored, user can retry

        logger.info(
            "user_id=<%s>, has_refresh_token=<%s> | calendar connected successfully",
            user_id,
            result.get("has_refresh_token"),
        )

        # Return success page
        return create_response(
            200,
            """
            <html>
            <head>
                <title>Calendar Connected</title>
                <script>
                    // Notify parent window (if opened in popup)
                    if (window.opener) {
                        window.opener.postMessage({
                            type: 'calendar_connected',
                            provider: 'google'
                        }, '*');
                    }
                    // Auto-close after 2 seconds
                    setTimeout(function() {
                        if (window.opener) {
                            window.close();
                        } else {
                            window.location.href = '/';
                        }
                    }, 2000);
                </script>
                <style>
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background-color: #f5f5f5;
                    }
                    .container {
                        text-align: center;
                        background: white;
                        padding: 40px;
                        border-radius: 8px;
                        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    }
                    .success-icon {
                        font-size: 48px;
                        color: #4CAF50;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="success-icon">✓</div>
                    <h1>Calendar Connected!</h1>
                    <p>Your Google Calendar has been successfully connected.</p>
                    <p>This window will close automatically...</p>
                    <p><a href="/">Or click here to return to the application</a></p>
                </div>
            </body>
            </html>
            """,
            content_type="text/html",
        )

    except Exception as e:
        logger.error(
            "error=<%s> | unexpected error in calendar callback",
            str(e),
            exc_info=True,
        )
        return create_response(
            500,
            """
            <html>
            <head><title>Error</title></head>
            <body>
                <h1>Unexpected Error</h1>
                <p>An unexpected error occurred while connecting your calendar.</p>
                <p>Please try again or contact support.</p>
                <p><a href="/">Return to application</a></p>
            </body>
            </html>
            """,
            content_type="text/html",
        )


def handle_calendar_disconnect(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Handle POST /calendar/disconnect - Disconnect calendar.

    This endpoint:
    1. Validates JWT token
    2. Deletes tokens from Secrets Manager
    3. Updates user record in DynamoDB
    4. Returns success/error response

    Args:
        event: API Gateway event
        context: Lambda context

    Returns:
        JSON response with status
    """
    try:
        # Extract and validate JWT token
        jwt_handler = get_jwt_handler()
        token = extract_token_from_header(event.get("headers", {}))

        if not token:
            logger.warning("missing authorization token")
            return create_error_response(401, "Missing authorization token")

        try:
            user_id = jwt_handler.verify_token(token)
        except Exception as e:
            logger.warning("token=<%s...>, error=<%s> | invalid token", token[:20], str(e))
            return create_error_response(401, "Invalid authorization token")

        # Verify user exists
        user = get_user_from_db(user_id)
        if not user:
            logger.warning("user_id=<%s> | user not found", user_id)
            return create_error_response(404, "User not found")

        # Create calendar client
        try:
            client = CalendarClient(
                user_id=user_id,
                client_id=os.environ["GOOGLE_CALENDAR_CLIENT_ID"],
                client_secret=os.environ["GOOGLE_CALENDAR_CLIENT_SECRET"],
                redirect_uri=os.environ["GOOGLE_CALENDAR_REDIRECT_URI"],
            )
        except ValueError as e:
            logger.error("user_id=<%s>, error=<%s> | invalid user_id format", user_id, str(e))
            return create_error_response(400, "Invalid user ID format")

        # Disconnect calendar (delete tokens)
        try:
            client.disconnect()
        except ClientError as e:
            logger.error(
                "user_id=<%s>, error=<%s> | failed to delete tokens",
                user_id,
                str(e),
                exc_info=True,
            )
            # Continue anyway - might already be deleted

        # Update user record
        try:
            update_user_calendar_status(user_id=user_id, connected=False)
        except Exception as e:
            logger.error(
                "user_id=<%s>, error=<%s> | failed to update user record",
                user_id,
                str(e),
                exc_info=True,
            )
            return create_error_response(500, "Failed to update user record")

        logger.info("user_id=<%s> | calendar disconnected successfully", user_id)

        return create_response(
            200,
            {
                "status": "disconnected",
                "message": "Calendar successfully disconnected",
            },
        )

    except Exception as e:
        logger.error(
            "error=<%s> | unexpected error in calendar disconnect",
            str(e),
            exc_info=True,
        )
        return create_error_response(500, "Internal server error")


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Main Lambda handler for calendar endpoints.

    Routes:
    - GET /calendar/auth → handle_calendar_auth (JWT required)
    - GET /calendar/callback → handle_calendar_callback (public)
    - POST /calendar/disconnect → handle_calendar_disconnect (JWT required)
    - OPTIONS /* → CORS preflight

    Args:
        event: API Gateway event
        context: Lambda context

    Returns:
        API Gateway response
    """
    path = event.get("path", "")
    method = event.get("httpMethod", "")

    logger.info("method=<%s>, path=<%s> | handling calendar request", method, path)

    # CORS preflight
    if method == "OPTIONS":
        return create_response(200, {})

    # Route to appropriate handler
    if path == "/calendar/auth" and method == "GET":
        return handle_calendar_auth(event, context)
    elif path == "/calendar/callback" and method == "GET":
        return handle_calendar_callback(event, context)
    elif path == "/calendar/disconnect" and method == "POST":
        return handle_calendar_disconnect(event, context)
    else:
        logger.warning("method=<%s>, path=<%s> | endpoint not found", method, path)
        return create_error_response(404, "Endpoint not found")
