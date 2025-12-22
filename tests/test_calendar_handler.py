"""Tests for calendar handler Lambda function.

This module tests the calendar OAuth endpoints including:
- /calendar/auth (initiate OAuth flow)
- /calendar/callback (OAuth callback from Google)
- /calendar/disconnect (disconnect calendar)
"""

import json
import os
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from exec_assistant.interfaces.calendar_handler import (
    create_error_response,
    create_response,
    extract_token_from_header,
    get_user_from_db,
    handle_calendar_auth,
    handle_calendar_callback,
    handle_calendar_disconnect,
    lambda_handler,
    update_user_calendar_status,
)
from exec_assistant.shared.models import User


@pytest.fixture
def mock_env_vars():
    """Mock environment variables."""
    with patch.dict(
        os.environ,
        {
            "GOOGLE_CALENDAR_CLIENT_ID": "test-client-id",
            "GOOGLE_CALENDAR_CLIENT_SECRET": "test-client-secret",
            "GOOGLE_CALENDAR_REDIRECT_URI": "https://example.com/callback",
            "JWT_SECRET_KEY": "test-jwt-secret",
            "USERS_TABLE_NAME": "test-users-table",
            "AWS_REGION": "us-east-1",
        },
    ):
        yield


@pytest.fixture
def sample_user():
    """Create a sample user."""
    return User(
        user_id="test-user-123",
        email="test@example.com",
        name="Test User",
        created_at=datetime.now(UTC),
        is_calendar_connected=False,
        calendar_refresh_token=None,
    )


@pytest.fixture
def mock_dynamodb(sample_user):
    """Mock DynamoDB resource."""
    mock_db = MagicMock()
    mock_table = MagicMock()
    mock_db.Table.return_value = mock_table

    # Default: return sample user
    mock_table.get_item.return_value = {"Item": sample_user.to_dynamodb()}

    with patch("exec_assistant.interfaces.calendar_handler.boto3.resource") as mock_boto:
        mock_boto.return_value = mock_db
        yield mock_table


@pytest.fixture
def mock_jwt_handler():
    """Mock JWT handler."""
    mock_handler = MagicMock()
    mock_handler.verify_token.return_value = "test-user-123"

    with patch("exec_assistant.interfaces.calendar_handler.JWTHandler") as mock_jwt:
        mock_jwt.return_value = mock_handler
        yield mock_handler


@pytest.fixture
def mock_calendar_client():
    """Mock CalendarClient."""
    mock_client = MagicMock()
    mock_client.get_authorization_url.return_value = (
        "https://accounts.google.com/oauth/authorize?client_id=test"
    )
    mock_client.handle_oauth_callback.return_value = {
        "access_token": "test-access-token",
        "refresh_token": "test-refresh-token",
    }

    with patch("exec_assistant.interfaces.calendar_handler.CalendarClient") as mock_cal:
        mock_cal.return_value = mock_client
        yield mock_client


