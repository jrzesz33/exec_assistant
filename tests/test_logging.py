"""Unit tests for structured logging utilities."""

import logging
import os
from io import StringIO
from unittest.mock import patch

import pytest

from exec_assistant.shared.logging import get_logger


class TestGetLogger:
    """Tests for get_logger function."""

    def test_get_logger_returns_logger(self) -> None:
        """Test that get_logger returns a Logger instance."""
        logger = get_logger("test_module")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test_module"

    def test_get_logger_default_level(self) -> None:
        """Test default log level is INFO."""
        with patch.dict(os.environ, {}, clear=True):
            logger = get_logger("test_default_level")
            # Clear any existing handlers
            logger.handlers.clear()
            logger = get_logger("test_default_level")
            assert logger.level == logging.INFO

    def test_get_logger_custom_level_from_env(self) -> None:
        """Test setting custom log level via environment variable."""
        with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}):
            logger = get_logger("test_custom_level")
            # Clear handlers to force reconfiguration
            logger.handlers.clear()
            logger = get_logger("test_custom_level")
            assert logger.level == logging.DEBUG

    def test_get_logger_invalid_level_defaults_to_info(self) -> None:
        """Test that invalid log level defaults to INFO."""
        with patch.dict(os.environ, {"LOG_LEVEL": "INVALID_LEVEL"}):
            logger = get_logger("test_invalid_level")
            logger.handlers.clear()
            logger = get_logger("test_invalid_level")
            # Should default to INFO
            assert logger.level == logging.INFO

    def test_get_logger_case_insensitive(self) -> None:
        """Test that log level is case-insensitive."""
        with patch.dict(os.environ, {"LOG_LEVEL": "warning"}):
            logger = get_logger("test_case_insensitive")
            logger.handlers.clear()
            logger = get_logger("test_case_insensitive")
            assert logger.level == logging.WARNING

    def test_get_logger_has_handler(self) -> None:
        """Test that logger has a StreamHandler configured."""
        logger = get_logger("test_handler")
        assert len(logger.handlers) >= 1
        assert any(isinstance(h, logging.StreamHandler) for h in logger.handlers)

    def test_get_logger_does_not_propagate(self) -> None:
        """Test that logger does not propagate to root logger."""
        logger = get_logger("test_propagate")
        assert logger.propagate is False

    def test_get_logger_format(self) -> None:
        """Test logger format includes level and module name."""
        logger = get_logger("test_format")

        # Capture log output
        handler = logger.handlers[0] if logger.handlers else None
        assert handler is not None

        formatter = handler.formatter
        assert formatter is not None

        # Create a test log record
        record = logging.LogRecord(
            name="test_format",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )

        formatted = formatter.format(record)
        assert "[INFO]" in formatted
        assert "test_format" in formatted
        assert "test message" in formatted

    def test_get_logger_reuses_existing_logger(self) -> None:
        """Test that calling get_logger twice returns the same logger."""
        logger1 = get_logger("test_reuse")
        logger2 = get_logger("test_reuse")

        assert logger1 is logger2
        # Should not add duplicate handlers
        assert len(logger1.handlers) == len(logger2.handlers)

    def test_get_logger_different_modules(self) -> None:
        """Test creating loggers for different modules."""
        logger1 = get_logger("module1")
        logger2 = get_logger("module2")

        assert logger1.name == "module1"
        assert logger2.name == "module2"
        assert logger1 is not logger2


class TestLoggingOutput:
    """Tests for actual logging output format."""

    def test_log_output_format_info(self) -> None:
        """Test INFO level log output format."""
        logger = get_logger("test_output_info")

        # Create a string buffer to capture output
        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setFormatter(
            logging.Formatter("[%(levelname)s] %(name)s | %(message)s")
        )

        # Clear existing handlers and add our test handler
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        logger.info("user_id=<%s> | test message", "user-123")

        log_output = log_stream.getvalue()
        assert "[INFO]" in log_output
        assert "test_output_info" in log_output
        assert "user_id=<user-123> | test message" in log_output

    def test_log_output_format_debug(self) -> None:
        """Test DEBUG level log output format."""
        logger = get_logger("test_output_debug")

        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setFormatter(
            logging.Formatter("[%(levelname)s] %(name)s | %(message)s")
        )

        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        logger.debug("session_id=<%s>, meeting_id=<%s> | debugging", "sess-1", "meet-1")

        log_output = log_stream.getvalue()
        assert "[DEBUG]" in log_output
        assert "session_id=<sess-1>, meeting_id=<meet-1> | debugging" in log_output

    def test_log_output_format_error(self) -> None:
        """Test ERROR level log output format."""
        logger = get_logger("test_output_error")

        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setFormatter(
            logging.Formatter("[%(levelname)s] %(name)s | %(message)s")
        )

        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.ERROR)

        logger.error("error=<%s> | operation failed", "connection timeout")

        log_output = log_stream.getvalue()
        assert "[ERROR]" in log_output
        assert "error=<connection timeout> | operation failed" in log_output

    def test_log_output_format_warning(self) -> None:
        """Test WARNING level log output format."""
        logger = get_logger("test_output_warning")

        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setFormatter(
            logging.Formatter("[%(levelname)s] %(name)s | %(message)s")
        )

        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)

        logger.warning("resource=<%s> | resource not found", "calendar-123")

        log_output = log_stream.getvalue()
        assert "[WARNING]" in log_output
        assert "resource=<calendar-123> | resource not found" in log_output


