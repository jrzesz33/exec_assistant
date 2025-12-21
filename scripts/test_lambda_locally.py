#!/usr/bin/env python3
"""Local Lambda test harness for testing Lambda functions before deployment.

This script simulates the AWS Lambda environment locally, allowing you to:
- Test Lambda handlers with mock AWS services
- Send test requests (API Gateway events)
- See full stack traces for debugging
- Use real AWS services with a flag

Usage:
    python scripts/test_lambda_locally.py --event test_events/chat_message.json
    python scripts/test_lambda_locally.py --event test_events/chat_message.json --real-aws
    python scripts/test_lambda_locally.py --handler auth_handler --event test_events/auth_token.json

Examples:
    # Test with mocked AWS
    python scripts/test_lambda_locally.py --event test_events/chat_message.json

    # Test with real Bedrock
    export AWS_BEDROCK_ENABLED=1
    python scripts/test_lambda_locally.py --event test_events/chat_message.json --real-aws

    # Test specific handler
    python scripts/test_lambda_locally.py --handler agent_handler --event test_events/chat_message.json
"""

import argparse
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# ANSI color codes
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"


class LambdaContext:
    """Mock AWS Lambda context object."""

    def __init__(
        self,
        function_name: str = "test-function",
        memory_limit: int = 512,
        timeout: int = 30,
    ):
        """Initialize Lambda context.

        Args:
            function_name: Lambda function name
            memory_limit: Memory limit in MB
            timeout: Timeout in seconds
        """
        self.function_name = function_name
        self.memory_limit_in_mb = str(memory_limit)
        self.invoked_function_arn = f"arn:aws:lambda:us-east-1:123456789012:function:{function_name}"
        self.aws_request_id = "test-request-id-12345"
        self.log_group_name = f"/aws/lambda/{function_name}"
        self.log_stream_name = "2024/01/01/[$LATEST]test-stream"
        self.remaining_time_in_millis = lambda: timeout * 1000

    def get_remaining_time_in_millis(self) -> int:
        """Get remaining execution time in milliseconds.

        Returns:
            Remaining time in milliseconds
        """
        return self.remaining_time_in_millis()


