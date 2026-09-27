from __future__ import annotations

import asyncio

from app.agents.lyrics_agent import LyricsAgent
from app.agents.request_agent import RequestAgent
from app.agents.transition_agent import TransitionAgent, TransitionIssue
from app.agents.vibe_agent import VibeAgent
from app.models.agent import AIResponse
from app.models.base import (
    AIMessageType,
    LockStatus,
    RequestDecisionType,
    RequestStatus,
    VibePreset,
    VibeVector,
)
from app.models.queue import QueueItem
from app.models.request import SongRequest


class CapturingAIClient:
    def __init__(self, response: AIResponse):
        self.response = response
        self.request = None

    async def decide(self, request):
        self.request = request
        return self.response


class PlayableRequestCatalog:
    def __init__(self, songs=None):
        self.songs = songs or {}
        self.song_repo = self

    def find_local_matches(self, query, limit=5):
        return []

    def get(self, song_id):
        return self.songs.get(song_id)

    def is_playable_local_track(self, song):
        return song is not None


def test_lyrics_agent_sends_supported_ai_request():
    response = AIResponse(
        request_id="lyrics-test",
        message_type=AIMessageType.LYRIC_ANALYSIS,
        lyrics_analysis={"language": "English", "family_friendly": True},
    )
    client = CapturingAIClient(response)
    features = asyncio.run(LyricsAgent(ai_client=client).analyze_lyrics("song-1", "sample lyrics"))

    assert client.request.message_type == AIMessageType.LYRIC_ANALYSIS
    assert client.request.lyrics_data == {"lyrics": "sample lyrics"}
    assert features.language == "English"


def test_vibe_fallback_preserves_manual_vibe(sample_event_state):
    sample_event_state.current_vibe = VibePreset.HYPE
    sample_event_state.vibe_vector = VibeVector.from_preset(VibePreset.HYPE)
    client = CapturingAIClient(
        AIResponse(
            request_id="vibe-test",
            message_type=AIMessageType.VIBE_UPDATE,
            success=False,
            error="model unavailable",
        )
    )

    recommendation = asyncio.run(VibeAgent(ai_client=client).evaluate_vibe(sample_event_state))

    assert recommendation.recommended_vibe == sample_event_state.vibe_vector


def test_transition_agent_sends_supported_ai_request():
    response = AIResponse(
        request_id="transition-test",
        message_type=AIMessageType.TRANSITION_REVIEW,
        queue_changes=[],
    )
    client = CapturingAIClient(response)
    queue = [
        QueueItem(song_id=f"song-{i}", position=i, lock_status=LockStatus.FLEXIBLE)
        for i in range(6)
    ]
    issue = TransitionIssue(
        index1=3,
        index2=4,
        issue_type="bpm_jump",
        severity=0.8,
        description="Large BPM jump",
    )

    changes = asyncio.run(TransitionAgent(ai_client=client).recommend_improvements(queue, [issue]))

    assert changes == []
    assert client.request.message_type == AIMessageType.TRANSITION_REVIEW
    assert len(client.request.queue_data) == 6


def test_request_agent_records_decision_lifecycle(sample_event_state):
    response = AIResponse(
        request_id="request-test",
        message_type=AIMessageType.REQUEST_DECISION,
        request_decision=RequestDecisionType.QUEUE.value,
        confidence=0.9,
    )
    client = CapturingAIClient(response)
    request = SongRequest(
        request_id="request-test",
        requested_song_query="Known song",
        matched_song_id="SNG_test001",
    )

    decision = asyncio.run(
        RequestAgent(
            ai_client=client,
            candidate_generator=PlayableRequestCatalog({"SNG_test001": object()}),
        ).evaluate_request(request, sample_event_state)
    )

    assert decision.decision == RequestDecisionType.QUEUE
    assert request.status == RequestStatus.QUEUED
    assert [item.to_status for item in request.status_history] == [
        RequestStatus.VALIDATING,
        RequestStatus.POLICY_CHECK,
        RequestStatus.ANALYZING,
        RequestStatus.DECISION,
        RequestStatus.QUEUED,
    ]


def test_request_agent_rejects_unmatched_song(monkeypatch, sample_event_state):
    client = CapturingAIClient(
        AIResponse(
            request_id="unmatched-request",
            message_type=AIMessageType.REQUEST_DECISION,
        )
    )
    request = SongRequest(
        request_id="unmatched-request",
        requested_song_query="Not in library",
    )

    decision = asyncio.run(
        RequestAgent(
            ai_client=client,
            candidate_generator=PlayableRequestCatalog(),
        ).evaluate_request(request, sample_event_state)
    )

    assert client.request is None
    assert decision.decision == RequestDecisionType.REJECT
    assert request.status == RequestStatus.REJECTED
    assert request.status_history[-1].to_status == RequestStatus.REJECTED
