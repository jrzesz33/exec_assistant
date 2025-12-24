"""Structured logging utilities.

This module provides structured logging following the project's logging standards:
- Field-value pairs first: field=<value>
- Human message after pipe: | message
- Use %s interpolation (NOT f-strings)
- Lowercase, no punctuation in messages

Example:
    logger.info("user_id=<%s>, session_id=<%s> | processing chat message", user_id, session_id)
"""

import logging
import os
import sys


def get_logger(name: str) -> logging.Logger:
    """Get a configured logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Only configure if not already configured
    if not logger.handlers:
        # Get log level from environment (default: INFO)
        log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
        log_level = getattr(logging, log_level_str, logging.INFO)

        logger.setLevel(log_level)

        # Create console handler
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(log_level)

        # Simple format for CloudWatch (it adds timestamp automatically)
        # Format: [LEVEL] module_name | message
        formatter = logging.Formatter("[%(levelname)s] %(name)s | %(message)s")
        handler.setFormatter(formatter)

        logger.addHandler(handler)

        # Prevent propagation to root logger (avoid duplicate logs)
        logger.propagate = False

    return logger
