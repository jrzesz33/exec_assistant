"""Configuration management for Executive Assistant system.

Loads configuration from:
1. Environment variables (.env file)
2. YAML configuration files (agents.yaml, meeting_types.yaml)
3. Default values

Usage:
    from exec_assistant.shared.config import get_config

    config = get_config()
    model = config.get_agent_model("meeting_coordinator")
"""

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # AWS Configuration
    aws_region: str = Field(default="us-east-1")
    aws_account_id: str | None = None

    # Bedrock Model Configuration
    bedrock_model: str = Field(default="anthropic.claude-3-5-sonnet-20241022-v2:0")
    bedrock_region: str = Field(default="us-east-1")

    # DynamoDB Tables
    dynamodb_meetings_table: str = Field(default="exec-assistant-meetings-dev")
    dynamodb_chat_sessions_table: str = Field(default="exec-assistant-chat-sessions-dev")
    dynamodb_endpoint: str | None = None  # For local DynamoDB

    # S3 Buckets
    s3_documents_bucket: str = Field(default="exec-assistant-documents-dev")
    s3_sessions_bucket: str = Field(default="exec-assistant-sessions-dev")

    # KMS
    kms_key_id: str | None = None

    # Calendar Integration
    calendar_api_type: str = Field(default="google")  # or "microsoft"
    google_calendar_oauth_client_id: str | None = None
    google_calendar_oauth_client_secret: str | None = None
    google_calendar_credentials_path: str = Field(
        default="~/.credentials/calendar_credentials.json"
    )
    google_calendar_token_path: str = Field(default="~/.credentials/calendar_token.json")

    # Microsoft Graph (alternative)
    microsoft_graph_client_id: str | None = None
    microsoft_graph_client_secret: str | None = None
    microsoft_graph_tenant_id: str | None = None

    # Slack Configuration
    slack_bot_token: str | None = None
    slack_app_token: str | None = None
    slack_signing_secret: str | None = None
    slack_user_id: str | None = None
    slack_webhook_url: str | None = None

    # Twilio (SMS)
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_from_phone_number: str | None = None
    twilio_to_phone_number: str | None = None

    # Email (SendGrid or SES)
    sendgrid_api_key: str | None = None
    sendgrid_from_email: str | None = None
    ses_from_email: str | None = None
    ses_region: str | None = None

    # Integration Services
    pagerduty_api_key: str | None = None
    pagerduty_service_id: str | None = None
    servicenow_instance: str | None = None
    servicenow_username: str | None = None
    servicenow_password: str | None = None

    # Application Configuration
    environment: str = Field(default="dev")
    log_level: str = Field(default="INFO")
    log_format: str = Field(default="json")

    # Session Management
    session_timeout_minutes: int = Field(default=30)
    session_cleanup_hours: int = Field(default=24)

    # Meeting Prep
    calendar_check_interval_hours: int = Field(default=2)
    default_prep_hours_before: int = Field(default=24)
    meeting_prep_timeout_minutes: int = Field(default=60)

    # Feature Flags
    enable_sms_notifications: bool = Field(default=False)
    enable_email_notifications: bool = Field(default=False)
    enable_voice_memos: bool = Field(default=False)
    enable_post_meeting_processing: bool = Field(default=False)

    # Development/Testing
    use_local_dynamodb: bool = Field(default=False)
    skip_signature_verification: bool = Field(default=False)
    test_mode: bool = Field(default=False)
    mock_calendar_api: bool = Field(default=False)
    mock_bedrock: bool = Field(default=False)