class TestHelperFunctions:
    """Test helper functions."""

    def test_create_response_json(self):
        """Test creating JSON response."""
        response = create_response(200, {"message": "Success"})

        assert response["statusCode"] == 200
        assert response["headers"]["Content-Type"] == "application/json"
        assert response["headers"]["Access-Control-Allow-Origin"] == "*"
        assert json.loads(response["body"]) == {"message": "Success"}

    def test_create_response_html(self):
        """Test creating HTML response."""
        html_content = "<html><body>Test</body></html>"
        response = create_response(200, html_content, content_type="text/html")

        assert response["statusCode"] == 200
        assert response["headers"]["Content-Type"] == "text/html"
        assert response["body"] == html_content

    def test_create_error_response(self):
        """Test creating error response."""
        response = create_error_response(404, "Not found")

        assert response["statusCode"] == 404
        body = json.loads(response["body"])
        assert body["error"] == "Not found"

    def test_create_error_response_with_details(self):
        """Test creating error response with details."""
        response = create_error_response(400, "Bad request", details="Invalid parameter")

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["error"] == "Bad request"
        assert body["details"] == "Invalid parameter"

    def test_extract_token_from_header_bearer(self):
        """Test extracting token from Bearer header."""
        headers = {"Authorization": "Bearer test-token-123"}
        token = extract_token_from_header(headers)

        assert token == "test-token-123"

    def test_extract_token_from_header_lowercase(self):
        """Test extracting token from lowercase header."""
        headers = {"authorization": "Bearer test-token-456"}
        token = extract_token_from_header(headers)

        assert token == "test-token-456"

    def test_extract_token_from_header_missing(self):
        """Test extracting token from missing header."""
        token = extract_token_from_header({})

        assert token is None

    def test_extract_token_from_header_invalid_format(self):
        """Test extracting token from invalid format."""
        headers = {"Authorization": "Basic test-token"}
        token = extract_token_from_header(headers)

        assert token is None

    def test_get_user_from_db(self, mock_env_vars, mock_dynamodb, sample_user):
        """Test getting user from DynamoDB."""
        user = get_user_from_db("test-user-123")

        assert user is not None
        assert user.user_id == sample_user.user_id
        assert user.email == sample_user.email
        mock_dynamodb.get_item.assert_called_once_with(Key={"user_id": "test-user-123"})

    def test_get_user_from_db_not_found(self, mock_env_vars, mock_dynamodb):
        """Test getting user that doesn't exist."""
        mock_dynamodb.get_item.return_value = {}
        user = get_user_from_db("nonexistent-user")

        assert user is None

    def test_update_user_calendar_status_connect(self, mock_env_vars, mock_dynamodb, sample_user):
        """Test updating user calendar status to connected."""
        update_user_calendar_status("test-user-123", connected=True, refresh_token="refresh-123")

        # Verify user was loaded
        mock_dynamodb.get_item.assert_called_once()

        # Verify user was updated
        mock_dynamodb.put_item.assert_called_once()
        saved_item = mock_dynamodb.put_item.call_args[1]["Item"]
        assert saved_item["is_calendar_connected"] is True
        assert saved_item["calendar_refresh_token"] == "refresh-123"

    def test_update_user_calendar_status_disconnect(self, mock_env_vars, mock_dynamodb, sample_user):
        """Test updating user calendar status to disconnected."""
        update_user_calendar_status("test-user-123", connected=False)

        mock_dynamodb.put_item.assert_called_once()
        saved_item = mock_dynamodb.put_item.call_args[1]["Item"]
        assert saved_item["is_calendar_connected"] is False
        assert saved_item["calendar_refresh_token"] is None


class TestHandleCalendarAuth:
    """Test handle_calendar_auth endpoint."""

    def test_success(
        self,
        mock_env_vars,
        mock_jwt_handler,
        mock_calendar_client,
        mock_dynamodb,
    ):
        """Test successful auth initiation."""
        event = {
            "path": "/calendar/auth",
            "httpMethod": "GET",
            "headers": {"Authorization": "Bearer valid-token"},
        }

        response = handle_calendar_auth(event, None)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert "authorization_url" in body
        assert body["provider"] == "google"
        assert body["status"] == "redirect_required"
        mock_jwt_handler.verify_token.assert_called_once_with("valid-token")

    def test_missing_token(self, mock_env_vars, mock_jwt_handler, mock_dynamodb):
        """Test auth initiation with missing token."""
        event = {
            "path": "/calendar/auth",
            "httpMethod": "GET",
            "headers": {},
        }

        response = handle_calendar_auth(event, None)

        assert response["statusCode"] == 401
        body = json.loads(response["body"])
        assert "error" in body

    def test_invalid_token(self, mock_env_vars, mock_jwt_handler, mock_dynamodb):
        """Test auth initiation with invalid token."""
        mock_jwt_handler.verify_token.side_effect = ValueError("Invalid token")

        event = {
            "path": "/calendar/auth",
            "httpMethod": "GET",
            "headers": {"Authorization": "Bearer invalid-token"},
        }

        response = handle_calendar_auth(event, None)

        assert response["statusCode"] == 401
        body = json.loads(response["body"])
        assert "error" in body

    def test_user_not_found(self, mock_env_vars, mock_jwt_handler, mock_dynamodb):
        """Test auth initiation when user not found."""
        mock_dynamodb.get_item.return_value = {}

        event = {
            "path": "/calendar/auth",
            "httpMethod": "GET",
            "headers": {"Authorization": "Bearer valid-token"},
        }

        response = handle_calendar_auth(event, None)

        assert response["statusCode"] == 404
        body = json.loads(response["body"])
        assert "error" in body

    def test_calendar_client_error(
        self,
        mock_env_vars,
        mock_jwt_handler,
        mock_calendar_client,
        mock_dynamodb,
    ):
        """Test auth initiation when CalendarClient fails."""
        mock_calendar_client.get_authorization_url.side_effect = Exception("Calendar error")

        event = {
            "path": "/calendar/auth",
            "httpMethod": "GET",
            "headers": {"Authorization": "Bearer valid-token"},
        }

        response = handle_calendar_auth(event, None)

        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert "error" in body


