"""Comprehensive tests for MeetingClassifier.

This module provides extensive test coverage for:
- Initialization with config loading
- Meeting classification by type
- Prep timing retrieval
- Prep trigger logic
- Edge cases and error handling
"""

from datetime import UTC, datetime, timedelta

import pytest
import yaml

from exec_assistant.shared.meeting_classifier import MeetingClassifier
from exec_assistant.shared.models import Meeting, MeetingType


class TestMeetingClassifierInitialization:
    """Test suite for MeetingClassifier initialization."""

    def test_init_with_default_config_path(self):
        """Test loading config from default path."""
        classifier = MeetingClassifier()

        assert classifier is not None
        assert classifier.config is not None
        assert classifier.prep_timing is not None
        assert classifier.detection_rules is not None

        # Verify all meeting types are configured
        assert "leadership_team" in classifier.prep_timing
        assert "one_on_one" in classifier.prep_timing
        assert "qbr" in classifier.prep_timing
        assert "reliability_review" in classifier.prep_timing
        assert "executive_staff" in classifier.prep_timing
        assert "interview_debrief" in classifier.prep_timing
        assert "vendor_meeting" in classifier.prep_timing
        assert "unknown" in classifier.prep_timing

    def test_init_with_custom_config_path(self, tmp_path):
        """Test loading config from custom path."""
        # Create temporary config file
        config_data = {
            "meeting_coordinator": {
                "prep_timing": {
                    "leadership_team": 24,
                    "unknown": 12,
                },
                "meeting_type_detection": {
                    "leadership_team": {
                        "keywords": ["leadership team"],
                        "min_attendees": 5,
                    },
                },
            },
        }

        config_file = tmp_path / "custom_agents.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        classifier = MeetingClassifier(config_path=str(config_file))

        assert classifier is not None
        assert classifier.prep_timing["leadership_team"] == 24
        assert classifier.prep_timing["unknown"] == 12

    def test_init_missing_config_file(self):
        """Test handling of missing config file."""
        with pytest.raises(FileNotFoundError) as exc_info:
            MeetingClassifier(config_path="/nonexistent/path/agents.yaml")

        assert "config file not found" in str(exc_info.value)

    def test_init_missing_meeting_coordinator_section(self, tmp_path):
        """Test handling of missing meeting_coordinator section."""
        config_data = {"other_section": {}}

        config_file = tmp_path / "invalid_agents.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        with pytest.raises(ValueError) as exc_info:
            MeetingClassifier(config_path=str(config_file))

        assert "missing meeting_coordinator section" in str(exc_info.value)

    def test_init_missing_prep_timing_section(self, tmp_path):
        """Test handling of missing prep_timing section."""
        config_data = {
            "meeting_coordinator": {
                "meeting_type_detection": {},
            },
        }

        config_file = tmp_path / "invalid_agents.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        with pytest.raises(ValueError) as exc_info:
            MeetingClassifier(config_path=str(config_file))

        assert "missing prep_timing section" in str(exc_info.value)

    def test_init_missing_detection_section(self, tmp_path):
        """Test handling of missing meeting_type_detection section."""
        config_data = {
            "meeting_coordinator": {
                "prep_timing": {"unknown": 24},
            },
        }

        config_file = tmp_path / "invalid_agents.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        with pytest.raises(ValueError) as exc_info:
            MeetingClassifier(config_path=str(config_file))

        assert "missing meeting_type_detection section" in str(exc_info.value)


