"""Meeting classification and prep trigger logic.

This module provides the MeetingClassifier class for:
- Classifying meetings by type based on keywords and attendee count
- Determining prep trigger timing (hours before meeting)
- Deciding when to send prep notifications

Configuration is loaded from config/agents.yaml.
"""

from datetime import datetime, timedelta
from pathlib import Path

import yaml

from exec_assistant.shared.logging import get_logger
from exec_assistant.shared.models import Meeting, MeetingType

logger = get_logger(__name__)


class MeetingClassifier:
    """Classifier for meeting types and prep trigger timing.

    This class loads configuration from agents.yaml and provides methods to:
    - Classify meetings into types based on keywords and attendee count
    - Calculate prep trigger time (hours before meeting)
    - Determine if prep should be triggered now

    Attributes:
        config: Dictionary containing meeting classification configuration
        prep_timing: Dictionary mapping meeting types to prep hours
        detection_rules: Dictionary of detection rules per meeting type
    """

    def __init__(self, config_path: str | None = None) -> None:
        """Initialize the meeting classifier.

        Args:
            config_path: Path to agents.yaml config file. If None, uses default
                location at config/agents.yaml relative to project root.

        Raises:
            FileNotFoundError: If config file does not exist
            ValueError: If config is invalid or missing required sections
        """
        if config_path is None:
            # Default to config/agents.yaml in project root
            project_root = Path(__file__).parent.parent.parent.parent
            config_path = str(project_root / "config" / "agents.yaml")

        config_file = Path(config_path)
        if not config_file.exists():
            msg = f"config file not found at path=<{config_path}>"
            logger.error(msg)
            raise FileNotFoundError(msg)

        logger.info("config_path=<%s> | loading meeting classifier configuration", config_path)

        with open(config_file) as f:
            full_config = yaml.safe_load(f)

        # Extract meeting coordinator config
        if "meeting_coordinator" not in full_config:
            msg = "missing meeting_coordinator section in config"
            logger.error("config_path=<%s> | %s", config_path, msg)
            raise ValueError(msg)

        self.config = full_config["meeting_coordinator"]

        # Validate required sections
        if "prep_timing" not in self.config:
            msg = "missing prep_timing section in meeting_coordinator config"
            logger.error("config_path=<%s> | %s", config_path, msg)
            raise ValueError(msg)

        if "meeting_type_detection" not in self.config:
            msg = "missing meeting_type_detection section in meeting_coordinator config"
            logger.error("config_path=<%s> | %s", config_path, msg)
            raise ValueError(msg)

        self.prep_timing = self.config["prep_timing"]
        self.detection_rules = self.config["meeting_type_detection"]

        logger.debug(
            "meeting_types=<%s> | loaded meeting classifier configuration",
            len(self.detection_rules),
        )

    def classify_meeting(self, meeting: Meeting) -> MeetingType:
        """Classify a meeting by type using keyword and attendee rules.

        Classification logic:
        1. Process meeting types in order defined in config
        2. For each type, check if keywords match (case-insensitive)
        3. Check if attendee count meets min/max constraints
        4. Return first matching type, or UNKNOWN if none match

        Args:
            meeting: Meeting object to classify

        Returns:
            MeetingType enum value for the classified type
        """
        title = meeting.title.lower() if meeting.title else ""
        attendee_count = len(meeting.attendees)

        logger.debug(
            "meeting_id=<%s>, title=<%s>, attendees=<%s> | classifying meeting",
            meeting.meeting_id,
            meeting.title,
            attendee_count,
        )

        # Handle empty title edge case
        if not title:
            logger.debug(
                "meeting_id=<%s> | empty title, returning unknown type",
                meeting.meeting_id,
            )
            return MeetingType.UNKNOWN

        # Process types in config order
        for type_name, rules in self.detection_rules.items():
            # Map config names to MeetingType enum values
            try:
                meeting_type = MeetingType(type_name)
            except ValueError:
                logger.warning(
                    "type_name=<%s> | invalid meeting type in config, skipping",
                    type_name,
                )
                continue

            # Check keyword match
            keywords = rules.get("keywords", [])
            keyword_match = any(keyword.lower() in title for keyword in keywords)

            if not keyword_match:
                continue

            # Check attendee count constraints
            min_attendees = rules.get("min_attendees")
            max_attendees = rules.get("max_attendees")

            # Validate min constraint
            if min_attendees is not None and attendee_count < min_attendees:
                logger.debug(
                    "meeting_id=<%s>, type=<%s>, attendees=<%s>, min=<%s> | attendee count below minimum",
                    meeting.meeting_id,
                    type_name,
                    attendee_count,
                    min_attendees,
                )
                continue

            # Validate max constraint
            if max_attendees is not None and attendee_count > max_attendees:
                logger.debug(
                    "meeting_id=<%s>, type=<%s>, attendees=<%s>, max=<%s> | attendee count above maximum",
                    meeting.meeting_id,
                    type_name,
                    attendee_count,
                    max_attendees,
                )
                continue

            # Both keyword and attendee count match
            logger.info(
                "meeting_id=<%s>, type=<%s>, attendees=<%s> | classified meeting",
                meeting.meeting_id,
                type_name,
                attendee_count,
            )
            return meeting_type

        # No match found
        logger.debug(
            "meeting_id=<%s>, title=<%s>, attendees=<%s> | no matching type found, returning unknown",
            meeting.meeting_id,
            meeting.title,
            attendee_count,
        )
        return MeetingType.UNKNOWN

    def get_prep_hours(self, meeting_type: MeetingType) -> int:
        """Get prep notification hours for a meeting type.

        Args:
            meeting_type: The meeting type enum value

        Returns:
            Number of hours before meeting to send prep notification

        Raises:
            ValueError: If meeting_type is not a valid MeetingType enum
        """
        if not isinstance(meeting_type, MeetingType):
            msg = f"meeting_type must be MeetingType enum, got {type(meeting_type)}"
            logger.error("meeting_type=<%s> | %s", meeting_type, msg)
            raise ValueError(msg)

        type_key = meeting_type.value
        prep_hours = self.prep_timing.get(type_key)

        if prep_hours is None:
            # Default to unknown type timing
            default_hours = self.prep_timing.get("unknown", 24)
            logger.warning(
                "meeting_type=<%s> | no prep timing configured, using default=<%s>",
                type_key,
                default_hours,
            )
            return default_hours

        logger.debug(
            "meeting_type=<%s>, prep_hours=<%s> | retrieved prep timing",
            type_key,
            prep_hours,
        )
        return prep_hours

    def should_trigger_prep(
        self,
        meeting: Meeting,
        current_time: datetime,
    ) -> bool:
        """Determine if prep should be triggered now.

        Prep is triggered if current_time is within the prep window, defined as:
        - After: meeting.start_time - prep_hours
        - Before: meeting.start_time

        Args:
            meeting: Meeting object with start_time and meeting_type
            current_time: Current time (timezone-aware)

        Returns:
            True if prep should be triggered, False otherwise
        """
        # Get prep hours for this meeting type
        prep_hours = self.get_prep_hours(meeting.meeting_type)

        # Calculate prep trigger time
        prep_trigger_time = meeting.start_time - timedelta(hours=prep_hours)

        # Check if current time is in prep window
        in_window = prep_trigger_time <= current_time < meeting.start_time

        logger.debug(
            "meeting_id=<%s>, meeting_type=<%s>, prep_hours=<%s>, start_time=<%s>, current_time=<%s>, trigger_time=<%s>, in_window=<%s> | checking prep trigger",
            meeting.meeting_id,
            meeting.meeting_type.value,
            prep_hours,
            meeting.start_time.isoformat(),
            current_time.isoformat(),
            prep_trigger_time.isoformat(),
            in_window,
        )

        return in_window