class Config:
    """Configuration manager for Executive Assistant system."""

    def __init__(self, config_dir: Path | None = None) -> None:
        """Initialize configuration.

        Args:
            config_dir: Path to config directory (defaults to project root/config)
        """
        self.settings = Settings()

        # Determine config directory
        if config_dir is None:
            # Try to find config directory relative to this file
            current_file = Path(__file__)
            project_root = current_file.parent.parent.parent.parent
            config_dir = project_root / "config"

        self.config_dir = Path(config_dir)

        # Load YAML configurations
        self.agents_config: dict[str, Any] = {}
        self.meeting_types_config: dict[str, Any] = {}

        self._load_yaml_configs()

    def _load_yaml_configs(self) -> None:
        """Load YAML configuration files."""
        # Load agents.yaml
        agents_file = self.config_dir / "agents.yaml"
        if agents_file.exists():
            logger.debug("config_file=<%s> | loading agents configuration", agents_file)
            with agents_file.open() as f:
                self.agents_config = yaml.safe_load(f) or {}
        else:
            logger.warning("config_file=<%s> | agents config file not found", agents_file)

        # Load meeting_types.yaml
        meeting_types_file = self.config_dir / "meeting_types.yaml"
        if meeting_types_file.exists():
            logger.debug(
                "config_file=<%s> | loading meeting types configuration",
                meeting_types_file,
            )
            with meeting_types_file.open() as f:
                self.meeting_types_config = yaml.safe_load(f) or {}
        else:
            logger.warning(
                "config_file=<%s> | meeting types config file not found",
                meeting_types_file,
            )

    def get_agent_config(self, agent_name: str) -> dict[str, Any]:
        """Get configuration for a specific agent.

        Args:
            agent_name: Name of the agent (e.g., "meeting_coordinator")

        Returns:
            Agent configuration dict
        """
        return self.agents_config.get(agent_name, {})

    def get_agent_model(self, agent_name: str) -> str:
        """Get model ID for a specific agent.

        Args:
            agent_name: Name of the agent

        Returns:
            Bedrock model ID
        """
        agent_config = self.get_agent_config(agent_name)
        return agent_config.get("model", self.settings.bedrock_model)

    def get_agent_enabled(self, agent_name: str) -> bool:
        """Check if an agent is enabled.

        Args:
            agent_name: Name of the agent

        Returns:
            True if agent is enabled
        """
        agent_config = self.get_agent_config(agent_name)
        return agent_config.get("enabled", False)

    def get_prep_hours(self, meeting_type: str) -> int:
        """Get prep hours before meeting for a meeting type.

        Args:
            meeting_type: Meeting type (e.g., "leadership_team")

        Returns:
            Hours before meeting to trigger prep
        """
        meeting_coordinator_config = self.get_agent_config("meeting_coordinator")
        prep_timing = meeting_coordinator_config.get("prep_timing", {})
        return prep_timing.get(meeting_type, self.settings.default_prep_hours_before)

    def get_meeting_type_config(self, meeting_type: str) -> dict[str, Any]:
        """Get configuration for a meeting type.

        Args:
            meeting_type: Meeting type (e.g., "leadership_team")

        Returns:
            Meeting type configuration dict
        """
        return self.meeting_types_config.get(meeting_type, {})

    def get_prep_questions(self, meeting_type: str) -> list[str]:
        """Get prep questions for a meeting type.

        Args:
            meeting_type: Meeting type

        Returns:
            List of prep questions
        """
        meeting_config = self.get_meeting_type_config(meeting_type)
        return meeting_config.get("prep_questions", [])

    def get_required_context(self, meeting_type: str) -> list[str]:
        """Get required context agents for a meeting type.

        Args:
            meeting_type: Meeting type

        Returns:
            List of agent names to gather context from
        """
        meeting_config = self.get_meeting_type_config(meeting_type)
        return meeting_config.get("required_context", [])

    def get_agenda_template(self, meeting_type: str) -> str:
        """Get agenda template for a meeting type.

        Args:
            meeting_type: Meeting type

        Returns:
            Agenda template string
        """
        meeting_config = self.get_meeting_type_config(meeting_type)
        return meeting_config.get("agenda_template", "")

    def get_note_template(self, meeting_type: str) -> str:
        """Get note template for a meeting type.

        Args:
            meeting_type: Meeting type

        Returns:
            Note template string
        """
        meeting_config = self.get_meeting_type_config(meeting_type)
        return meeting_config.get("note_template", "")

    def get_meeting_detection_rules(self, meeting_type: str) -> dict[str, Any]:
        """Get detection rules for a meeting type.

        Args:
            meeting_type: Meeting type

        Returns:
            Detection rules dict (keywords, min/max attendees)
        """
        meeting_coordinator_config = self.get_agent_config("meeting_coordinator")
        detection_rules = meeting_coordinator_config.get("meeting_type_detection", {})
        return detection_rules.get(meeting_type, {})


# Global config instance
_config: Config | None = None


def get_config(config_dir: Path | None = None) -> Config:
    """Get global configuration instance.

    Args:
        config_dir: Optional config directory path (only used on first call)

    Returns:
        Config instance
    """
    global _config
    if _config is None:
        _config = Config(config_dir=config_dir)
    return _config


def reload_config(config_dir: Path | None = None) -> Config:
    """Reload configuration (useful for testing).

    Args:
        config_dir: Optional config directory path

    Returns:
        New Config instance
    """
    global _config
    _config = Config(config_dir=config_dir)
    return _config
