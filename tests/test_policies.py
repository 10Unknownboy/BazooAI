"""Tests for the policy engine (spec §51)."""

from __future__ import annotations

import pytest

from app.models.base import VibePreset
from app.models.song import Song
from app.models.event import EventConfig, EventState
from app.policies.policy_engine import PolicyEngine


@pytest.fixture
def policy_engine():
    return PolicyEngine()


def test_allowed_song_passes(policy_engine, sample_song, sample_event_state):
    """A policy-compatible song should pass all checks."""
    result = policy_engine.check_song(sample_song, sample_event_state)
    assert result.passed
    assert len(result.violations) == 0


def test_song_in_allowed_language_passes(policy_engine, sample_song, sample_event_state):
    """Song in an allowed language should pass."""
    sample_song.language = "Hindi"
    result = policy_engine.check_song(sample_song, sample_event_state)
    assert result.passed


def test_policy_result_has_violations_list(policy_engine, sample_song, sample_event_state):
    """Policy result should contain a violations list."""
    result = policy_engine.check_song(sample_song, sample_event_state)
    assert hasattr(result, "violations")
    assert isinstance(result.violations, list)


def test_policy_result_structure(policy_engine, sample_song, sample_event_state):
    """Policy result should have passed field and violations list."""
    result = policy_engine.check_song(sample_song, sample_event_state)
    assert hasattr(result, "passed")
    assert hasattr(result, "violations")
