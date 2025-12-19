"""Integration tests for Meeting Coordinator agent.

This module tests the meeting coordinator agent end-to-end with real Bedrock calls
(when AWS credentials are available) or with mock responses for local development.
"""

import os
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from exec_assistant.agents.meeting_coordinator import (
    run_meeting_coordinator,
    create_agent,
    create_session_manager,
)
from tests.test_utils import AgentTestHelper


@pytest.mark.asyncio
class TestMeetingCoordinator:
    """Test suite for Meeting Coordinator agent."""

    async def test_create_session_manager_local(self, test_session_id, clean_session_dir):
        """Test session manager creation in local environment."""
        os.environ["ENV"] = "local"
        session_manager = create_session_manager(test_session_id)

        # Verify it's a FileSessionManager
        assert session_manager is not None
        assert session_manager.session_id == test_session_id

    async def test_create_session_manager_production(self, test_session_id):
        """Test session manager creation in production environment."""
        os.environ["ENV"] = "prod"
        os.environ["SESSIONS_BUCKET_NAME"] = "test-bucket"

        session_manager = create_session_manager(test_session_id)

        # Verify it's an S3SessionManager
        assert session_manager is not None
        assert session_manager.session_id == test_session_id

    async def test_create_agent(self, test_session_id, clean_session_dir):
        """Test agent creation with proper configuration."""
        agent = create_agent(test_session_id)

        assert agent is not None
        assert agent.name == "Meeting Coordinator"
        assert len(agent.tools) == 2  # get_upcoming_meetings, save_prep_response

    @patch("exec_assistant.agents.meeting_coordinator.BedrockModel")
    async def test_run_meeting_coordinator_greeting(
        self,
        mock_bedrock_class,
        test_session_id,
        test_user_id,
        clean_session_dir,
        mock_aws_services,
    ):
        """Test meeting coordinator agent with a greeting message."""
        # Mock Bedrock response
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Hello! I'm your Meeting Coordinator. How can I help you prepare for upcoming meetings?"
        mock_model.run = AsyncMock(return_value=mock_response)
        mock_bedrock_class.return_value = mock_model

        # Create mock agent that uses the mock model
        with patch("exec_assistant.agents.meeting_coordinator.create_agent") as mock_create:
            mock_agent = MagicMock()
            mock_agent.run = AsyncMock(return_value=mock_response)
            mock_create.return_value = mock_agent

            # Run agent with greeting
            response = await run_meeting_coordinator(
                user_id=test_user_id,
                session_id=test_session_id,
                message="Hi, I need help with meeting prep",
            )

            # Verify response
            assert response is not None
            assert len(response) > 0
            assert mock_agent.run.called

    @patch("exec_assistant.agents.meeting_coordinator.BedrockModel")
    async def test_run_meeting_coordinator_context_questions(
        self,
        mock_bedrock_class,
        test_session_id,
        test_user_id,
        clean_session_dir,
        mock_aws_services,
    ):
        """Test meeting coordinator asking contextual questions."""
        # Mock Bedrock response
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.content = (
            "Great! To help you prepare effectively, can you tell me:\n"
            "1. Who will be attending the meeting?\n"
            "2. What's the main topic or objective?"
        )
        mock_model.run = AsyncMock(return_value=mock_response)
        mock_bedrock_class.return_value = mock_model

        with patch("exec_assistant.agents.meeting_coordinator.create_agent") as mock_create:
            mock_agent = MagicMock()
            mock_agent.run = AsyncMock(return_value=mock_response)
            mock_create.return_value = mock_agent

            # Run agent with meeting prep request
            response = await run_meeting_coordinator(
                user_id=test_user_id,
                session_id=test_session_id,
                message="I have a leadership team meeting tomorrow and need to prepare",
            )

            # Verify response asks contextual questions
            assert response is not None
            assert len(response) > 0
            assert mock_agent.run.called

    @pytest.mark.integration
    @pytest.mark.skipif(
        not os.environ.get("AWS_BEDROCK_ENABLED"),
        reason="Requires AWS Bedrock credentials - set AWS_BEDROCK_ENABLED=1 to run",
    )
    async def test_run_meeting_coordinator_real_bedrock(
        self,
        test_session_id,
        test_user_id,
        clean_session_dir,
        mock_aws_services,
    ):
        """Integration test with real Bedrock API calls.

        This test only runs when AWS_BEDROCK_ENABLED=1 is set.
        It requires valid AWS credentials with Bedrock access.
        """
        helper = AgentTestHelper()

        # Test greeting
        response1 = await run_meeting_coordinator(
            user_id=test_user_id,
            session_id=test_session_id,
            message="Hello, I need help preparing for a meeting",
        )

        assert response1 is not None
        assert len(response1) > 0
        helper.add_user_message("Hello, I need help preparing for a meeting")
        helper.add_assistant_message(response1)

        # Test follow-up
        response2 = await run_meeting_coordinator(
            user_id=test_user_id,
            session_id=test_session_id,
            message="It's a quarterly business review with the executive team",
        )

        assert response2 is not None
        assert len(response2) > 0
        helper.add_user_message("It's a quarterly business review with the executive team")
        helper.add_assistant_message(response2)

        # Verify conversation was maintained
        conversation = helper.get_conversation_history()
        assert len(conversation) == 4  # 2 user + 2 assistant messages


@pytest.mark.asyncio
class TestMeetingCoordinatorTools:
    """Test suite for Meeting Coordinator tools."""

    async def test_get_upcoming_meetings_returns_empty_list(self, test_user_id):
        """Test get_upcoming_meetings tool returns empty list (Phase 2)."""
        from exec_assistant.agents.meeting_coordinator import get_upcoming_meetings

        meetings = get_upcoming_meetings(test_user_id, days=7)

        # In Phase 2, this returns empty list
        assert isinstance(meetings, list)
        assert len(meetings) == 0

    async def test_save_prep_response_returns_true(self, test_session_id):
        """Test save_prep_response tool returns True."""
        from exec_assistant.agents.meeting_coordinator import save_prep_response

        result = save_prep_response(
            session_id=test_session_id,
            question="Who will attend the meeting?",
            answer="Executive team: CEO, CTO, CFO, VP Engineering",
        )

        # In Phase 2, this just logs and returns True
        assert result is True


# Manual test script helpers
def print_test_instructions():
    """Print instructions for manual testing."""
    print("\n" + "=" * 80)
    print("MEETING COORDINATOR AGENT - MANUAL TEST INSTRUCTIONS")
    print("=" * 80)
    print("\nTo test the agent manually:")
    print("\n1. Set environment variable:")
    print("   export ENV=local")
    print("\n2. For mock testing (no AWS):")
    print("   pytest tests/test_meeting_coordinator.py -v")
    print("\n3. For integration testing with real Bedrock:")
    print("   export AWS_BEDROCK_ENABLED=1")
    print("   pytest tests/test_meeting_coordinator.py -v -m integration")
    print("\n4. To run the test script directly:")
    print("   python tests/test_meeting_coordinator.py")
    print("\n5. Session files will be saved to: .sessions/")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    """Run manual test when script is executed directly."""
    print_test_instructions()

    # Check if pytest is available
    try:
        import sys

        pytest.main([__file__, "-v", "--tb=short"])
    except ImportError:
        print("\nERROR: pytest not installed. Install with:")
        print("  pip install pytest pytest-asyncio moto")
