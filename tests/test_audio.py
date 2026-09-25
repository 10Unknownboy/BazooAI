"""Tests for audio analysis (spec §51)."""

from __future__ import annotations

import pytest

from app.models.song import AudioFeatures
from app.models.base import AnalysisStatus


def test_audio_features_model():
    """AudioFeatures should be a valid Pydantic model."""
    features = AudioFeatures(
        song_id="SNG_test",
        bpm=120.0,
        energy=0.8,
        danceability=0.7,
        valence=0.6,
        analysis_status=AnalysisStatus.COMPLETE,
    )
    assert features.song_id == "SNG_test"
    assert features.bpm == 120.0
    assert features.analysis_status == AnalysisStatus.COMPLETE


def test_audio_features_defaults():
    """AudioFeatures should have sensible defaults."""
    features = AudioFeatures(song_id="SNG_test2")
    assert features.analysis_status == AnalysisStatus.PENDING
    assert features.analysis_version == 1
    assert features.file_hash is None


def test_audio_features_embedding():
    """AudioFeatures should support embedding storage."""
    features = AudioFeatures(
        song_id="SNG_test3",
        audio_embedding=[0.1, 0.2, 0.3, 0.4],
    )
    assert features.audio_embedding is not None
    assert len(features.audio_embedding) == 4
