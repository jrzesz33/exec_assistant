"""Agent chat handler for Lambda function.

This module handles chat interactions with the Meeting Coordinator agent.
It provides the /chat/send endpoint for user messages.
"""

import json
import logging
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3

from exec_assistant.agents.meeting_coordinator import run_meeting_coordinator
from exec_assistant.shared.jwt_handler import JWTHandler
from exec_assistant.shared.models import ChatSession, ChatSessionState

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Environment variables
CHAT_SESSIONS_TABLE_NAME = os.environ.get("CHAT_SESSIONS_TABLE_NAME", "")
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "")
SESSIONS_BUCKET_NAME = os.environ.get("SESSIONS_BUCKET_NAME", "")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# Lazy-initialized clients
_jwt_handler: JWTHandler | None = None
_dynamodb = None


def get_dynamodb():
    """Get or create DynamoDB resource.

    Returns:
        boto3 DynamoDB resource
    """
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    return _dynamodb


def get_jwt_handler() -> JWTHandler:
    """Get or create JWT handler instance."""
    global _jwt_handler
    if _jwt_handler is None:
        _jwt_handler = JWTHandler(secret_key=JWT_SECRET_KEY)
    return _jwt_handler


def create_response(
    status_code: int,
    body: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Create API Gateway response with CORS headers.

    Args:
        status_code: HTTP status code
        body: Response body dictionary
        headers: Optional additional headers

    Returns:
        API Gateway response dictionary
    """
    default_headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
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


async def handle_chat_send(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Handle POST /chat/send - Send message to agent.

    Request body:
        {
            "message": "User message",
            "session_id": "optional-existing-session"
        }

    Response:
        {
            "session_id": "uuid",
            "message": "Agent response",
            "state": "active"
        }

    Args:
        event: API Gateway event
        context: Lambda context

    Returns:
        API Gateway response
    """
    logger.info("path=</chat/send> | handling chat message")

    try:
        # Verify JWT token
        headers = event.get("headers", {})
        auth_header = headers.get("authorization", "")

        if not auth_header.startswith("Bearer "):
            return create_response(401, {"error": "Missing Authorization header"})

        access_token = auth_header.replace("Bearer ", "")
        jwt_handler = get_jwt_handler()
        payload = jwt_handler.verify_token(access_token, expected_type="access")
        user_id = payload.sub

        # Parse request body
        body = json.loads(event.get("body", "{}"))
        message = body.get("message", "").strip()
        session_id = body.get("session_id")

        if not message:
            return create_response(400, {"error": "Message is required"})

        logger.info(
            "user_id=<%s>, message_length=<%d> | processing chat message",
            user_id,
            len(message),
        )

        # Get or create chat session
        dynamodb = get_dynamodb()
        sessions_table = dynamodb.Table(CHAT_SESSIONS_TABLE_NAME)

        if session_id:
            # Load existing session
            response = sessions_table.get_item(Key={"session_id": session_id})
            if "Item" not in response:
                return create_response(404, {"error": "Session not found"})

            chat_session = ChatSession.from_dynamodb(response["Item"])
        else:
            # Create new session
            session_id = str(uuid.uuid4())
            chat_session = ChatSession(
                session_id=session_id,
                user_id=user_id,
                meeting_id=None,  # No specific meeting for general chat
                state=ChatSessionState.ACTIVE,
                expires_at=datetime.now(UTC) + timedelta(hours=2),
            )

        # Add user message
        chat_session.add_message("user", message)

        # Run agent
        logger.info(
            "session_id=<%s> | running meeting coordinator agent",
            session_id,
        )

        agent_response = await run_meeting_coordinator(
            user_id=user_id,
            session_id=session_id,
            message=message,
        )

        # Add agent response
        chat_session.add_message("assistant", agent_response)

        # Save session
        sessions_table.put_item(Item=chat_session.to_dynamodb())

        logger.info(
            "session_id=<%s>, response_length=<%d> | chat response sent",
            session_id,
            len(agent_response),
        )

        return create_response(
            200,
            {
                "session_id": session_id,
                "message": agent_response,
                "state": chat_session.state.value,
            },
        )

    except ValueError as e:
        logger.warning("error=<%s> | invalid request", str(e))
        return create_response(401, {"error": "Invalid or expired token"})

    except Exception as e:
        logger.error("error=<%s> | chat send failed", str(e), exc_info=True)
        return create_response(500, {"error": "Internal server error"})


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Main Lambda handler for agent endpoints.

    Routes requests to appropriate handler based on path and method.

    Args:
        event: API Gateway event
        context: Lambda context

    Returns:
        API Gateway response
    """
    # Support both API Gateway v1 (REST API) and v2 (HTTP API) event formats
    request_context = event.get("requestContext", {})
    http_context = request_context.get("http", {})

    method = event.get("httpMethod") or http_context.get("method", "")
    path = event.get("path") or event.get("rawPath", "")

    logger.info("method=<%s>, path=<%s> | processing request", method, path)

    # Handle OPTIONS for CORS
    if method == "OPTIONS":
        return create_response(200, {})

    # Route to handlers
    if path == "/chat/send" and method == "POST":
        # Run async handler
        import asyncio

        return asyncio.run(handle_chat_send(event, context))
    else:
        return create_response(404, {"error": "Not found"})
