"""Test cases for bug fixes and regressions.

This module contains tests for specific bugs that have been fixed,
ensuring they don't regress in future changes.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from exec_assistant.agents.meeting_coordinator import run_meeting_coordinator


@pytest.mark.asyncio
class TestBugFixes:
    """Test suite for specific bug fixes."""

    async def test_bug_response_message_dict_access(
        self,
        test_session_id,
        test_user_id,
        clean_session_dir,
        mock_aws_services,
    ):
        """Test fix for: AttributeError - 'dict' object has no attribute 'content'.

        Bug: meeting_coordinator.py line 227 used attribute access on dict
        Original code: response.message.content[0].text
        Fixed code: response.message["content"][0]["text"]

        GitHub Issue: N/A (discovered in production CloudWatch logs)
        Fixed in: PR #XXX

        This test ensures the Strands SDK response format is correctly handled
        as a dictionary, not an object with attributes.
        """
        # Mock Strands SDK response in correct format (dict, not object)
        mock_response = MagicMock()
        mock_response.message = {
            "content": [{"text": "Hello! I'm your Meeting Coordinator."}],
            "role": "assistant",
        }
        mock_response.stop_reason = "end_turn"

        # Mock the agent.invoke_async to return our mock response
        with patch("exec_assistant.agents.meeting_coordinator.create_agent") as mock_create:
            mock_agent = MagicMock()
            mock_agent.invoke_async = AsyncMock(return_value=mock_response)
            mock_create.return_value = mock_agent

            # This should NOT raise AttributeError
            response = await run_meeting_coordinator(
                user_id=test_user_id,
                session_id=test_session_id,
                message="Hello",
            )

            # Verify response is extracted correctly
            assert response is not None
            assert isinstance(response, str)
            assert "Meeting Coordinator" in response

            # Verify invoke_async was called
            mock_agent.invoke_async.assert_called_once_with("Hello")

    async def test_bug_strands_response_format_variations(
        self,
        test_session_id,
        test_user_id,
        clean_session_dir,
        mock_aws_services,
    ):
        """Test handling of various Strands SDK response formats.

        This test ensures the code correctly handles different valid response
        formats that might be returned by different Strands SDK versions or models.
        """
        test_cases = [
            # Standard format
            {
                "message": {
                    "content": [{"text": "Response 1"}],
                    "role": "assistant",
                },
                "stop_reason": "end_turn",
                "expected": "Response 1",
            },
            # Multiple content blocks (should use first)
            {
                "message": {
                    "content": [
                        {"text": "First block"},
                        {"text": "Second block"},
                    ],
                    "role": "assistant",
                },
                "stop_reason": "end_turn",
                "expected": "First block",
            },
            # With tool use (still has text)
            {
                "message": {
                    "content": [
                        {"text": "Let me check that..."},
                        {
                            "toolUse": {
                                "toolUseId": "123",
                                "name": "get_upcoming_meetings",
                            }
                        },
                    ],
                    "role": "assistant",
                },
                "stop_reason": "tool_use",
                "expected": "Let me check that...",
            },
        ]

        for i, test_case in enumerate(test_cases):
            mock_response = MagicMock()
            mock_response.message = test_case["message"]
            mock_response.stop_reason = test_case["stop_reason"]

            with patch("exec_assistant.agents.meeting_coordinator.create_agent") as mock_create:
                mock_agent = MagicMock()
                mock_agent.invoke_async = AsyncMock(return_value=mock_response)
                mock_create.return_value = mock_agent

                response = await run_meeting_coordinator(
                    user_id=test_user_id,
                    session_id=f"{test_session_id}-{i}",
                    message=f"Test case {i}",
                )

                assert response == test_case["expected"], f"Test case {i} failed"

    async def test_bug_empty_response_handling(
        self,
        test_session_id,
        test_user_id,
        clean_session_dir,
        mock_aws_services,
    ):
        """Test handling of edge case: empty response from agent.

        This ensures the code gracefully handles empty or malformed responses
        without crashing.
        """
        # Mock response with empty text
        mock_response = MagicMock()
        mock_response.message = {
            "content": [{"text": ""}],
            "role": "assistant",
        }
        mock_response.stop_reason = "end_turn"

        with patch("exec_assistant.agents.meeting_coordinator.create_agent") as mock_create:
            mock_agent = MagicMock()
            mock_agent.invoke_async = AsyncMock(return_value=mock_response)
            mock_create.return_value = mock_agent

            # Should handle empty response without crashing
            response = await run_meeting_coordinator(
                user_id=test_user_id,
                session_id=test_session_id,
                message="Hello",
            )

            assert response == ""  # Empty string is valid

    async def test_bug_session_manager_env_check(
        self,
        test_session_id,
        clean_session_dir,
    ):
        """Test fix for: S3SessionManager used in local environment.

        Bug: When ENV is not set to 'local', code tries to use S3SessionManager
        without credentials, causing boto3 errors.

        This test ensures FileSessionManager is used when ENV=local.
        """
        from exec_assistant.agents.meeting_coordinator import create_session_manager

        # Ensure ENV is local
        os.environ["ENV"] = "local"

        session_manager = create_session_manager(test_session_id)

        # Verify it's a FileSessionManager (not S3SessionManager)
        from strands.session import FileSessionManager

        assert isinstance(session_manager, FileSessionManager)
        assert session_manager.session_id == test_session_id


@pytest.mark.asyncio
class TestRegressionPrevention:
    """Tests to prevent common regressions."""

    async def test_logging_no_fstrings(self):
        """Ensure logging statements don't use f-strings.

        Common mistake: Using f-strings in logging which prevents structured logging.
        Correct: Use %s placeholders.
        """
        import inspect

        from exec_assistant.agents import meeting_coordinator

        # Read source code
        source = inspect.getsource(meeting_coordinator)

        # Check for f-strings in logger calls (simple regex check)
        import re

        # Look for logger.X(f"...") pattern
        fstring_pattern = r'logger\.\w+\(f["\']'
        matches = re.findall(fstring_pattern, source)

        assert len(matches) == 0, f"Found f-strings in logging: {matches}"

    async def test_type_annotations_present(self):
        """Ensure all functions have type annotations.

        This prevents regressions where type annotations are accidentally removed.
        """
        import inspect

        from exec_assistant.agents.meeting_coordinator import (
            create_agent,
            create_session_manager,
            run_meeting_coordinator,
        )

        functions_to_check = [
            run_meeting_coordinator,
            create_agent,
            create_session_manager,
        ]

        for func in functions_to_check:
            sig = inspect.signature(func)

            # Check return annotation
            assert sig.return_annotation != inspect.Parameter.empty, (
                f"{func.__name__} missing return type annotation"
            )

            # Check parameter annotations
            for param_name, param in sig.parameters.items():
                if param_name in ["args", "kwargs"]:
                    continue  # *args, **kwargs don't need annotations

                assert param.annotation != inspect.Parameter.empty, (
                    f"{func.__name__} parameter '{param_name}' missing type annotation"
                )

    async def test_docstrings_present(self):
        """Ensure all public functions have docstrings.

        This prevents regressions where docstrings are accidentally removed.
        """
        from exec_assistant.agents.meeting_coordinator import (
            create_agent,
            create_session_manager,
            get_upcoming_meetings,
            run_meeting_coordinator,
            save_prep_response,
        )

        functions_to_check = [
            run_meeting_coordinator,
            create_agent,
            create_session_manager,
            get_upcoming_meetings,
            save_prep_response,
        ]

        for func in functions_to_check:
            assert func.__doc__ is not None, f"{func.__name__} missing docstring"
            assert len(func.__doc__.strip()) > 0, f"{func.__name__} has empty docstring"


if __name__ == "__main__":
    """Run bug fix tests directly."""
    pytest.main([__file__, "-v", "--tb=short"])
