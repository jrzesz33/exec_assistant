#!/usr/bin/env python3
"""Local agent testing script for development.

This script allows developers to interactively test the Meeting Coordinator agent
in a local environment without deploying to AWS.

Usage:
    python scripts/test_agent_local.py

Requirements:
    - Virtual environment must be activated
    - ENV=local (set automatically by this script)
    - Optional: AWS_BEDROCK_ENABLED=1 for real Bedrock calls (requires AWS credentials)
"""

import asyncio
import os
import sys
import uuid
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

# Set local environment
os.environ["ENV"] = "local"
os.environ["AWS_REGION"] = "us-east-1"
os.environ["CHAT_SESSIONS_TABLE_NAME"] = "test-chat-sessions"
os.environ["MEETINGS_TABLE_NAME"] = "test-meetings"
os.environ["JWT_SECRET_KEY"] = "test-secret-key"

# Check for Bedrock testing mode
BEDROCK_ENABLED = os.environ.get("AWS_BEDROCK_ENABLED", "0") == "1"

from exec_assistant.agents.meeting_coordinator import run_meeting_coordinator


def print_banner():
    """Print welcome banner."""
    print("\n" + "=" * 80)
    print("MEETING COORDINATOR AGENT - LOCAL TESTING")
    print("=" * 80)
    print(f"\nMode: {'REAL BEDROCK' if BEDROCK_ENABLED else 'MOCK (no AWS calls)'}")
    print(f"Environment: {os.environ.get('ENV', 'unknown')}")
    print(f"Session storage: .sessions/")
    print("\nCommands:")
    print("  - Type your message and press Enter")
    print("  - Type 'quit' or 'exit' to end session")
    print("  - Type 'new' to start a new session")
    print("  - Type 'history' to see conversation history")
    print("=" * 80 + "\n")


async def interactive_test():
    """Run interactive test session."""
    print_banner()

    if not BEDROCK_ENABLED:
        print("⚠️  Note: Running in MOCK mode (no real AWS API calls)")
        print("   Set AWS_BEDROCK_ENABLED=1 and configure AWS credentials to test with real Bedrock\n")

    session_id = f"local-test-{uuid.uuid4()}"
    user_id = "test-user"
    message_count = 0

    print(f"Session ID: {session_id}")
    print("\nReady! Start chatting with the Meeting Coordinator:\n")

    while True:
        try:
            # Get user input
            user_input = input("You: ").strip()

            if not user_input:
                continue

            # Handle commands
            if user_input.lower() in ["quit", "exit"]:
                print("\nEnding session. Goodbye!")
                break
            elif user_input.lower() == "new":
                session_id = f"local-test-{uuid.uuid4()}"
                message_count = 0
                print(f"\n✓ New session started: {session_id}\n")
                continue
            elif user_input.lower() == "history":
                print(f"\n✓ Messages in this session: {message_count}\n")
                continue

            # Run agent
            message_count += 1
            print("\nAgent: ", end="", flush=True)

            if BEDROCK_ENABLED:
                # Real Bedrock call
                try:
                    response = await run_meeting_coordinator(
                        user_id=user_id,
                        session_id=session_id,
                        message=user_input,
                    )
                    print(response)
                except Exception as e:
                    print(f"ERROR: {e}")
                    print("\nTip: Check AWS credentials and Bedrock model access")
            else:
                # Mock response for testing without AWS
                mock_responses = [
                    "Hello! I'm your Meeting Coordinator. How can I help you prepare for upcoming meetings?",
                    "Great! To help you prepare effectively, can you tell me about the meeting - who's attending and what's the main objective?",
                    "Thanks for that context. Let me help you think through the preparation. What outcomes are you hoping to achieve?",
                    "Based on what you've shared, here are some key areas to prepare...",
                ]
                response = mock_responses[min(message_count - 1, len(mock_responses) - 1)]
                print(response)

            print()  # Blank line after response

        except KeyboardInterrupt:
            print("\n\nSession interrupted. Goodbye!")
            break
        except Exception as e:
            print(f"\nERROR: {e}")
            print("Type 'quit' to exit or continue testing\n")


def run_example_test():
    """Run a quick example test without interaction."""
    print("\nRunning example test (non-interactive)...")

    session_id = f"example-{uuid.uuid4()}"
    user_id = "test-user"

    async def test():
        print(f"\nSession: {session_id}")
        print("\n1. Testing greeting:")
        print("   User: Hello, I need help with meeting prep")

        if BEDROCK_ENABLED:
            try:
                response = await run_meeting_coordinator(
                    user_id=user_id,
                    session_id=session_id,
                    message="Hello, I need help with meeting prep",
                )
                print(f"   Agent: {response}\n")
            except Exception as e:
                print(f"   ERROR: {e}\n")
        else:
            print(
                "   Agent: Hello! I'm your Meeting Coordinator. How can I help you prepare for upcoming meetings?\n"
            )

        print("✓ Example test completed\n")

    asyncio.run(test())


def main():
    """Main entry point."""
    if len(sys.argv) > 1 and sys.argv[1] == "--example":
        # Run quick example
        run_example_test()
    else:
        # Interactive mode
        try:
            asyncio.run(interactive_test())
        except KeyboardInterrupt:
            print("\nGoodbye!")


if __name__ == "__main__":
    main()
