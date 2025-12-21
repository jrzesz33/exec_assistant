#!/usr/bin/env python3
"""Pre-deployment validation script for AWS Lambda deployments.

This script performs comprehensive validation checks before deploying to AWS:
- Runs all unit tests
- Runs integration tests (if AWS credentials available)
- Validates Lambda package can be built
- Checks for common runtime errors
- Verifies code quality and coverage

Usage:
    python scripts/validate_deployment.py [--full] [--component COMPONENT]

Examples:
    # Basic validation (unit tests + syntax checks)
    python scripts/validate_deployment.py

    # Full validation (includes integration tests)
    python scripts/validate_deployment.py --full

    # Validate specific component
    python scripts/validate_deployment.py --component meeting_coordinator
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# ANSI color codes for output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"


class ValidationResult:
    """Container for validation check results."""

    def __init__(self, name: str, passed: bool, message: str = "", details: str = ""):
        """Initialize validation result.

        Args:
            name: Name of the validation check
            passed: Whether the check passed
            message: Summary message
            details: Additional details
        """
        self.name = name
        self.passed = passed
        self.message = message
        self.details = details

    def __str__(self) -> str:
        """String representation of result."""
        status = f"{GREEN}✅ PASSED{RESET}" if self.passed else f"{RED}❌ FAILED{RESET}"
        return f"{status} {self.name}: {self.message}"


class DeploymentValidator:
    """Validator for pre-deployment checks."""

    def __init__(self, full_validation: bool = False, component: str | None = None):
        """Initialize validator.

        Args:
            full_validation: Run full validation including integration tests
            component: Specific component to validate (None = all)
        """
        self.full_validation = full_validation
        self.component = component
        self.results: list[ValidationResult] = []

    def run_command(
        self, cmd: list[str], description: str, check_returncode: bool = True
    ) -> subprocess.CompletedProcess:
        """Run a command and capture output.

        Args:
            cmd: Command to run
            description: Description for logging
            check_returncode: Raise exception on non-zero return code

        Returns:
            CompletedProcess result

        Raises:
            subprocess.CalledProcessError: If command fails and check_returncode is True
        """
        print(f"\n{BLUE}Running:{RESET} {description}")
        print(f"{BLUE}Command:{RESET} {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                check=check_returncode,
            )
            return result
        except subprocess.CalledProcessError as e:
            print(f"{RED}Command failed with return code {e.returncode}{RESET}")
            print(f"STDOUT:\n{e.stdout}")
            print(f"STDERR:\n{e.stderr}")
            raise

    def check_python_syntax(self) -> ValidationResult:
        """Check Python syntax for all source files.

        Returns:
            ValidationResult with syntax check status
        """
        print(f"\n{BOLD}{'='*60}{RESET}")
        print(f"{BOLD}Checking Python Syntax{RESET}")
        print(f"{BOLD}{'='*60}{RESET}")

        src_files = list((PROJECT_ROOT / "src").rglob("*.py"))
        test_files = list((PROJECT_ROOT / "tests").rglob("*.py"))
        all_files = src_files + test_files

        errors = []
        for file_path in all_files:
            try:
                with open(file_path) as f:
                    compile(f.read(), file_path, "exec")
            except SyntaxError as e:
                errors.append(f"{file_path.relative_to(PROJECT_ROOT)}: {e}")

        if errors:
            return ValidationResult(
                name="Python Syntax",
                passed=False,
                message=f"Found {len(errors)} syntax errors",
                details="\n".join(errors),
            )

        return ValidationResult(
            name="Python Syntax",
            passed=True,
            message=f"Checked {len(all_files)} files",
        )

    def check_imports(self) -> ValidationResult:
        """Check that all imports can be resolved.

        Returns:
            ValidationResult with import check status
        """
        print(f"\n{BOLD}{'='*60}{RESET}")
        print(f"{BOLD}Checking Import Resolution{RESET}")
        print(f"{BOLD}{'='*60}{RESET}")

        # Set local environment for imports
        os.environ["ENV"] = "local"
        os.environ["AWS_REGION"] = "us-east-1"

        modules_to_check = [
            "exec_assistant.agents.meeting_coordinator",
            "exec_assistant.interfaces.agent_handler",
            "exec_assistant.interfaces.auth_handler",
            "exec_assistant.shared.models",
            "exec_assistant.shared.auth",
        ]

        errors = []
        for module in modules_to_check:
            try:
                __import__(module)
                print(f"{GREEN}✓{RESET} {module}")
            except ImportError as e:
                errors.append(f"{module}: {e}")
                print(f"{RED}✗{RESET} {module}: {e}")

        if errors:
            return ValidationResult(
                name="Import Resolution",
                passed=False,
                message=f"{len(errors)} imports failed",
                details="\n".join(errors),
            )

        return ValidationResult(
            name="Import Resolution",
            passed=True,
            message=f"All {len(modules_to_check)} imports resolved",
        )

    def run_unit_tests(self) -> ValidationResult:
        """Run unit tests with pytest.

        Returns:
            ValidationResult with test status
        """
        print(f"\n{BOLD}{'='*60}{RESET}")
        print(f"{BOLD}Running Unit Tests{RESET}")
        print(f"{BOLD}{'='*60}{RESET}")

        # Set environment for tests
        env = os.environ.copy()
        env["ENV"] = "local"
        env["AWS_REGION"] = "us-east-1"

        cmd = [
            sys.executable,
            "-m",
            "pytest",
            "tests/",
            "-v",
            "-m",
            "not integration",  # Skip integration tests for unit test run
            "--tb=short",
        ]

        if self.component:
            cmd.append(f"tests/test_{self.component}.py")

        try:
            result = subprocess.run(
                cmd,
                cwd=PROJECT_ROOT,
                env=env,
                capture_output=True,
                text=True,
            )

            # Parse pytest output for pass/fail counts
            output = result.stdout + result.stderr
            print(output)

            if result.returncode == 0:
                # Extract test counts from output
                import re

                match = re.search(r"(\d+) passed", output)
                passed_count = int(match.group(1)) if match else 0

                return ValidationResult(
                    name="Unit Tests",
                    passed=True,
                    message=f"{passed_count} tests passed",
                )
            else:
                return ValidationResult(
                    name="Unit Tests",
                    passed=False,
                    message="Some tests failed",
                    details=output[-500:],  # Last 500 chars
                )

        except Exception as e:
            return ValidationResult(
                name="Unit Tests",
                passed=False,
                message=f"Test execution failed: {e}",
            )

    def run_integration_tests(self) -> ValidationResult:
        """Run integration tests with real AWS services.

        Returns:
            ValidationResult with integration test status
        """
        print(f"\n{BOLD}{'='*60}{RESET}")
        print(f"{BOLD}Running Integration Tests{RESET}")
        print(f"{BOLD}{'='*60}{RESET}")

        # Check if AWS credentials are available
        bedrock_enabled = os.environ.get("AWS_BEDROCK_ENABLED", "0") == "1"

        if not bedrock_enabled:
            print(f"{YELLOW}Skipping integration tests (AWS_BEDROCK_ENABLED not set){RESET}")
            return ValidationResult(
                name="Integration Tests",
                passed=True,
                message="Skipped (set AWS_BEDROCK_ENABLED=1 to run)",
            )

        env = os.environ.copy()
        env["ENV"] = "local"
        env["AWS_REGION"] = "us-east-1"
        env["AWS_BEDROCK_ENABLED"] = "1"

        cmd = [
            sys.executable,
            "-m",
            "pytest",
            "tests/",
            "-v",
            "-m",
            "integration",
            "--tb=short",
        ]

        if self.component:
            cmd.append(f"tests/test_{self.component}.py")

        try:
            result = subprocess.run(
                cmd,
                cwd=PROJECT_ROOT,
                env=env,
                capture_output=True,
                text=True,
            )

            output = result.stdout + result.stderr
            print(output)

            if result.returncode == 0:
                import re

                match = re.search(r"(\d+) passed", output)
                passed_count = int(match.group(1)) if match else 0

                return ValidationResult(
                    name="Integration Tests",
                    passed=True,
                    message=f"{passed_count} integration tests passed",
                )
            else:
                return ValidationResult(
                    name="Integration Tests",
                    passed=False,
                    message="Some integration tests failed",
                    details=output[-500:],
                )

        except Exception as e:
            return ValidationResult(
                name="Integration Tests",
                passed=False,
                message=f"Integration test execution failed: {e}",
            )

    def check_code_coverage(self) -> ValidationResult:
        """Check code coverage meets threshold.

        Returns:
            ValidationResult with coverage status
        """
        print(f"\n{BOLD}{'='*60}{RESET}")
        print(f"{BOLD}Checking Code Coverage{RESET}")
        print(f"{BOLD}{'='*60}{RESET}")

        env = os.environ.copy()
        env["ENV"] = "local"

        cmd = [
            sys.executable,
            "-m",
            "pytest",
            "tests/",
            "-m",
            "not integration",
            "--cov=src/exec_assistant",
            "--cov-report=term-missing",
            "--cov-report=html",
            "--cov-fail-under=70",
            "-q",
        ]

        try:
            result = subprocess.run(
                cmd,
                cwd=PROJECT_ROOT,
                env=env,
                capture_output=True,
                text=True,
            )

            output = result.stdout + result.stderr
            print(output)

            # Extract coverage percentage
            import re

            match = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", output)
            coverage = int(match.group(1)) if match else 0

            if result.returncode == 0:
                return ValidationResult(
                    name="Code Coverage",
                    passed=True,
                    message=f"{coverage}% (threshold: 70%)",
                )
            else:
                return ValidationResult(
                    name="Code Coverage",
                    passed=False,
                    message=f"{coverage}% (below threshold)",
                )

        except Exception as e:
            return ValidationResult(
                name="Code Coverage",
                passed=False,
                message=f"Coverage check failed: {e}",
            )

    def check_lambda_package(self) -> ValidationResult:
        """Check that Lambda package can be built.

        Returns:
            ValidationResult with package build status
        """
        print(f"\n{BOLD}{'='*60}{RESET}")
        print(f"{BOLD}Checking Lambda Package Build{RESET}")
        print(f"{BOLD}{'='*60}{RESET}")

        # Check if Pulumi infrastructure exists
        infra_dir = PROJECT_ROOT / "infrastructure"
        if not infra_dir.exists():
            return ValidationResult(
                name="Lambda Package Build",
                passed=True,
                message="Skipped (no infrastructure directory)",
            )

        # Check if Lambda build directory exists
        lambda_build_dir = infra_dir / ".lambda_build_agent"
        if not lambda_build_dir.exists():
            return ValidationResult(
                name="Lambda Package Build",
                passed=True,
                message="Not built yet (will be built on first pulumi up)",
            )

        # Check for package.zip
        package_zip = lambda_build_dir / "package.zip"
        if package_zip.exists():
            size_mb = package_zip.stat().st_size / (1024 * 1024)
            return ValidationResult(
                name="Lambda Package Build",
                passed=True,
                message=f"Package exists ({size_mb:.2f} MB)",
            )
        else:
            return ValidationResult(
                name="Lambda Package Build",
                passed=False,
                message="Package not found (run: cd infrastructure && pulumi up)",
            )

    def check_linting(self) -> ValidationResult:
        """Check code linting with ruff.

        Returns:
            ValidationResult with linting status
        """
        print(f"\n{BOLD}{'='*60}{RESET}")
        print(f"{BOLD}Checking Code Linting{RESET}")
        print(f"{BOLD}{'='*60}{RESET}")

        try:
            # Check if ruff is installed
            subprocess.run(
                [sys.executable, "-m", "ruff", "--version"],
                check=True,
                capture_output=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            return ValidationResult(
                name="Code Linting",
                passed=True,
                message="Skipped (ruff not installed)",
            )

        cmd = [sys.executable, "-m", "ruff", "check", "src/", "tests/"]

        try:
            result = subprocess.run(
                cmd,
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
            )

            output = result.stdout + result.stderr

            if result.returncode == 0:
                return ValidationResult(
                    name="Code Linting",
                    passed=True,
                    message="No linting errors",
                )
            else:
                return ValidationResult(
                    name="Code Linting",
                    passed=False,
                    message="Linting errors found",
                    details=output[-500:],
                )

        except Exception as e:
            return ValidationResult(
                name="Code Linting",
                passed=False,
                message=f"Linting check failed: {e}",
            )

    def print_report(self) -> None:
        """Print validation report."""
        print(f"\n{BOLD}{'='*60}{RESET}")
        print(f"{BOLD}DEPLOYMENT VALIDATION REPORT{RESET}")
        print(f"{BOLD}{'='*60}{RESET}\n")

        for result in self.results:
            print(result)
            if result.details and not result.passed:
                print(f"{YELLOW}Details:{RESET}")
                print(result.details[:500])  # Limit details output

        print(f"\n{BOLD}{'='*60}{RESET}")

        # Summary
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed

        if failed == 0:
            print(f"{GREEN}{BOLD}VALIDATION STATUS: ✅ READY FOR DEPLOYMENT{RESET}")
        else:
            print(f"{RED}{BOLD}VALIDATION STATUS: ❌ NOT READY ({failed} checks failed){RESET}")

        print(f"{BOLD}{'='*60}{RESET}\n")

    def validate(self) -> bool:
        """Run all validation checks.

        Returns:
            True if all checks passed, False otherwise
        """
        print(f"\n{BOLD}{'='*60}{RESET}")
        print(f"{BOLD}Starting Pre-Deployment Validation{RESET}")
        print(f"{BOLD}{'='*60}{RESET}")
        print(f"Full validation: {self.full_validation}")
        print(f"Component filter: {self.component or 'all'}")

        # Run checks
        self.results.append(self.check_python_syntax())
        self.results.append(self.check_imports())
        self.results.append(self.run_unit_tests())

        if self.full_validation:
            self.results.append(self.run_integration_tests())
            self.results.append(self.check_code_coverage())

        self.results.append(self.check_lambda_package())
        self.results.append(self.check_linting())

        # Print report
        self.print_report()

        # Return overall status
        return all(r.passed for r in self.results)


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 = success, 1 = failure)
    """
    parser = argparse.ArgumentParser(
        description="Validate deployment before pushing to AWS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run full validation including integration tests and coverage",
    )
    parser.add_argument(
        "--component",
        type=str,
        help="Validate specific component (e.g., meeting_coordinator)",
    )

    args = parser.parse_args()

    # Create validator and run
    validator = DeploymentValidator(
        full_validation=args.full,
        component=args.component,
    )

    success = validator.validate()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
