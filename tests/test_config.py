"""Unit tests for configuration management."""

from pathlib import Path

import pytest

from exec_assistant.shared.config import Config, get_config, reload_config


class TestConfig:
    """Tests for Config class."""

    @pytest.fixture
    def config(self) -> Config:
        """Create a Config instance for testing."""
        # Find the config directory
        current_file = Path(__file__)
        project_root = current_file.parent.parent
        config_dir = project_root / "config"
        return Config(config_dir=config_dir)

    def test_load_agents_config(self, config: Config) -> None:
        """Test loading agents.yaml configuration."""
        assert config.agents_config is not None
        assert "meeting_coordinator" in config.agents_config
        assert "budget_manager" in config.agents_config

    def test_load_meeting_types_config(self, config: Config) -> None:
        """Test loading meeting_types.yaml configuration."""
        assert config.meeting_types_config is not None
        assert "leadership_team" in config.meeting_types_config
        assert "one_on_one" in config.meeting_types_config

    def test_get_agent_config(self, config: Config) -> None:
        """Test getting agent configuration."""
        meeting_coordinator_config = config.get_agent_config("meeting_coordinator")
        assert meeting_coordinator_config is not None
        assert "enabled" in meeting_coordinator_config
        assert "model" in meeting_coordinator_config

    def test_get_agent_model(self, config: Config) -> None:
        """Test getting agent model."""
        model = config.get_agent_model("meeting_coordinator")
        assert model is not None
        assert "claude" in model.lower()

    def test_get_agent_enabled(self, config: Config) -> None:
        """Test checking if agent is enabled."""
        # Meeting coordinator should be enabled
        assert config.get_agent_enabled("meeting_coordinator") is True

        # Document manager should be disabled in Phase 1
        assert config.get_agent_enabled("document_manager") is False

    def test_get_prep_hours(self, config: Config) -> None:
        """Test getting prep hours for different meeting types."""
        # Leadership team meeting: 24 hours
        assert config.get_prep_hours("leadership_team") == 24

        # One-on-one: 12 hours
        assert config.get_prep_hours("one_on_one") == 12

        # QBR: 72 hours
        assert config.get_prep_hours("qbr") == 72

        # Unknown meeting type should use default
        default_hours = config.get_prep_hours("nonexistent_type")
        assert default_hours == config.settings.default_prep_hours_before

    def test_get_meeting_type_config(self, config: Config) -> None:
        """Test getting meeting type configuration."""
        lt_config = config.get_meeting_type_config("leadership_team")
        assert lt_config is not None
        assert "name" in lt_config
        assert "prep_questions" in lt_config
        assert "required_context" in lt_config

    def test_get_prep_questions(self, config: Config) -> None:
        """Test getting prep questions for a meeting type."""
        questions = config.get_prep_questions("leadership_team")
        assert isinstance(questions, list)
        assert len(questions) > 0
        assert all(isinstance(q, str) for q in questions)

    def test_get_required_context(self, config: Config) -> None:
        """Test getting required context agents for a meeting type."""
        context_agents = config.get_required_context("leadership_team")
        assert isinstance(context_agents, list)
        assert "budget_manager" in context_agents
        assert "big_rocks_manager" in context_agents

        # One-on-one should only need HR manager
        one_on_one_context = config.get_required_context("one_on_one")
        assert "hr_manager" in one_on_one_context

    def test_get_agenda_template(self, config: Config) -> None:
        """Test getting agenda template for a meeting type."""
        template = config.get_agenda_template("leadership_team")
        assert isinstance(template, str)
        assert len(template) > 0
        assert "agenda" in template.lower() or "meeting" in template.lower()

    def test_get_note_template(self, config: Config) -> None:
        """Test getting note template for a meeting type."""
        template = config.get_note_template("one_on_one")
        assert isinstance(template, str)
        assert len(template) > 0

    def test_get_meeting_detection_rules(self, config: Config) -> None:
        """Test getting meeting detection rules."""
        lt_rules = config.get_meeting_detection_rules("leadership_team")
        assert "keywords" in lt_rules
        assert isinstance(lt_rules["keywords"], list)
        assert len(lt_rules["keywords"]) > 0

        # One-on-one should have attendee limits
        one_on_one_rules = config.get_meeting_detection_rules("one_on_one")
        assert one_on_one_rules.get("min_attendees") == 2
        assert one_on_one_rules.get("max_attendees") == 2

    def test_settings_defaults(self, config: Config) -> None:
        """Test that settings have sensible defaults."""
        assert config.settings.aws_region is not None
        assert config.settings.environment in ["dev", "staging", "prod"]
        assert config.settings.log_level in ["DEBUG", "INFO", "WARNING", "ERROR"]
        assert config.settings.session_timeout_minutes > 0


class TestGlobalConfig:
    """Tests for global config instance."""

    def test_get_config_singleton(self) -> None:
        """Test that get_config returns the same instance."""
        config1 = get_config()
        config2 = get_config()
        assert config1 is config2

    def test_reload_config(self) -> None:
        """Test reloading configuration."""
        config1 = get_config()
        config2 = reload_config()
        # Should be different instances after reload
        assert config1 is not config2
