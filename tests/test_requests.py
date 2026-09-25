"""Tests for the request system (spec §51)."""

from __future__ import annotations

import pytest

from app.models.base import RequestStatus, RequestDecisionType, VibeVector, VibePreset
from app.models.request import SongRequest


def test_request_lifecycle_tracked():
    """All request status transitions should be recorded."""
    request = SongRequest(
        requested_song_query="Brown Munde",
        requester="test_user",
    )
    assert request.status == RequestStatus.RECEIVED
    
    request.transition_to(RequestStatus.VALIDATING, reason="Starting validation")
    assert request.status == RequestStatus.VALIDATING
    assert len(request.status_history) == 1
    
    request.transition_to(RequestStatus.POLICY_CHECK, reason="Checking policy")
    assert request.status == RequestStatus.POLICY_CHECK
    assert len(request.status_history) == 2


def test_request_status_history():
    """Status history should contain from_status and to_status."""
    request = SongRequest(requested_song_query="Test Song")
    
    request.transition_to(RequestStatus.VALIDATING, reason="test")
    
    transition = request.status_history[0]
    assert transition.from_status == RequestStatus.RECEIVED
    assert transition.to_status == RequestStatus.VALIDATING


def test_request_initial_state():
    """New request should start with RECEIVED status."""
    request = SongRequest(
        requested_song_query="Kala Chashma",
        requester="DJ Guest",
    )
    assert request.status == RequestStatus.RECEIVED
    assert request.decision is None
    assert len(request.status_history) == 0


def test_deferred_request_preserved():
    """Deferred request should maintain all its data."""
    request = SongRequest(
        requested_song_query="Romantic Song",
        current_vibe=VibeVector.from_preset(VibePreset.PARTY),
    )
    
    request.transition_to(RequestStatus.DECISION, reason="Analyzed")
    request.decision = RequestDecisionType.DEFER
    request.decision_reason = "Vibe mismatch - will play after transition"
    
    assert request.decision == RequestDecisionType.DEFER
    assert request.decision_reason != ""
    assert request.current_vibe is not None