class TestMeetingClassification:
    """Test suite for meeting classification logic."""

    @pytest.fixture
    def classifier(self):
        """Create classifier instance for testing."""
        return MeetingClassifier()

    @pytest.fixture
    def base_meeting(self, test_user_id):
        """Create base meeting for testing."""
        return Meeting(
            meeting_id="test-meeting-1",
            user_id=test_user_id,
            title="Test Meeting",
            start_time=datetime.now(UTC) + timedelta(days=1),
            end_time=datetime.now(UTC) + timedelta(days=1, hours=1),
            attendees=["user@example.com"],
        )

    def test_classify_leadership_team_meeting(self, classifier, base_meeting):
        """Test classifying leadership team meeting with keywords and attendees."""
        base_meeting.title = "Leadership Team Sync"
        base_meeting.attendees = [f"user{i}@example.com" for i in range(8)]

        result = classifier.classify_meeting(base_meeting)

        assert result == MeetingType.LEADERSHIP_TEAM

    def test_classify_leadership_team_multiple_keywords(self, classifier, base_meeting):
        """Test leadership team classification with different keyword variations."""
        test_cases = [
            "Leadership Team Meeting",
            "LT Meeting for Q4",
            "Senior Leadership Sync",
            "LEADERSHIP SYNC",  # Test case insensitivity
        ]

        for title in test_cases:
            base_meeting.title = title
            base_meeting.attendees = [f"user{i}@example.com" for i in range(8)]

            result = classifier.classify_meeting(base_meeting)

            assert result == MeetingType.LEADERSHIP_TEAM, f"Failed for title: {title}"

    def test_classify_one_on_one_meeting(self, classifier, base_meeting):
        """Test classifying one-on-one meeting with exact 2 attendees."""
        base_meeting.title = "1-1 with Manager"
        base_meeting.attendees = ["user1@example.com", "user2@example.com"]

        result = classifier.classify_meeting(base_meeting)

        assert result == MeetingType.ONE_ON_ONE

    def test_classify_one_on_one_keyword_variations(self, classifier, base_meeting):
        """Test one-on-one classification with different keyword variations."""
        test_cases = [
            "1-1 catch up",
            "1:1 weekly",
            "One on One meeting",
            "1 on 1 sync",
            "Catch up",
        ]

        for title in test_cases:
            base_meeting.title = title
            base_meeting.attendees = ["user1@example.com", "user2@example.com"]

            result = classifier.classify_meeting(base_meeting)

            assert result == MeetingType.ONE_ON_ONE, f"Failed for title: {title}"

    def test_classify_qbr_meeting(self, classifier, base_meeting):
        """Test classifying quarterly business review."""
        base_meeting.title = "Q4 QBR 2024"
        base_meeting.attendees = [f"user{i}@example.com" for i in range(10)]

        result = classifier.classify_meeting(base_meeting)

        assert result == MeetingType.QUARTERLY_BUSINESS_REVIEW

    def test_classify_qbr_keyword_variations(self, classifier, base_meeting):
        """Test QBR classification with different keyword variations."""
        test_cases = [
            "QBR - Quarterly Business Review",
            "Q1 Review 2025",
            "Q2 review session",
            "Quarterly Review Meeting",
        ]

        for title in test_cases:
            base_meeting.title = title
            base_meeting.attendees = [f"user{i}@example.com" for i in range(8)]

            result = classifier.classify_meeting(base_meeting)

            assert result == MeetingType.QUARTERLY_BUSINESS_REVIEW, f"Failed for title: {title}"

    def test_classify_reliability_review(self, classifier, base_meeting):
        """Test classifying reliability review meeting."""
        base_meeting.title = "Post-mortem for SEV1 incident"
        base_meeting.attendees = [f"user{i}@example.com" for i in range(5)]

        result = classifier.classify_meeting(base_meeting)

        assert result == MeetingType.RELIABILITY_REVIEW

    def test_classify_reliability_review_keywords(self, classifier, base_meeting):
        """Test reliability review classification with keyword variations."""
        test_cases = [
            "Reliability Meeting",
            "Postmortem Review",
            "Incident Review",
            "RCA for outage",
            "Root Cause Analysis",
        ]

        for title in test_cases:
            base_meeting.title = title
            base_meeting.attendees = [f"user{i}@example.com" for i in range(4)]

            result = classifier.classify_meeting(base_meeting)

            assert result == MeetingType.RELIABILITY_REVIEW, f"Failed for title: {title}"

    def test_classify_executive_staff_meeting(self, classifier, base_meeting):
        """Test classifying executive staff meeting."""
        base_meeting.title = "Executive Staff Meeting"
        base_meeting.attendees = [f"exec{i}@example.com" for i in range(8)]

        result = classifier.classify_meeting(base_meeting)

        assert result == MeetingType.EXECUTIVE_STAFF

    def test_classify_interview_debrief(self, classifier, base_meeting):
        """Test classifying interview debrief meeting."""
        base_meeting.title = "Interview Debrief - John Doe"
        base_meeting.attendees = [f"interviewer{i}@example.com" for i in range(4)]

        result = classifier.classify_meeting(base_meeting)

        assert result == MeetingType.INTERVIEW_DEBRIEF

    def test_classify_vendor_meeting(self, classifier, base_meeting):
        """Test classifying vendor meeting."""
        base_meeting.title = "Vendor Review with AWS"
        base_meeting.attendees = [f"user{i}@example.com" for i in range(3)]

        result = classifier.classify_meeting(base_meeting)

        assert result == MeetingType.VENDOR_MEETING

    def test_classify_unknown_no_keyword_match(self, classifier, base_meeting):
        """Test unknown classification when no keywords match."""
        base_meeting.title = "Random Team Sync"
        base_meeting.attendees = [f"user{i}@example.com" for i in range(5)]

        result = classifier.classify_meeting(base_meeting)

        assert result == MeetingType.UNKNOWN

    def test_classify_keyword_match_attendee_count_too_low(self, classifier, base_meeting):
        """Test unknown when keyword matches but attendee count below minimum."""
        base_meeting.title = "Leadership Team Meeting"
        base_meeting.attendees = ["user1@example.com", "user2@example.com"]  # Only 2, need 5+

        result = classifier.classify_meeting(base_meeting)

        assert result == MeetingType.UNKNOWN

    def test_classify_keyword_match_attendee_count_too_high(self, classifier, base_meeting):
        """Test unknown when keyword matches but attendee count above maximum."""
        base_meeting.title = "1-1 meeting"
        base_meeting.attendees = [
            f"user{i}@example.com" for i in range(5)
        ]  # 5 attendees, need exactly 2

        result = classifier.classify_meeting(base_meeting)

        assert result == MeetingType.UNKNOWN

    def test_classify_case_insensitive_matching(self, classifier, base_meeting):
        """Test case-insensitive keyword matching."""
        base_meeting.title = "LEADERSHIP TEAM MEETING"
        base_meeting.attendees = [f"user{i}@example.com" for i in range(8)]

        result = classifier.classify_meeting(base_meeting)

        assert result == MeetingType.LEADERSHIP_TEAM

    def test_classify_partial_keyword_matching(self, classifier, base_meeting):
        """Test partial keyword matching (keyword as substring)."""
        base_meeting.title = "Weekly leadership team sync and planning"
        base_meeting.attendees = [f"user{i}@example.com" for i in range(8)]

        result = classifier.classify_meeting(base_meeting)

        assert result == MeetingType.LEADERSHIP_TEAM

    def test_classify_empty_title(self, classifier, base_meeting):
        """Test classification with empty title."""
        base_meeting.title = ""
        base_meeting.attendees = [f"user{i}@example.com" for i in range(5)]

        result = classifier.classify_meeting(base_meeting)

        assert result == MeetingType.UNKNOWN

    def test_classify_zero_attendees(self, classifier, base_meeting):
        """Test classification with zero attendees."""
        base_meeting.title = "Leadership Team Meeting"
        base_meeting.attendees = []

        result = classifier.classify_meeting(base_meeting)

        assert result == MeetingType.UNKNOWN

    def test_classify_first_match_wins(self, classifier, base_meeting):
        """Test that first matching type is returned (config order matters)."""
        # Title could match multiple types, but first match wins
        base_meeting.title = "1-1 Interview Debrief"
        base_meeting.attendees = ["user1@example.com", "user2@example.com"]

        result = classifier.classify_meeting(base_meeting)

        # Should match one_on_one (appears before interview_debrief in config)
        assert result == MeetingType.ONE_ON_ONE


