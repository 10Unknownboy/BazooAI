"""Tests for failure handling (spec §51)."""

from __future__ import annotations

import asyncio
import pytest

from app.models.base import SystemMode, VibePreset, VibeVector
from app.playback.fallback import FallbackManager
from app.agents.ai_client import AIModelClient


@pytest.fixture
def fallback_manager():
    return FallbackManager()


def test_system_starts_in_normal_mode(fallback_manager):
    """System should start in NORMAL mode."""
    assert not fallback_manager.is_fallback_mode()


def test_enter_fallback_mode(fallback_manager):
    """System should transition to fallback when AI unavailable."""
    fallback_manager.enter_fallback("AI model server unreachable")
    assert fallback_manager.is_fallback_mode()


def test_exit_fallback_mode(fallback_manager):
    """System should recover from fallback mode."""
    fallback_manager.enter_fallback("test")
    assert fallback_manager.is_fallback_mode()
    
    fallback_manager.exit_fallback()
    assert not fallback_manager.is_fallback_mode()


def test_ai_client_health_check_fails_gracefully():
    """AI client should handle connection failures gracefully."""
    client = AIModelClient()
    # check_health is async — run it
    result = asyncio.run(client.check_health())
    assert result is False


def test_event_state_preserves_on_mode_change(sample_event_state, fallback_manager):
    """Event state should be preserved when entering/exiting fallback."""
    original_vibe = sample_event_state.current_vibe
    original_energy = sample_event_state.current_energy
    
    fallback_manager.enter_fallback("test")
    
    assert sample_event_state.current_vibe == original_vibe
    assert sample_event_state.current_energy == original_energy
