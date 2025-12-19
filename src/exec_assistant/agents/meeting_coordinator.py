"""Meeting Coordinator Agent using AWS Nova via Strands SDK.

This agent helps users prepare for upcoming meetings by asking contextual questions,
gathering relevant information, and generating meeting materials.
"""

import logging
import os
from typing import Any

import boto3
from strands.agent import Agent
from strands.models import BedrockModel
from strands.session import S3SessionManager, FileSessionManager
from strands.tools import tool

logger = logging.getLogger(__name__)

# Environment variables
CHAT_SESSIONS_TABLE_NAME = os.environ.get("CHAT_SESSIONS_TABLE_NAME", "")
MEETINGS_TABLE_NAME = os.environ.get("MEETINGS_TABLE_NAME", "")
SESSIONS_BUCKET_NAME = os.environ.get("SESSIONS_BUCKET_NAME", "")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
ENV = os.environ.get("ENV", "local")  # local, dev, prod

# Lazy-initialized AWS clients
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


@tool
def get_upcoming_meetings(user_id: str, days: int = 7) -> list[dict[str, Any]]:
    """Get upcoming meetings for a user.

    Args:
        user_id: User identifier
        days: Number of days to look ahead (default 7)

    Returns:
        List of upcoming meetings with title, time, and attendees
    """
    logger.info("user_id=<%s>, days=<%d> | getting upcoming meetings", user_id, days)

    # For Phase 2: Return empty list (calendar integration in Phase 3+)
    # In future phases, this will query the meetings DynamoDB table
    return []


@tool
def save_prep_response(
    session_id: str,
    question: str,
    answer: str,
) -> bool:
    """Save user's response to a prep question.

    Args:
        session_id: Chat session ID
        question: Question that was asked
        answer: User's answer to the question

    Returns:
        True if saved successfully
    """
    logger.info(
        "session_id=<%s>, question_length=<%d> | saving prep response",
        session_id,
        len(question),
    )

    try:
        # For Phase 2: Just log it (full implementation in Phase 3+)
        # In future phases, update the prep_responses field in chat_sessions table
        # dynamodb = get_dynamodb()
        # sessions_table = dynamodb.Table(CHAT_SESSIONS_TABLE_NAME)
        # sessions_table.update_item(...)

        logger.debug(
            "session_id=<%s> | prep response: q=<%s>, a=<%s>",
            session_id,
            question[:50],
            answer[:50],
        )

        return True

    except Exception as e:
        logger.error(
            "session_id=<%s>, error=<%s> | failed to save prep response",
            session_id,
            str(e),
        )
        return False


def create_session_manager(session_id: str):
    """Create a session manager based on environment.

    Args:
        session_id: Unique session identifier

    Returns:
        SessionManager instance (FileSessionManager for local, S3SessionManager for production)
    """
    if ENV == "local":
        # Use file-based session manager for local development
        sessions_dir = os.path.join(os.getcwd(), ".sessions")
        os.makedirs(sessions_dir, exist_ok=True)
        logger.debug("session_id=<%s> | using FileSessionManager at %s", session_id, sessions_dir)
        return FileSessionManager(
            session_id=session_id,
            directory=sessions_dir,
        )
    else:
        # Use S3 session manager for production
        if not SESSIONS_BUCKET_NAME:
            raise ValueError("SESSIONS_BUCKET_NAME environment variable required for non-local environments")
        logger.debug(
            "session_id=<%s>, bucket=<%s> | using S3SessionManager",
            session_id,
            SESSIONS_BUCKET_NAME,
        )
        return S3SessionManager(
            session_id=session_id,
            bucket=SESSIONS_BUCKET_NAME,
            region_name=AWS_REGION,
        )


def create_agent(session_id: str) -> Agent:
    """Create Meeting Coordinator agent with proper session management.

    Args:
        session_id: Unique session identifier

    Returns:
        Configured Agent instance
    """
    # Configure AWS Nova Lite model via Bedrock
    model = BedrockModel(
        model_id="us.amazon.nova-lite-v1:0",  # AWS Nova Lite - balanced performance/cost
        region_name=AWS_REGION,
        temperature=0.7,
    )

    # Create session manager based on environment
    session_manager = create_session_manager(session_id)

    # Create Meeting Coordinator agent
    return Agent(
        name="Meeting Coordinator",
        model=model,
        session_manager=session_manager,
        system_prompt="""You are a Meeting Coordinator assistant. Your role is to help executives prepare for upcoming meetings.

Your capabilities:
- Help users prepare for meetings by asking relevant contextual questions
- Understand meeting purpose, attendees, and expected outcomes
- Gather information about what the user wants to accomplish
- Provide helpful suggestions for meeting agendas and discussion topics
- Be proactive in identifying potential issues or opportunities

Your personality:
- Professional but conversational
- Concise and to-the-point
- Ask one question at a time to avoid overwhelming the user
- Focus on actionable insights and practical suggestions

Guidelines:
- Always greet the user warmly on first contact
- Ask clarifying questions to understand their needs
- Provide specific, actionable advice
- Keep responses under 3-4 sentences unless specifically asked for more detail
- If a user asks about a meeting, help them think through preparation steps

Remember: You're an executive's trusted assistant, not just a chatbot. Be helpful, efficient, and respectful of their time.""",
        tools=[get_upcoming_meetings, save_prep_response],
    )


async def run_meeting_coordinator(
    user_id: str,
    session_id: str,
    message: str,
) -> str:
    """Run the Meeting Coordinator agent for a user message.

    Args:
        user_id: User identifier
        session_id: Chat session identifier
        message: User's message to the agent

    Returns:
        Agent's response message

    Raises:
        Exception: If agent execution fails
    """
    logger.info(
        "user_id=<%s>, session_id=<%s>, message_length=<%d> | running meeting coordinator",
        user_id,
        session_id,
        len(message),
    )

    try:
        # Create agent instance with session-specific session manager
        agent = create_agent(session_id)

        # Execute agent with user message
        response = await agent.run(
            user_message=message,
        )

        logger.info(
            "session_id=<%s>, response_length=<%d> | agent response generated",
            session_id,
            len(response.content),
        )

        return response.content

    except Exception as e:
        logger.error(
            "session_id=<%s>, error=<%s> | agent execution failed",
            session_id,
            str(e),
            exc_info=True,
        )
        raise