class TestPrepTiming:
    """Test suite for prep timing retrieval."""

    @pytest.fixture
    def classifier(self):
        """Create classifier instance for testing."""
        return MeetingClassifier()

    def test_get_prep_hours_leadership_team(self, classifier):
        """Test prep hours for leadership team meeting."""
        hours = classifier.get_prep_hours(MeetingType.LEADERSHIP_TEAM)
        assert hours == 24

    def test_get_prep_hours_one_on_one(self, classifier):
        """Test prep hours for one-on-one meeting."""
        hours = classifier.get_prep_hours(MeetingType.ONE_ON_ONE)
        assert hours == 12

    def test_get_prep_hours_reliability_review(self, classifier):
        """Test prep hours for reliability review."""
        hours = classifier.get_prep_hours(MeetingType.RELIABILITY_REVIEW)
        assert hours == 48

    def test_get_prep_hours_qbr(self, classifier):
        """Test prep hours for QBR."""
        hours = classifier.get_prep_hours(MeetingType.QUARTERLY_BUSINESS_REVIEW)
        assert hours == 72

    def test_get_prep_hours_executive_staff(self, classifier):
        """Test prep hours for executive staff meeting."""
        hours = classifier.get_prep_hours(MeetingType.EXECUTIVE_STAFF)
        assert hours == 48

    def test_get_prep_hours_interview_debrief(self, classifier):
        """Test prep hours for interview debrief."""
        hours = classifier.get_prep_hours(MeetingType.INTERVIEW_DEBRIEF)
        assert hours == 4

    def test_get_prep_hours_vendor_meeting(self, classifier):
        """Test prep hours for vendor meeting."""
        hours = classifier.get_prep_hours(MeetingType.VENDOR_MEETING)
        assert hours == 24

    def test_get_prep_hours_unknown_type(self, classifier):
        """Test default prep hours for unknown type."""
        hours = classifier.get_prep_hours(MeetingType.UNKNOWN)
        assert hours == 24

    def test_get_prep_hours_invalid_type(self, classifier):
        """Test error handling for invalid meeting type."""
        with pytest.raises(ValueError) as exc_info:
            classifier.get_prep_hours("not_a_meeting_type")

        assert "must be MeetingType enum" in str(exc_info.value)