class TestHandleCalendarCallback:
    """Test handle_calendar_callback endpoint."""

    def test_success(
        self,
        mock_env_vars,
        mock_calendar_client,
        mock_dynamodb,
    ):
        """Test successful OAuth callback."""
        event = {
            "path": "/calendar/callback",
            "httpMethod": "GET",
            "queryStringParameters": {
                "code": "auth-code-123",
                "state": "test-user-123",
            },
        }

        response = handle_calendar_callback(event, None)

        assert response["statusCode"] == 200
        assert response["headers"]["Content-Type"] == "text/html"
        assert "Calendar Connected" in response["body"]
        assert "window.opener.postMessage" in response["body"]

        # Verify callback was handled
        mock_calendar_client.handle_oauth_callback.assert_called_once_with(
            code="auth-code-123",
            state="test-user-123",
        )

        # Verify user was updated
        mock_dynamodb.put_item.assert_called_once()

    def test_missing_code(self, mock_env_vars, mock_calendar_client, mock_dynamodb):
        """Test callback with missing code."""
        event = {
            "path": "/calendar/callback",
            "httpMethod": "GET",
            "queryStringParameters": {
                "state": "test-user-123",
            },
        }

        response = handle_calendar_callback(event, None)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "error" in body

    def test_missing_state(self, mock_env_vars, mock_calendar_client, mock_dynamodb):
        """Test callback with missing state."""
        event = {
            "path": "/calendar/callback",
            "httpMethod": "GET",
            "queryStringParameters": {
                "code": "auth-code-123",
            },
        }

        response = handle_calendar_callback(event, None)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "error" in body

    def test_oauth_error_from_google(self, mock_env_vars, mock_calendar_client, mock_dynamodb):
        """Test callback with OAuth error from Google."""
        event = {
            "path": "/calendar/callback",
            "httpMethod": "GET",
            "queryStringParameters": {
                "error": "access_denied",
                "error_description": "User denied access",
            },
        }

        response = handle_calendar_callback(event, None)

        assert response["statusCode"] == 200
        assert "text/html" in response["headers"]["Content-Type"]
        assert "Authorization Failed" in response["body"]
        assert "access_denied" in response["body"]

    def test_calendar_callback_error(
        self,
        mock_env_vars,
        mock_calendar_client,
        mock_dynamodb,
    ):
        """Test callback when CalendarClient fails."""
        mock_calendar_client.handle_oauth_callback.side_effect = Exception("Callback error")

        event = {
            "path": "/calendar/callback",
            "httpMethod": "GET",
            "queryStringParameters": {
                "code": "auth-code-123",
                "state": "test-user-123",
            },
        }

        response = handle_calendar_callback(event, None)

        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert "error" in body

    def test_no_query_parameters(self, mock_env_vars, mock_calendar_client, mock_dynamodb):
        """Test callback with no query parameters."""
        event = {
            "path": "/calendar/callback",
            "httpMethod": "GET",
        }

        response = handle_calendar_callback(event, None)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "error" in body