class LambdaTestHarness:
    """Harness for testing Lambda functions locally."""

    def __init__(self, use_real_aws: bool = False, verbose: bool = False):
        """Initialize test harness.

        Args:
            use_real_aws: Use real AWS services instead of mocks
            verbose: Print verbose output
        """
        self.use_real_aws = use_real_aws
        self.verbose = verbose
        self.setup_environment()

    def setup_environment(self) -> None:
        """Set up environment variables for Lambda simulation."""
        # Set environment based on real_aws flag
        if self.use_real_aws:
            os.environ["ENV"] = "local"  # Still use local for session management
            # Keep existing AWS credentials
            if self.verbose:
                print(f"{BLUE}Using real AWS services{RESET}")
        else:
            # Mock environment
            os.environ["ENV"] = "local"
            os.environ["AWS_ACCESS_KEY_ID"] = "testing"
            os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
            os.environ["AWS_SECURITY_TOKEN"] = "testing"
            os.environ["AWS_SESSION_TOKEN"] = "testing"
            if self.verbose:
                print(f"{BLUE}Using mocked AWS services{RESET}")

        # Common environment variables
        os.environ.setdefault("AWS_REGION", "us-east-1")
        os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
        os.environ.setdefault("CHAT_SESSIONS_TABLE_NAME", "exec-assistant-chat-sessions")
        os.environ.setdefault("MEETINGS_TABLE_NAME", "exec-assistant-meetings")
        os.environ.setdefault("SESSIONS_BUCKET_NAME", "exec-assistant-sessions")
        os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")

    def load_event(self, event_file: Path) -> dict[str, Any]:
        """Load event from JSON file.

        Args:
            event_file: Path to event JSON file

        Returns:
            Event dictionary

        Raises:
            FileNotFoundError: If event file doesn't exist
            json.JSONDecodeError: If event file is invalid JSON
        """
        if not event_file.exists():
            raise FileNotFoundError(f"Event file not found: {event_file}")

        with open(event_file) as f:
            event = json.load(f)

        if self.verbose:
            print(f"\n{BLUE}Loaded event from:{RESET} {event_file}")
            print(f"{BLUE}Event data:{RESET}")
            print(json.dumps(event, indent=2))

        return event

    def invoke_handler(
        self, handler_name: str, event: dict[str, Any], context: LambdaContext
    ) -> dict[str, Any]:
        """Invoke Lambda handler function.

        Args:
            handler_name: Handler module name (e.g., 'agent_handler', 'auth_handler')
            event: API Gateway event
            context: Lambda context

        Returns:
            Handler response

        Raises:
            ImportError: If handler cannot be imported
            Exception: If handler execution fails
        """
        print(f"\n{BOLD}{'='*60}{RESET}")
        print(f"{BOLD}Invoking Lambda Handler: {handler_name}{RESET}")
        print(f"{BOLD}{'='*60}{RESET}\n")

        # Import handler
        try:
            if handler_name == "agent_handler":
                from exec_assistant.interfaces.agent_handler import handler
            elif handler_name == "auth_handler":
                from exec_assistant.interfaces.auth_handler import handler
            else:
                raise ImportError(f"Unknown handler: {handler_name}")

            print(f"{GREEN}✓{RESET} Handler imported successfully\n")

        except ImportError as e:
            print(f"{RED}✗ Failed to import handler:{RESET} {e}")
            raise

        # Set up mocking if needed
        if not self.use_real_aws:
            from moto import mock_aws

            # Mock AWS services
            with mock_aws():
                # Create mock DynamoDB tables
                import boto3

                dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

                # Create chat sessions table
                dynamodb.create_table(
                    TableName=os.environ["CHAT_SESSIONS_TABLE_NAME"],
                    KeySchema=[{"AttributeName": "session_id", "KeyType": "HASH"}],
                    AttributeDefinitions=[
                        {"AttributeName": "session_id", "AttributeType": "S"}
                    ],
                    BillingMode="PAY_PER_REQUEST",
                )

                # Create meetings table
                dynamodb.create_table(
                    TableName=os.environ["MEETINGS_TABLE_NAME"],
                    KeySchema=[{"AttributeName": "meeting_id", "KeyType": "HASH"}],
                    AttributeDefinitions=[
                        {"AttributeName": "meeting_id", "AttributeType": "S"}
                    ],
                    BillingMode="PAY_PER_REQUEST",
                )

                print(f"{GREEN}✓{RESET} Mock DynamoDB tables created\n")

                # Invoke handler
                return self._execute_handler(handler, event, context)
        else:
            # Invoke with real AWS
            return self._execute_handler(handler, event, context)

    def _execute_handler(
        self, handler: Any, event: dict[str, Any], context: LambdaContext
    ) -> dict[str, Any]:
        """Execute handler and capture response.

        Args:
            handler: Lambda handler function
            event: API Gateway event
            context: Lambda context

        Returns:
            Handler response
        """
        print(f"{BLUE}Executing handler...{RESET}\n")

        try:
            response = handler(event, context)

            print(f"{GREEN}✓{RESET} Handler executed successfully\n")

            if self.verbose:
                print(f"{BLUE}Full response:{RESET}")
                print(json.dumps(response, indent=2))

            return response

        except Exception as e:
            print(f"{RED}✗ Handler execution failed:{RESET} {e}\n")
            print(f"{RED}Full stack trace:{RESET}")
            traceback.print_exc()
            raise

    def print_response(self, response: dict[str, Any]) -> None:
        """Print handler response in a readable format.

        Args:
            response: Handler response
        """
        print(f"\n{BOLD}{'='*60}{RESET}")
        print(f"{BOLD}Lambda Response{RESET}")
        print(f"{BOLD}{'='*60}{RESET}\n")

        # Status code
        status_code = response.get("statusCode", "UNKNOWN")
        if status_code == 200:
            status_color = GREEN
        elif 200 <= status_code < 300:
            status_color = GREEN
        elif 400 <= status_code < 500:
            status_color = YELLOW
        else:
            status_color = RED

        print(f"{BOLD}Status Code:{RESET} {status_color}{status_code}{RESET}")

        # Headers
        headers = response.get("headers", {})
        if headers:
            print(f"\n{BOLD}Headers:{RESET}")
            for key, value in headers.items():
                print(f"  {key}: {value}")

        # Body
        body = response.get("body", "")
        if body:
            print(f"\n{BOLD}Body:{RESET}")
            try:
                # Try to parse and pretty-print JSON
                body_json = json.loads(body)
                print(json.dumps(body_json, indent=2))
            except json.JSONDecodeError:
                # Not JSON, print as-is
                print(body)

        print(f"\n{BOLD}{'='*60}{RESET}\n")

    def validate_dynamodb_item(self, item: dict[str, Any], model_name: str = "") -> list[str]:
        """Validate DynamoDB item for common constraint violations.

        Args:
            item: DynamoDB item dictionary
            model_name: Name of the model (for error messages)

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Known GSI keys per table (from infrastructure/storage.py)
        gsi_keys = {
            "chat-sessions": ["user_id", "meeting_id"],
            "meetings": ["user_id", "start_time"],
            "action-items": ["meeting_id", "owner"],
            "users": ["google_id", "email"],
        }

        # Check for empty strings in any field
        for key, value in item.items():
            if isinstance(value, str) and value == "":
                # Determine if this field is a GSI key
                is_gsi_key = any(key in keys for keys in gsi_keys.values())

                if is_gsi_key:
                    errors.append(
                        f"{model_name}.{key} is an empty string (violates GSI constraint). "
                        f"Use None or omit the field instead."
                    )
                else:
                    # Warn about empty strings in non-GSI fields (best practice)
                    errors.append(
                        f"{model_name}.{key} is an empty string (consider using None instead)"
                    )

        return errors

    def validate_response(self, response: dict[str, Any]) -> bool:
        """Validate handler response format and DynamoDB operations.

        Args:
            response: Handler response

        Returns:
            True if response is valid, False otherwise
        """
        print(f"{BOLD}Validating response...{RESET}\n")

        checks = []

        # Check required fields
        if "statusCode" not in response:
            checks.append(f"{RED}✗{RESET} Missing 'statusCode' field")
        else:
            checks.append(f"{GREEN}✓{RESET} Has 'statusCode' field")

        if "headers" not in response:
            checks.append(f"{YELLOW}⚠{RESET} Missing 'headers' field (optional)")
        else:
            checks.append(f"{GREEN}✓{RESET} Has 'headers' field")

        if "body" not in response:
            checks.append(f"{RED}✗{RESET} Missing 'body' field")
        else:
            checks.append(f"{GREEN}✓{RESET} Has 'body' field")

            # Validate body is JSON string
            try:
                json.loads(response["body"])
                checks.append(f"{GREEN}✓{RESET} Body is valid JSON")
            except json.JSONDecodeError:
                checks.append(f"{RED}✗{RESET} Body is not valid JSON")

        # Print checks
        for check in checks:
            print(check)

        # Return overall status
        is_valid = "✗" not in "".join(checks)
        print()
        if is_valid:
            print(f"{GREEN}✓ Response format is valid{RESET}\n")
        else:
            print(f"{RED}✗ Response format is invalid{RESET}\n")

        return is_valid


def create_sample_events() -> None:
    """Create sample event files if they don't exist."""
    events_dir = PROJECT_ROOT / "test_events"
    events_dir.mkdir(exist_ok=True)

    # Sample chat message event
    chat_message_event = {
        "httpMethod": "POST",
        "path": "/chat/send",
        "headers": {
            "authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test-token",
            "content-type": "application/json",
        },
        "body": json.dumps({"message": "Hello, I need help preparing for a meeting"}),
    }

    chat_file = events_dir / "chat_message.json"
    if not chat_file.exists():
        with open(chat_file, "w") as f:
            json.dump(chat_message_event, f, indent=2)
        print(f"{GREEN}Created sample event:{RESET} {chat_file}")

    # Sample auth token event
    auth_token_event = {
        "httpMethod": "POST",
        "path": "/auth/token",
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"user_id": "test-user"}),
    }

    auth_file = events_dir / "auth_token.json"
    if not auth_file.exists():
        with open(auth_file, "w") as f:
            json.dump(auth_token_event, f, indent=2)
        print(f"{GREEN}Created sample event:{RESET} {auth_file}")


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 = success, 1 = failure)
    """
    parser = argparse.ArgumentParser(
        description="Test Lambda functions locally",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--event",
        type=Path,
        help="Path to event JSON file (e.g., test_events/chat_message.json)",
    )
    parser.add_argument(
        "--handler",
        type=str,
        default="agent_handler",
        choices=["agent_handler", "auth_handler"],
        help="Handler to invoke (default: agent_handler)",
    )
    parser.add_argument(
        "--real-aws",
        action="store_true",
        help="Use real AWS services instead of mocks (requires credentials)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print verbose output including full event and response",
    )
    parser.add_argument(
        "--create-samples",
        action="store_true",
        help="Create sample event files and exit",
    )

    args = parser.parse_args()

    # Create sample events if requested
    if args.create_samples:
        create_sample_events()
        return 0

    # Validate arguments
    if not args.event:
        print(f"{RED}Error:{RESET} --event is required")
        print("\nRun with --create-samples to generate sample event files:")
        print("  python scripts/test_lambda_locally.py --create-samples")
        return 1

    try:
        # Create test harness
        harness = LambdaTestHarness(
            use_real_aws=args.real_aws,
            verbose=args.verbose,
        )

        # Load event
        event = harness.load_event(args.event)

        # Create Lambda context
        context = LambdaContext(
            function_name=f"exec-assistant-{args.handler.replace('_', '-')}",
            memory_limit=512,
            timeout=30,
        )

        # Invoke handler
        response = harness.invoke_handler(args.handler, event, context)

        # Print response
        harness.print_response(response)

        # Validate response
        is_valid = harness.validate_response(response)

        # Return exit code based on validation
        if is_valid and response.get("statusCode") == 200:
            print(f"{GREEN}{BOLD}✓ Lambda test successful{RESET}\n")
            return 0
        else:
            print(f"{YELLOW}{BOLD}⚠ Lambda test completed with issues{RESET}\n")
            return 1

    except FileNotFoundError as e:
        print(f"{RED}Error:{RESET} {e}")
        print("\nCreate event file or run with --create-samples:")
        print("  python scripts/test_lambda_locally.py --create-samples")
        return 1

    except Exception as e:
        print(f"\n{RED}{BOLD}✗ Lambda test failed{RESET}")
        print(f"{RED}Error:{RESET} {e}\n")
        if args.verbose:
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