class TestPrepTriggerLogic:
    """Test suite for prep trigger determination."""

    @pytest.fixture
    def classifier(self):
        """Create classifier instance for testing."""
        return MeetingClassifier()

    @pytest.fixture
    def sample_meeting(self, test_user_id):
        """Create sample meeting for testing."""
        start_time = datetime(2025, 1, 15, 14, 0, tzinfo=UTC)
        return Meeting(
            meeting_id="test-meeting-trigger",
            user_id=test_user_id,
            title="Test Meeting",
            start_time=start_time,
            end_time=start_time + timedelta(hours=1),
            attendees=["user@example.com"],
            meeting_type=MeetingType.LEADERSHIP_TEAM,  # 24 hour prep window
        )

    def test_should_trigger_within_window(self, classifier, sample_meeting):
        """Test trigger returns True when within prep window."""
        # Meeting at Jan 15 14:00, prep window starts at Jan 14 14:00 (24h before)
        current_time = datetime(2025, 1, 14, 20, 0, tzinfo=UTC)  # 18h before meeting

        result = classifier.should_trigger_prep(sample_meeting, current_time)

        assert result is True

    def test_should_trigger_too_early(self, classifier, sample_meeting):
        """Test trigger returns False when too early (before window)."""
        # Meeting at Jan 15 14:00, prep window starts at Jan 14 14:00
        current_time = datetime(2025, 1, 14, 10, 0, tzinfo=UTC)  # 4h before window

        result = classifier.should_trigger_prep(sample_meeting, current_time)

        assert result is False

    def test_should_trigger_too_late(self, classifier, sample_meeting):
        """Test trigger returns False when meeting already started."""
        # Meeting at Jan 15 14:00
        current_time = datetime(2025, 1, 15, 15, 0, tzinfo=UTC)  # 1h after start

        result = classifier.should_trigger_prep(sample_meeting, current_time)

        assert result is False

    def test_should_trigger_exact_boundary_start(self, classifier, sample_meeting):
        """Test trigger at exact start of prep window."""
        # Meeting at Jan 15 14:00, prep window starts at Jan 14 14:00
        current_time = datetime(2025, 1, 14, 14, 0, tzinfo=UTC)  # Exactly at window start

        result = classifier.should_trigger_prep(sample_meeting, current_time)

        assert result is True

    def test_should_trigger_exact_boundary_end(self, classifier, sample_meeting):
        """Test trigger at exact end of prep window (meeting start time)."""
        # Meeting at Jan 15 14:00
        current_time = datetime(2025, 1, 15, 14, 0, tzinfo=UTC)  # Exactly at meeting start

        result = classifier.should_trigger_prep(sample_meeting, current_time)

        # Should be False (window is [trigger_time, start_time) - excludes end)
        assert result is False

    def test_should_trigger_one_on_one_shorter_window(self, classifier, sample_meeting):
        """Test trigger with shorter prep window (one-on-one = 12h)."""
        sample_meeting.meeting_type = MeetingType.ONE_ON_ONE
        # Meeting at Jan 15 14:00, prep window starts at Jan 15 02:00 (12h before)

        # Within window
        current_time = datetime(2025, 1, 15, 10, 0, tzinfo=UTC)
        assert classifier.should_trigger_prep(sample_meeting, current_time) is True

        # Before window
        current_time = datetime(2025, 1, 15, 1, 0, tzinfo=UTC)
        assert classifier.should_trigger_prep(sample_meeting, current_time) is False

    def test_should_trigger_qbr_longer_window(self, classifier, sample_meeting):
        """Test trigger with longer prep window (QBR = 72h)."""
        sample_meeting.meeting_type = MeetingType.QUARTERLY_BUSINESS_REVIEW
        # Meeting at Jan 15 14:00, prep window starts at Jan 12 14:00 (72h before)

        # Within window
        current_time = datetime(2025, 1, 13, 14, 0, tzinfo=UTC)
        assert classifier.should_trigger_prep(sample_meeting, current_time) is True

        # Before window
        current_time = datetime(2025, 1, 12, 10, 0, tzinfo=UTC)
        assert classifier.should_trigger_prep(sample_meeting, current_time) is False

    def test_should_trigger_meeting_in_past(self, classifier, sample_meeting):
        """Test trigger for meeting already in the past."""
        # Meeting was yesterday
        sample_meeting.start_time = datetime(2025, 1, 13, 14, 0, tzinfo=UTC)
        sample_meeting.end_time = datetime(2025, 1, 13, 15, 0, tzinfo=UTC)

        current_time = datetime(2025, 1, 15, 14, 0, tzinfo=UTC)

        result = classifier.should_trigger_prep(sample_meeting, current_time)

        assert result is False

    def test_should_trigger_meeting_far_future(self, classifier, sample_meeting):
        """Test trigger for meeting very far in future."""
        # Meeting is 30 days from now
        sample_meeting.start_time = datetime(2025, 2, 14, 14, 0, tzinfo=UTC)
        sample_meeting.end_time = datetime(2025, 2, 14, 15, 0, tzinfo=UTC)

        current_time = datetime(2025, 1, 15, 14, 0, tzinfo=UTC)

        result = classifier.should_trigger_prep(sample_meeting, current_time)

        assert result is False


