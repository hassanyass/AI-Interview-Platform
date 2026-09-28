"""Verbal Background subsection, step 1: HR's per-section settings.

docs/verbal-background-subsection-plan.md §10/§11 -- the settings live in
InterviewSection.config next to time_budget_minutes and are validated by
the same SectionConfig the section endpoints already run every config
through. Pure schema tests; the live endpoint path is verified against the
running backend.
"""
import pytest

from backend.schemas.admin import (
    validate_section_config,
    default_verbal_section_config,
    BACKGROUND_QUESTION_COUNT_MAX,
)


def test_existing_timing_only_config_is_unchanged():
    assert validate_section_config({"time_budget_minutes": 20}) == {"time_budget_minutes": 20}
    assert validate_section_config(None) is None


def test_background_settings_round_trip_with_budget():
    cfg = {"time_budget_minutes": 20, "include_background": True,
           "background_question_count": 3, "background_time_budget_minutes": 5}
    assert validate_section_config(cfg) == cfg


def test_background_settings_allowed_before_time_budget_is_set():
    """A new VERBAL section is seeded before HR types a budget; publish is
    what still refuses an unbudgeted section."""
    seed = default_verbal_section_config()
    assert seed == {"include_background": True, "background_question_count": 3,
                    "background_time_budget_minutes": 5}
    assert validate_section_config(seed) == seed


def test_background_budget_must_fit_in_half_the_section_budget():
    with pytest.raises(ValueError, match="at most half"):
        validate_section_config({"time_budget_minutes": 8, "include_background": True,
                                 "background_time_budget_minutes": 5})
    # Exactly half is fine; and the rule only bites when background is ON.
    assert validate_section_config({"time_budget_minutes": 10, "include_background": True,
                                    "background_time_budget_minutes": 5})["background_time_budget_minutes"] == 5
    assert validate_section_config({"time_budget_minutes": 8, "include_background": False,
                                    "background_time_budget_minutes": 5})["include_background"] is False


@pytest.mark.parametrize("bad", [
    {"background_question_count": 0},
    {"background_question_count": BACKGROUND_QUESTION_COUNT_MAX + 1},
    {"background_time_budget_minutes": 0},
    {"time_budget_minutes": 0},
])
def test_out_of_range_values_are_rejected(bad):
    with pytest.raises(ValueError):
        validate_section_config(bad)