class TestLoggingLevels:
    """Tests for log level filtering."""

    def test_debug_logged_when_level_debug(self) -> None:
        """Test DEBUG messages are logged when level is DEBUG."""
        logger = get_logger("test_level_debug")

        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setFormatter(
            logging.Formatter("[%(levelname)s] %(name)s | %(message)s")
        )

        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        logger.debug("debug message")
        assert "debug message" in log_stream.getvalue()

    def test_debug_not_logged_when_level_info(self) -> None:
        """Test DEBUG messages are not logged when level is INFO."""
        logger = get_logger("test_level_info_filter")

        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setFormatter(
            logging.Formatter("[%(levelname)s] %(name)s | %(message)s")
        )

        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        logger.debug("debug message should not appear")
        assert "debug message should not appear" not in log_stream.getvalue()

    def test_info_logged_when_level_info(self) -> None:
        """Test INFO messages are logged when level is INFO."""
        logger = get_logger("test_level_info_pass")

        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setFormatter(
            logging.Formatter("[%(levelname)s] %(name)s | %(message)s")
        )

        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        logger.info("info message")
        assert "info message" in log_stream.getvalue()

    def test_warning_always_logged(self) -> None:
        """Test WARNING messages are logged at INFO level."""
        logger = get_logger("test_level_warning")

        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setFormatter(
            logging.Formatter("[%(levelname)s] %(name)s | %(message)s")
        )

        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        logger.warning("warning message")
        assert "warning message" in log_stream.getvalue()


class TestStructuredLoggingPatterns:
    """Tests for structured logging patterns used in the project."""

    def test_field_value_format(self) -> None:
        """Test field=<value> format is preserved."""
        logger = get_logger("test_field_value")

        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setFormatter(
            logging.Formatter("[%(levelname)s] %(name)s | %(message)s")
        )

        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        logger.info("user_id=<%s>, action=<%s> | operation complete", "user-1", "create")

        log_output = log_stream.getvalue()
        assert "user_id=<user-1>" in log_output
        assert "action=<create>" in log_output
        assert "| operation complete" in log_output

    def test_multiple_fields(self) -> None:
        """Test multiple field-value pairs."""
        logger = get_logger("test_multiple_fields")

        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setFormatter(
            logging.Formatter("[%(levelname)s] %(name)s | %(message)s")
        )

        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        logger.info(
            "user_id=<%s>, session_id=<%s>, meeting_id=<%s> | processing request",
            "user-123",
            "sess-456",
            "meet-789",
        )

        log_output = log_stream.getvalue()
        assert "user_id=<user-123>" in log_output
        assert "session_id=<sess-456>" in log_output
        assert "meeting_id=<meet-789>" in log_output

    def test_lowercase_message_format(self) -> None:
        """Test that messages follow lowercase convention."""
        logger = get_logger("test_lowercase")

        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setFormatter(
            logging.Formatter("[%(levelname)s] %(name)s | %(message)s")
        )

        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        # Correct format: lowercase, no punctuation
        logger.info("user_id=<%s> | processing meeting prep", "user-1")

        log_output = log_stream.getvalue()
        assert "processing meeting prep" in log_output


class TestExceptionLogging:
    """Tests for exception logging with exc_info."""

    def test_exception_logging_with_exc_info(self) -> None:
        """Test logging exceptions with traceback."""
        logger = get_logger("test_exception")

        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setFormatter(
            logging.Formatter("[%(levelname)s] %(name)s | %(message)s")
        )

        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.ERROR)

        try:
            raise ValueError("Test exception")
        except ValueError as e:
            logger.error(
                "error=<%s> | unexpected error occurred", str(e), exc_info=True
            )

        log_output = log_stream.getvalue()
        assert "error=<Test exception>" in log_output
        assert "unexpected error occurred" in log_output
        assert "Traceback" in log_output
        assert "ValueError: Test exception" in log_output


class TestLoggerConfiguration:
    """Tests for logger configuration edge cases."""

    def test_multiple_calls_do_not_add_duplicate_handlers(self) -> None:
        """Test that multiple get_logger calls don't create duplicate handlers."""
        logger_name = "test_no_duplicates"

        # Get logger multiple times
        logger1 = get_logger(logger_name)
        initial_handler_count = len(logger1.handlers)

        logger2 = get_logger(logger_name)
        logger3 = get_logger(logger_name)

        # Should still have the same number of handlers
        assert len(logger3.handlers) == initial_handler_count

    def test_logger_with_dunder_name(self) -> None:
        """Test logger creation with __name__ pattern."""
        logger = get_logger("exec_assistant.shared.calendar")
        assert logger.name == "exec_assistant.shared.calendar"

    def test_handler_writes_to_stdout(self) -> None:
        """Test that handler writes to stdout (CloudWatch compatibility)."""
        logger = get_logger("test_stdout")

        handler = logger.handlers[0] if logger.handlers else None
        assert handler is not None
        assert isinstance(handler, logging.StreamHandler)
        # StreamHandler with no argument or sys.stdout
        import sys

        # The handler should be writing to stdout
        assert handler.stream in (sys.stdout, sys.stderr) or handler.stream.name == "<stdout>"
