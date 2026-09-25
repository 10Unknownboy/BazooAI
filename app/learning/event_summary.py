"""Event-end learning summary generation (spec §35-36)."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from app.models.feedback import EventLearningReport, PatternRecord

logger = logging.getLogger(__name__)


class EventSummaryGenerator:
    """Generates an end-of-event learning summary."""

    def __init__(self, long_term_store=None, feedback_repo=None, play_history_repo=None):
        self.store = long_term_store
        self.feedback_repo = feedback_repo
        self.play_history_repo = play_history_repo

    def generate_summary(self, event_id: str, event_type: str | None = None) -> EventLearningReport:
        """Generate a machine-readable summary of the event for future learning."""
        logger.info(f"Generating learning summary for event {event_id}")

        successful_songs: list[str] = []
        poor_songs: list[str] = []
        genre_feedback: dict[str, list[float]] = defaultdict(list)
        transition_feedback: dict[str, list[float]] = defaultdict(list)
        songs_played = 0
        total_requests = 0

        # Aggregate song-level feedback
        if self.feedback_repo:
            try:
                feedbacks = self.feedback_repo.get_song_historical_feedback_for_event(event_id)
            except (AttributeError, Exception):
                # Fallback: use generic method if specific one not available
                feedbacks = []

            for fb in feedbacks:
                rating = fb.get("overall_rating")
                song_id = fb.get("song_id", "")
                if rating and rating >= 8:
                    successful_songs.append(song_id)
                elif rating and rating <= 4:
                    poor_songs.append(song_id)

        # Aggregate play history for pattern detection
        if self.play_history_repo:
            try:
                history = self.play_history_repo.get_event_history(event_id)
                songs_played = len(history)

                # Detect genre transition patterns
                for i in range(len(history) - 1):
                    from_genre = (history[i].get("vibe_at_selection") or {}).get("genre", "Unknown")
                    to_genre = (history[i + 1].get("vibe_at_selection") or {}).get("genre", "Unknown")
                    pattern_key = f"{from_genre} → {to_genre}"
                    fb_rating = history[i + 1].get("feedback_rating")
                    if fb_rating:
                        transition_feedback[pattern_key].append(float(fb_rating))
            except Exception as e:
                logger.warning(f"Could not aggregate play history: {e}")

        # Build pattern records
        successful_patterns: list[PatternRecord] = []
        weak_patterns: list[PatternRecord] = []

        for pattern, ratings in transition_feedback.items():
            avg = sum(ratings) / len(ratings) if ratings else 0.0
            record = PatternRecord(
                pattern=pattern,
                average_feedback=avg,
                sample_count=len(ratings),
            )
            if avg >= 7.0:
                successful_patterns.append(record)
            elif avg <= 4.0:
                weak_patterns.append(record)

        # Sort by feedback
        successful_patterns.sort(key=lambda p: p.average_feedback, reverse=True)
        weak_patterns.sort(key=lambda p: p.average_feedback)

        report = EventLearningReport(
            event_id=event_id,
            event_type=event_type,
            songs_played=songs_played,
            total_requests=total_requests,
            request_success_rate=0.0,
            successful_patterns=successful_patterns,
            weak_patterns=weak_patterns,
            successful_songs=successful_songs,
            poorly_performing_songs=poor_songs,
            crowd_preferences={},
        )

        # Save to long-term store if available
        if self.store:
            try:
                self.store.save_event_summary(event_id, report.model_dump())
            except Exception as e:
                logger.warning(f"Could not save event summary: {e}")

        logger.info(
            f"Event summary: {songs_played} songs, "
            f"{len(successful_songs)} successful, {len(poor_songs)} poor, "
            f"{len(successful_patterns)} good patterns, {len(weak_patterns)} weak patterns"
        )

        return report