class TestIntegrationWorkflows:
    """Integration tests for complete classification workflows."""

    @pytest.fixture
    def classifier(self):
        """Create classifier instance for testing."""
        return MeetingClassifier()

    def test_full_workflow_classify_get_hours_check_trigger(self, classifier, test_user_id):
        """Test complete workflow: classify -> get hours -> check trigger."""
        # Create meeting
        start_time = datetime.now(UTC) + timedelta(hours=20)
        meeting = Meeting(
            meeting_id="workflow-test-1",
            user_id=test_user_id,
            title="Leadership Team Q4 Planning",
            start_time=start_time,
            end_time=start_time + timedelta(hours=1),
            attendees=[f"leader{i}@example.com" for i in range(8)],
        )

        # Step 1: Classify
        meeting_type = classifier.classify_meeting(meeting)
        assert meeting_type == MeetingType.LEADERSHIP_TEAM

        # Step 2: Get prep hours
        prep_hours = classifier.get_prep_hours(meeting_type)
        assert prep_hours == 24

        # Step 3: Update meeting with classification
        meeting.meeting_type = meeting_type

        # Step 4: Check if should trigger (20h until meeting, 24h window = should trigger)
        current_time = datetime.now(UTC)
        should_trigger = classifier.should_trigger_prep(meeting, current_time)
        assert should_trigger is True

    def test_batch_classification_multiple_meetings(self, classifier, test_user_id):
        """Test classifying multiple meetings in batch."""
        now = datetime.now(UTC)

        meetings = [
            Meeting(
                meeting_id="batch-1",
                user_id=test_user_id,
                title="1-1 with Alice",
                start_time=now + timedelta(hours=8),
                end_time=now + timedelta(hours=9),
                attendees=["alice@example.com", "bob@example.com"],
            ),
            Meeting(
                meeting_id="batch-2",
                user_id=test_user_id,
                title="Executive Staff Meeting",
                start_time=now + timedelta(hours=50),
                end_time=now + timedelta(hours=51),
                attendees=[f"exec{i}@example.com" for i in range(10)],
            ),
            Meeting(
                meeting_id="batch-3",
                user_id=test_user_id,
                title="Random Team Sync",
                start_time=now + timedelta(hours=3),
                end_time=now + timedelta(hours=4),
                attendees=[f"user{i}@example.com" for i in range(5)],
            ),
        ]

        # Classify all meetings
        results = [classifier.classify_meeting(m) for m in meetings]

        assert results[0] == MeetingType.ONE_ON_ONE
        assert results[1] == MeetingType.EXECUTIVE_STAFF
        assert results[2] == MeetingType.UNKNOWN

        # Check which need prep now
        for meeting, meeting_type in zip(meetings, results, strict=True):
            meeting.meeting_type = meeting_type

        triggers = [classifier.should_trigger_prep(m, now) for m in meetings]

        # 1-1 in 8h with 12h window = should trigger (8 < 12)
        assert triggers[0] is True
        # Exec staff in 50h with 48h window = no trigger yet (50 > 48)
        assert triggers[1] is False
        # Unknown in 3h with 24h window = should trigger (3 < 24)
        assert triggers[2] is True

    def test_timezone_aware_trigger_checking(self, classifier, test_user_id):
        """Test trigger checking with different timezones."""
        # Create meeting in UTC
        start_time = datetime(2025, 1, 15, 14, 0, tzinfo=UTC)
        meeting = Meeting(
            meeting_id="tz-test-1",
            user_id=test_user_id,
            title="Leadership Team Meeting",
            start_time=start_time,
            end_time=start_time + timedelta(hours=1),
            attendees=[f"user{i}@example.com" for i in range(8)],
            meeting_type=MeetingType.LEADERSHIP_TEAM,
        )

        # Check trigger from different times (all UTC)
        current_time_1 = datetime(2025, 1, 14, 14, 0, tzinfo=UTC)  # Exactly 24h before
        current_time_2 = datetime(2025, 1, 14, 20, 0, tzinfo=UTC)  # 18h before
        current_time_3 = datetime(2025, 1, 13, 14, 0, tzinfo=UTC)  # 48h before

        assert classifier.should_trigger_prep(meeting, current_time_1) is True
        assert classifier.should_trigger_prep(meeting, current_time_2) is True
        assert classifier.should_trigger_prep(meeting, current_time_3) is False

    def test_real_world_meeting_scenarios(self, classifier, test_user_id):
        """Test realistic meeting scenarios."""
        now = datetime.now(UTC)

        scenarios = [
            {
                "title": "Weekly 1:1 - Sarah",
                "attendees": 2,
                "expected_type": MeetingType.ONE_ON_ONE,
                "hours_away": 10,
                "should_trigger": True,  # 10h away, 12h window
            },
            {
                "title": "Post-mortem: API outage",
                "attendees": 6,
                "expected_type": MeetingType.RELIABILITY_REVIEW,
                "hours_away": 40,
                "should_trigger": True,  # 40h away, 48h window
            },
            {
                "title": "Q1 2025 Quarterly Business Review",
                "attendees": 15,
                "expected_type": MeetingType.QUARTERLY_BUSINESS_REVIEW,
                "hours_away": 60,
                "should_trigger": True,  # 60h away, 72h window
            },
            {
                "title": "Interview Debrief - Jane Doe (Senior SRE)",
                "attendees": 4,
                "expected_type": MeetingType.INTERVIEW_DEBRIEF,
                "hours_away": 2,
                "should_trigger": True,  # 2h away, 4h window
            },
        ]

        for scenario in scenarios:
            start_time = now + timedelta(hours=scenario["hours_away"])
            meeting = Meeting(
                meeting_id=f"scenario-{scenario['title'][:10]}",
                user_id=test_user_id,
                title=scenario["title"],
                start_time=start_time,
                end_time=start_time + timedelta(hours=1),
                attendees=[f"user{i}@example.com" for i in range(scenario["attendees"])],
            )

            # Classify
            meeting_type = classifier.classify_meeting(meeting)
            assert meeting_type == scenario["expected_type"], (
                f"Classification failed for: {scenario['title']}"
            )

            # Check trigger
            meeting.meeting_type = meeting_type
            should_trigger = classifier.should_trigger_prep(meeting, now)
            assert should_trigger == scenario["should_trigger"], (
                f"Trigger check failed for: {scenario['title']}"
            )