class TestHandleCalendarDisconnect:
    """Test handle_calendar_disconnect endpoint."""

    def test_success(
        self,
        mock_env_vars,
        mock_jwt_handler,
        mock_calendar_client,
        mock_dynamodb,
    ):
        """Test successful disconnect."""
        event = {
            "path": "/calendar/disconnect",
            "httpMethod": "POST",
            "headers": {"Authorization": "Bearer valid-token"},
        }

        response = handle_calendar_disconnect(event, None)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["status"] == "disconnected"
        mock_jwt_handler.verify_token.assert_called_once_with("valid-token")
        mock_calendar_client.disconnect.assert_called_once()

    def test_missing_token(self, mock_env_vars, mock_jwt_handler, mock_dynamodb):
        """Test disconnect with missing token."""
        event = {
            "path": "/calendar/disconnect",
            "httpMethod": "POST",
            "headers": {},
        }

        response = handle_calendar_disconnect(event, None)

        assert response["statusCode"] == 401
        body = json.loads(response["body"])
        assert "error" in body

    def test_invalid_token(self, mock_env_vars, mock_jwt_handler, mock_dynamodb):
        """Test disconnect with invalid token."""
        mock_jwt_handler.verify_token.side_effect = ValueError("Invalid token")

        event = {
            "path": "/calendar/disconnect",
            "httpMethod": "POST",
            "headers": {"Authorization": "Bearer invalid-token"},
        }

        response = handle_calendar_disconnect(event, None)

        assert response["statusCode"] == 401
        body = json.loads(response["body"])
        assert "error" in body

    def test_user_not_found(self, mock_env_vars, mock_jwt_handler, mock_dynamodb):
        """Test disconnect when user not found."""
        mock_dynamodb.get_item.return_value = {}

        event = {
            "path": "/calendar/disconnect",
            "httpMethod": "POST",
            "headers": {"Authorization": "Bearer valid-token"},
        }

        response = handle_calendar_disconnect(event, None)

        assert response["statusCode"] == 404
        body = json.loads(response["body"])
        assert "error" in body

    def test_disconnect_error(
        self,
        mock_env_vars,
        mock_jwt_handler,
        mock_calendar_client,
        mock_dynamodb,
    ):
        """Test disconnect when CalendarClient fails."""
        mock_calendar_client.disconnect.side_effect = Exception("Disconnect error")

        event = {
            "path": "/calendar/disconnect",
            "httpMethod": "POST",
            "headers": {"Authorization": "Bearer valid-token"},
        }

        response = handle_calendar_disconnect(event, None)

        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert "error" in body


class TestLambdaHandler:
    """Test main Lambda handler routing."""

    def test_route_to_auth(
        self,
        mock_env_vars,
        mock_jwt_handler,
        mock_calendar_client,
        mock_dynamodb,
    ):
        """Test routing to auth handler."""
        event = {
            "path": "/calendar/auth",
            "httpMethod": "GET",
            "headers": {"Authorization": "Bearer valid-token"},
        }

        response = lambda_handler(event, None)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert "authorization_url" in body

    def test_route_to_callback(
        self,
        mock_env_vars,
        mock_calendar_client,
        mock_dynamodb,
    ):
        """Test routing to callback handler."""
        event = {
            "path": "/calendar/callback",
            "httpMethod": "GET",
            "queryStringParameters": {
                "code": "auth-code-123",
                "state": "test-user-123",
            },
        }

        response = lambda_handler(event, None)

        assert response["statusCode"] == 200
        assert "text/html" in response["headers"]["Content-Type"]

    def test_route_to_disconnect(
        self,
        mock_env_vars,
        mock_jwt_handler,
        mock_calendar_client,
        mock_dynamodb,
    ):
        """Test routing to disconnect handler."""
        event = {
            "path": "/calendar/disconnect",
            "httpMethod": "POST",
            "headers": {"Authorization": "Bearer valid-token"},
        }

        response = lambda_handler(event, None)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["status"] == "disconnected"

    def test_unknown_path(self, mock_env_vars):
        """Test routing to unknown path."""
        event = {
            "path": "/unknown",
            "httpMethod": "GET",
        }

        response = lambda_handler(event, None)

        assert response["statusCode"] == 404
        body = json.loads(response["body"])
        assert "error" in body

    def test_wrong_method_for_auth(self, mock_env_vars):
        """Test wrong HTTP method for auth endpoint."""
        event = {
            "path": "/calendar/auth",
            "httpMethod": "POST",
        }

        response = lambda_handler(event, None)

        assert response["statusCode"] == 404

    def test_wrong_method_for_callback(self, mock_env_vars):
        """Test wrong HTTP method for callback endpoint."""
        event = {
            "path": "/calendar/callback",
            "httpMethod": "POST",
        }

        response = lambda_handler(event, None)

        assert response["statusCode"] == 404

    def test_wrong_method_for_disconnect(self, mock_env_vars):
        """Test wrong HTTP method for disconnect endpoint."""
        event = {
            "path": "/calendar/disconnect",
            "httpMethod": "GET",
        }

        response = lambda_handler(event, None)

        assert response["statusCode"] == 404

    def test_missing_path(self, mock_env_vars):
        """Test event with missing path."""
        event = {
            "httpMethod": "GET",
        }

        response = lambda_handler(event, None)

        assert response["statusCode"] == 404

    def test_missing_method(self, mock_env_vars):
        """Test event with missing method."""
        event = {
            "path": "/calendar/auth",
        }

        response = lambda_handler(event, None)

        assert response["statusCode"] == 404


class TestGlobalCaching:
    """Test global client caching."""

    def test_dynamodb_caching(self, mock_env_vars):
        """Test DynamoDB client is cached."""
        from exec_assistant.interfaces.calendar_handler import _dynamodb, get_dynamodb

        # Reset global
        import exec_assistant.interfaces.calendar_handler as handler_module

        handler_module._dynamodb = None

        with patch("exec_assistant.interfaces.calendar_handler.boto3.resource") as mock_boto:
            mock_db = MagicMock()
            mock_boto.return_value = mock_db

            # First call should create client
            db1 = get_dynamodb()
            assert mock_boto.call_count == 1

            # Second call should use cached client
            db2 = get_dynamodb()
            assert mock_boto.call_count == 1
            assert db1 is db2

    def test_jwt_handler_caching(self, mock_env_vars):
        """Test JWT handler is cached."""
        from exec_assistant.interfaces.calendar_handler import _jwt_handler, get_jwt_handler

        # Reset global
        import exec_assistant.interfaces.calendar_handler as handler_module

        handler_module._jwt_handler = None

        with patch("exec_assistant.interfaces.calendar_handler.JWTHandler") as mock_jwt:
            mock_handler = MagicMock()
            mock_jwt.return_value = mock_handler

            # First call should create handler
            jwt1 = get_jwt_handler()
            assert mock_jwt.call_count == 1

            # Second call should use cached handler
            jwt2 = get_jwt_handler()
            assert mock_jwt.call_count == 1
            assert jwt1 is jwt2


class TestCORSHeaders:
    """Test CORS headers in responses."""

    def test_cors_in_success_response(self):
        """Test CORS headers in success response."""
        response = create_response(200, {"message": "Success"})

        assert "Access-Control-Allow-Origin" in response["headers"]
        assert response["headers"]["Access-Control-Allow-Origin"] == "*"
        assert "Access-Control-Allow-Methods" in response["headers"]
        assert "Access-Control-Allow-Headers" in response["headers"]

    def test_cors_in_error_response(self):
        """Test CORS headers in error response."""
        response = create_error_response(400, "Bad request")

        assert "Access-Control-Allow-Origin" in response["headers"]
        assert response["headers"]["Access-Control-Allow-Origin"] == "*"


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_headers(self, mock_env_vars):
        """Test handling empty headers dictionary."""
        event = {
            "path": "/calendar/auth",
            "httpMethod": "GET",
            "headers": None,
        }

        response = lambda_handler(event, None)

        assert response["statusCode"] == 401

    def test_malformed_authorization_header(self, mock_env_vars):
        """Test handling malformed authorization header."""
        event = {
            "path": "/calendar/auth",
            "httpMethod": "GET",
            "headers": {"Authorization": "NotBearer token"},
        }

        response = lambda_handler(event, None)

        assert response["statusCode"] == 401

    def test_callback_with_empty_query_params(self, mock_env_vars):
        """Test callback with empty query parameter values."""
        event = {
            "path": "/calendar/callback",
            "httpMethod": "GET",
            "queryStringParameters": {
                "code": "",
                "state": "",
            },
        }

        response = lambda_handler(event, None)

        assert response["statusCode"] == 400

    def test_dynamodb_connection_error(self, mock_env_vars, mock_jwt_handler):
        """Test handling DynamoDB connection errors."""
        with patch("exec_assistant.interfaces.calendar_handler.boto3.resource") as mock_boto:
            mock_boto.side_effect = Exception("DynamoDB connection failed")

            event = {
                "path": "/calendar/auth",
                "httpMethod": "GET",
                "headers": {"Authorization": "Bearer valid-token"},
            }

            response = lambda_handler(event, None)

            assert response["statusCode"] == 500

    def test_secrets_manager_error(
        self,
        mock_env_vars,
        mock_jwt_handler,
        mock_dynamodb,
        mock_calendar_client,
    ):
        """Test handling Secrets Manager errors."""
        mock_calendar_client.disconnect.side_effect = Exception("Secrets Manager error")

        event = {
            "path": "/calendar/disconnect",
            "httpMethod": "POST",
            "headers": {"Authorization": "Bearer valid-token"},
        }

        response = lambda_handler(event, None)

        assert response["statusCode"] == 500
