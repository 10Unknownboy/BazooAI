"""
Repository layer — provides a clean interface between the app and the database.
No raw SQL in application code. All queries go through repositories.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update, delete, func, and_
from sqlalchemy.orm import Session

from app.database.engine import (
    get_session,
    SongTable,
    AudioFeaturesTable,
    LyricsFeaturesTable,
    EventTable,
    PlayHistoryTable,
    RequestTable,
    FeedbackTable,
    TransitionFeedbackTable,
    EventFeedbackTable,
    AgentDecisionTable,
    ScoringSnapshotTable,
    RewardTable,
    LearnedPreferenceTable,
    APICacheTable,
)
from app.models.song import Song, AudioFeatures, LyricsFeatures
from app.models.event import EventConfig, EventState
from app.models.feedback import SongFeedback, TransitionFeedback, EventFeedback, RewardRecord
from app.models.agent import AgentDecision, ScoringSnapshot
from app.models.cache import CacheEntry


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Repository factory
# ---------------------------------------------------------------------------
_REPO_MAP: dict[str, type] = {}  # populated after class definitions


def get_repository(name: str, session: Session | None = None):
    """
    Factory to get a repository by name.

    Supported names: 'song', 'audio_features', 'lyrics_features', 'event',
    'play_history', 'feedback', 'agent_decision', 'reward',
    'learned_preference', 'cache', 'request'.
    """
    if not _REPO_MAP:
        # Lazy initialization to avoid circular import issues
        _REPO_MAP.update({
            "song": SongRepository,
            "audio_features": AudioFeaturesRepository,
            "lyrics_features": LyricsFeaturesRepository,
            "event": EventRepository,
            "play_history": PlayHistoryRepository,
            "feedback": FeedbackRepository,
            "agent_decision": AgentDecisionRepository,
            "reward": RewardRepository,
            "learned_preference": LearnedPreferenceRepository,
            "cache": CacheRepository,
            "request": RequestRepository,
        })
    repo_class = _REPO_MAP.get(name)
    if repo_class is None:
        raise ValueError(f"Unknown repository: {name}. Available: {list(_REPO_MAP.keys())}")
    return repo_class(session=session)


# ---------------------------------------------------------------------------
# Song Repository
# ---------------------------------------------------------------------------
class SongRepository:
    def __init__(self, session: Session | None = None):
        self._session = session

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = get_session()
        return self._session

    def get(self, song_id: str) -> Song | None:
        row = self.session.execute(
            select(SongTable).where(SongTable.song_id == song_id)
        ).scalar_one_or_none()
        if row is None:
            return None
        return self._row_to_model(row)

    def get_by_title_artist(self, title: str, artist: str) -> Song | None:
        row = self.session.execute(
            select(SongTable).where(
                and_(
                    func.lower(SongTable.title) == title.lower(),
                    func.lower(SongTable.artist) == artist.lower(),
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return self._row_to_model(row)

    def search(self, query: str, limit: int = 50) -> list[Song]:
        q = query.lower()
        rows = self.session.execute(
            select(SongTable).where(
                (func.lower(SongTable.title).contains(q))
                | (func.lower(SongTable.artist).contains(q))
            ).limit(limit)
        ).scalars().all()
        return [self._row_to_model(r) for r in rows]

    def get_all(self, limit: int = 1000) -> list[Song]:
        rows = self.session.execute(
            select(SongTable).limit(limit)
        ).scalars().all()
        return [self._row_to_model(r) for r in rows]

    def get_by_language(self, language: str, limit: int = 200) -> list[Song]:
        rows = self.session.execute(
            select(SongTable).where(
                func.lower(SongTable.language) == language.lower()
            ).limit(limit)
        ).scalars().all()
        return [self._row_to_model(r) for r in rows]

    def get_by_genre(self, genre: str, limit: int = 200) -> list[Song]:
        rows = self.session.execute(
            select(SongTable).where(
                func.lower(SongTable.genre) == genre.lower()
            ).limit(limit)
        ).scalars().all()
        return [self._row_to_model(r) for r in rows]

    def get_candidates(
        self,
        languages: list[str] | None = None,
        genres: list[str] | None = None,
        exclude_ids: list[str] | None = None,
        explicit_allowed: bool = True,
        limit: int = 200,
    ) -> list[Song]:
        """Get candidate songs with basic filters for candidate generation."""
        stmt = select(SongTable)
        conditions = []
        if languages:
            lower_langs = [l.lower() for l in languages]
            conditions.append(func.lower(SongTable.language).in_(lower_langs))
        if not explicit_allowed:
            conditions.append(SongTable.explicit == False)
        if exclude_ids:
            conditions.append(SongTable.song_id.notin_(exclude_ids))
        if conditions:
            stmt = stmt.where(and_(*conditions))
        stmt = stmt.order_by(SongTable.popularity.desc()).limit(limit)
        rows = self.session.execute(stmt).scalars().all()
        return [self._row_to_model(r) for r in rows]

    def save(self, song: Song) -> None:
        existing = self.session.execute(
            select(SongTable).where(SongTable.song_id == song.song_id)
        ).scalar_one_or_none()
        if existing:
            for key, value in song.model_dump(
                exclude={"audio_features", "lyrics_features", "first_seen"}
            ).items():
                setattr(existing, key, value)
            existing.last_updated = _utc_now()
        else:
            row = SongTable(**song.model_dump(
                exclude={"audio_features", "lyrics_features"}
            ))
            self.session.add(row)
        self.session.commit()

    def count(self) -> int:
        return self.session.execute(select(func.count(SongTable.song_id))).scalar() or 0

    def _row_to_model(self, row: SongTable) -> Song:
        return Song(
            song_id=row.song_id,
            title=row.title,
            artist=row.artist,
            artists=row.artists or [],
            album=row.album,
            album_id=row.album_id,
            release_year=row.release_year,
            release_date=row.release_date,
            duration=row.duration,
            language=row.language,
            languages=row.languages or [],
            genre=row.genre,
            subgenre=row.subgenre,
            genres=row.genres or [],
            explicit=row.explicit or False,
            popularity=row.popularity or 0.5,
            is_remix=row.is_remix or False,
            is_live=row.is_live or False,
            is_clean_version=row.is_clean_version or False,
            version_type=row.version_type,
            original_song_id=row.original_song_id,
            bpm=row.bpm,
            key=row.key,
            energy=row.energy,
            danceability=row.danceability,
            valence=row.valence,
            lyrics_available=row.lyrics_available or False,
            lyrics_analysis_available=row.lyrics_analysis_available or False,
            audio_analysis_status=row.audio_analysis_status or "PENDING",
            lyrics_analysis_status=row.lyrics_analysis_status or "PENDING",
            source_provider=row.source_provider,
            source_provider_id=row.source_provider_id,
            provider_ids=row.provider_ids or {},
            file_path=row.file_path,
            file_hash=row.file_hash,
            first_seen=row.first_seen,
            last_updated=row.last_updated,
        )


# ---------------------------------------------------------------------------
# Audio Features Repository
# ---------------------------------------------------------------------------
class AudioFeaturesRepository:
    def __init__(self, session: Session | None = None):
        self._session = session

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = get_session()
        return self._session

    def get(self, song_id: str) -> AudioFeatures | None:
        row = self.session.execute(
            select(AudioFeaturesTable).where(AudioFeaturesTable.song_id == song_id)
        ).scalar_one_or_none()
        if row is None:
            return None
        return AudioFeatures(
            song_id=row.song_id, bpm=row.bpm, tempo=row.tempo, key=row.key,
            loudness=row.loudness, energy=row.energy, danceability=row.danceability,
            valence=row.valence, acousticness=row.acousticness,
            instrumentalness=row.instrumentalness, speechiness=row.speechiness,
            spectral_centroid=row.spectral_centroid, spectral_bandwidth=row.spectral_bandwidth,
            spectral_rolloff=row.spectral_rolloff, zero_crossing_rate=row.zero_crossing_rate,
            mfcc_mean=row.mfcc_mean, chroma_mean=row.chroma_mean, onset_rate=row.onset_rate,
            duration=row.duration, file_hash=row.file_hash,
            analyzer_version=row.analyzer_version, analysis_version=row.analysis_version or 1,
            analysis_status=row.analysis_status or "PENDING", analyzed_at=row.analyzed_at,
            audio_embedding=row.audio_embedding,
        )

    def is_analyzed(self, song_id: str, analyzer_version: str | None = None) -> bool:
        row = self.session.execute(
            select(AudioFeaturesTable).where(
                and_(
                    AudioFeaturesTable.song_id == song_id,
                    AudioFeaturesTable.analysis_status == "COMPLETE",
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return False
        if analyzer_version and row.analyzer_version != analyzer_version:
            return False
        return True

    def save(self, features: AudioFeatures) -> None:
        existing = self.session.execute(
            select(AudioFeaturesTable).where(AudioFeaturesTable.song_id == features.song_id)
        ).scalar_one_or_none()
        data = features.model_dump()
        if existing:
            for key, value in data.items():
                if key != "song_id":
                    setattr(existing, key, value)
        else:
            row = AudioFeaturesTable(**data)
            self.session.add(row)
        self.session.commit()


# ---------------------------------------------------------------------------
# Lyrics Features Repository
# ---------------------------------------------------------------------------
class LyricsFeaturesRepository:
    def __init__(self, session: Session | None = None):
        self._session = session

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = get_session()
        return self._session

    def get(self, song_id: str) -> LyricsFeatures | None:
        row = self.session.execute(
            select(LyricsFeaturesTable).where(LyricsFeaturesTable.song_id == song_id)
        ).scalar_one_or_none()
        if row is None:
            return None
        return LyricsFeatures(
            song_id=row.song_id, language=row.language, themes=row.themes or [],
            sentiment=row.sentiment, mood=row.mood, romance=row.romance or 0.0,
            sadness=row.sadness or 0.0, celebration=row.celebration or 0.0,
            aggression=row.aggression or 0.0, sexual_content=row.sexual_content or 0.0,
            explicitness=row.explicitness or 0.0, violence=row.violence or 0.0,
            drugs=row.drugs or 0.0, breakup=row.breakup or 0.0,
            nostalgia=row.nostalgia or 0.0, family_friendly=row.family_friendly,
            event_suitability=row.event_suitability or {},
            source=row.source, content_hash=row.content_hash,
            analysis_model=row.analysis_model, analysis_version=row.analysis_version or 1,
            analysis_status=row.analysis_status or "PENDING", analyzed_at=row.analyzed_at,
            lyrics_embedding=row.lyrics_embedding,
        )

    def is_analyzed(self, song_id: str, analysis_model: str | None = None, analysis_version: int | None = None) -> bool:
        row = self.session.execute(
            select(LyricsFeaturesTable).where(
                and_(
                    LyricsFeaturesTable.song_id == song_id,
                    LyricsFeaturesTable.analysis_status == "COMPLETE",
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return False
        if analysis_model and row.analysis_model != analysis_model:
            return False
        if analysis_version and row.analysis_version != analysis_version:
            return False
        return True

    def save(self, features: LyricsFeatures) -> None:
        existing = self.session.execute(
            select(LyricsFeaturesTable).where(LyricsFeaturesTable.song_id == features.song_id)
        ).scalar_one_or_none()
        data = features.model_dump()
        if existing:
            for key, value in data.items():
                if key != "song_id":
                    setattr(existing, key, value)
        else:
            row = LyricsFeaturesTable(**data)
            self.session.add(row)
        self.session.commit()


# ---------------------------------------------------------------------------
# Event Repository
# ---------------------------------------------------------------------------
class EventRepository:
    def __init__(self, session: Session | None = None):
        self._session = session

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = get_session()
        return self._session

    def save_event(self, config: EventConfig, state: EventState) -> None:
        existing = self.session.execute(
            select(EventTable).where(EventTable.event_id == config.event_id)
        ).scalar_one_or_none()
        if existing:
            existing.state_json = state.model_dump(mode="json")
            existing.updated_at = _utc_now()
            existing.is_active = not state.is_ended
            if state.is_ended:
                existing.ended_at = state.event_ended_at
        else:
            row = EventTable(
                event_id=config.event_id,
                name=config.name,
                event_type=config.event_type,
                config_json=config.model_dump(mode="json"),
                state_json=state.model_dump(mode="json"),
            )
            self.session.add(row)
        self.session.commit()

    def save_state(self, event_id: str, state: EventState) -> None:
        self.session.execute(
            update(EventTable).where(EventTable.event_id == event_id).values(
                state_json=state.model_dump(mode="json"),
                updated_at=_utc_now(),
            )
        )
        self.session.commit()

    def get_event(self, event_id: str) -> tuple[EventConfig, EventState] | None:
        row = self.session.execute(
            select(EventTable).where(EventTable.event_id == event_id)
        ).scalar_one_or_none()
        if row is None:
            return None
        config = EventConfig.model_validate(row.config_json)
        state = EventState.model_validate(row.state_json)
        return config, state

    def get_active_event(self) -> tuple[EventConfig, EventState] | None:
        row = self.session.execute(
            select(EventTable).where(EventTable.is_active == True).order_by(
                EventTable.updated_at.desc()
            ).limit(1)
        ).scalar_one_or_none()
        if row is None:
            return None
        config = EventConfig.model_validate(row.config_json)
        state = EventState.model_validate(row.state_json)
        return config, state


# ---------------------------------------------------------------------------
# Play History Repository
# ---------------------------------------------------------------------------
class PlayHistoryRepository:
    def __init__(self, session: Session | None = None):
        self._session = session

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = get_session()
        return self._session

    def add(self, **kwargs) -> None:
        row = PlayHistoryTable(**kwargs)
        self.session.add(row)
        self.session.commit()

    def get_event_history(self, event_id: str) -> list[dict]:
        rows = self.session.execute(
            select(PlayHistoryTable).where(
                PlayHistoryTable.event_id == event_id
            ).order_by(PlayHistoryTable.position)
        ).scalars().all()
        return [
            {c.name: getattr(r, c.name) for c in PlayHistoryTable.__table__.columns}
            for r in rows
        ]

    def get_recent(self, event_id: str, limit: int = 20) -> list[dict]:
        rows = self.session.execute(
            select(PlayHistoryTable).where(
                PlayHistoryTable.event_id == event_id
            ).order_by(PlayHistoryTable.position.desc()).limit(limit)
        ).scalars().all()
        return [
            {c.name: getattr(r, c.name) for c in PlayHistoryTable.__table__.columns}
            for r in rows
        ]


# ---------------------------------------------------------------------------
# Feedback Repository
# ---------------------------------------------------------------------------
class FeedbackRepository:
    def __init__(self, session: Session | None = None):
        self._session = session

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = get_session()
        return self._session

    def save_song_feedback(self, feedback: SongFeedback) -> None:
        row = FeedbackTable(
            feedback_id=feedback.feedback_id,
            event_id=feedback.event_id,
            song_id=feedback.song_id,
            overall_rating=feedback.overall_rating,
            energy_rating=feedback.energy_rating,
            song_choice_rating=feedback.song_choice_rating,
            transition_rating=feedback.transition_rating,
            vibe_rating=feedback.vibe_rating,
            context_json=feedback.model_dump(mode="json"),
            decision_epoch=feedback.decision_epoch,
            was_requested=feedback.was_requested,
            request_id=feedback.request_id,
        )
        self.session.add(row)
        self.session.commit()

    def save_transition_feedback(self, feedback: TransitionFeedback) -> None:
        row = TransitionFeedbackTable(
            feedback_id=feedback.feedback_id,
            event_id=feedback.event_id,
            from_song_id=feedback.from_song_id,
            to_song_id=feedback.to_song_id,
            transition_rating=feedback.transition_rating,
            context_json=feedback.model_dump(mode="json"),
            decision_epoch=feedback.decision_epoch,
        )
        self.session.add(row)
        self.session.commit()

    def save_event_feedback(self, feedback: EventFeedback) -> None:
        row = EventFeedbackTable(
            feedback_id=feedback.feedback_id,
            event_id=feedback.event_id,
            overall_performance=feedback.overall_performance,
            song_selection=feedback.song_selection,
            vibe_maintenance=feedback.vibe_maintenance,
            transitions=feedback.transitions,
            request_handling=feedback.request_handling,
            variety=feedback.variety,
            songs_played=feedback.songs_played,
            total_requests=feedback.total_requests,
            accepted_requests=feedback.accepted_requests,
            deferred_requests=feedback.deferred_requests,
            rejected_requests=feedback.rejected_requests,
            average_song_feedback=feedback.average_song_feedback,
            comments=feedback.comments,
        )
        self.session.add(row)
        self.session.commit()

    def get_song_feedback_avg(self, event_id: str) -> float | None:
        result = self.session.execute(
            select(func.avg(FeedbackTable.overall_rating)).where(
                FeedbackTable.event_id == event_id
            )
        ).scalar()
        return result

    def get_song_historical_feedback(self, song_id: str) -> list[dict]:
        rows = self.session.execute(
            select(FeedbackTable).where(FeedbackTable.song_id == song_id)
        ).scalars().all()
        return [
            {c.name: getattr(r, c.name) for c in FeedbackTable.__table__.columns}
            for r in rows
        ]


# ---------------------------------------------------------------------------
# Agent Decision Repository
# ---------------------------------------------------------------------------
class AgentDecisionRepository:
    def __init__(self, session: Session | None = None):
        self._session = session

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = get_session()
        return self._session

    def save(self, decision: AgentDecision) -> None:
        row = AgentDecisionTable(**decision.model_dump())
        self.session.add(row)
        self.session.commit()

    def save_scoring_snapshot(self, snapshot: ScoringSnapshot) -> None:
        row = ScoringSnapshotTable(**snapshot.model_dump())
        self.session.add(row)
        self.session.commit()

    def get_latest_snapshot(self, event_id: str, song_id: str) -> dict | None:
        row = self.session.execute(
            select(ScoringSnapshotTable).where(
                and_(
                    ScoringSnapshotTable.event_id == event_id,
                    ScoringSnapshotTable.song_id == song_id,
                )
            ).order_by(ScoringSnapshotTable.decision_epoch.desc()).limit(1)
        ).scalar_one_or_none()
        if row is None:
            return None
        return {c.name: getattr(row, c.name) for c in ScoringSnapshotTable.__table__.columns}


# ---------------------------------------------------------------------------
# Reward Repository
# ---------------------------------------------------------------------------
class RewardRepository:
    def __init__(self, session: Session | None = None):
        self._session = session

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = get_session()
        return self._session

    def save(self, record: RewardRecord) -> None:
        row = RewardTable(
            reward_id=record.reward_id,
            event_id=record.event_id,
            decision_epoch=record.decision_epoch,
            state_json=record.model_dump(mode="json", include={
                "state_vibe", "state_energy", "state_event_type",
                "state_event_progress", "state_recent_genres",
                "state_recent_artists", "state_audience_age",
            }),
            action_song_id=record.action_song_id,
            action_score=record.action_score,
            action_components=record.action_score_components.model_dump() if record.action_score_components else {},
            reward=record.reward,
            raw_feedback=record.raw_feedback,
            next_state_json=record.model_dump(mode="json", include={
                "next_state_vibe", "next_state_energy", "next_state_event_progress",
            }),
            context_json=record.context,
        )
        self.session.add(row)
        self.session.commit()


# ---------------------------------------------------------------------------
# Learned Preference Repository
# ---------------------------------------------------------------------------
class LearnedPreferenceRepository:
    def __init__(self, session: Session | None = None):
        self._session = session

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = get_session()
        return self._session

    def get_preference(self, event_type: str, context_key: str, preference_type: str, preference_value: str) -> dict | None:
        row = self.session.execute(
            select(LearnedPreferenceTable).where(
                and_(
                    LearnedPreferenceTable.event_type == event_type,
                    LearnedPreferenceTable.context_key == context_key,
                    LearnedPreferenceTable.preference_type == preference_type,
                    LearnedPreferenceTable.preference_value == preference_value,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return {c.name: getattr(row, c.name) for c in LearnedPreferenceTable.__table__.columns}

    def update_preference(
        self,
        event_type: str,
        context_key: str,
        preference_type: str,
        preference_value: str,
        reward: float,
        context: dict | None = None,
    ) -> None:
        existing = self.session.execute(
            select(LearnedPreferenceTable).where(
                and_(
                    LearnedPreferenceTable.event_type == event_type,
                    LearnedPreferenceTable.context_key == context_key,
                    LearnedPreferenceTable.preference_type == preference_type,
                    LearnedPreferenceTable.preference_value == preference_value,
                )
            )
        ).scalar_one_or_none()

        if existing:
            n = existing.sample_count + 1
            existing.average_reward = (
                (existing.average_reward or 0.0) * existing.sample_count + reward
            ) / n
            existing.sample_count = n
            existing.last_reward = reward
            existing.score_adjustment = existing.average_reward * min(1.0, n / 10.0)
            existing.confidence = min(1.0, n / 20.0)
            existing.updated_at = _utc_now()
            if context:
                existing.context_json = context
        else:
            row = LearnedPreferenceTable(
                event_type=event_type,
                context_key=context_key,
                preference_type=preference_type,
                preference_value=preference_value,
                score_adjustment=reward * 0.1,
                confidence=0.05,
                sample_count=1,
                last_reward=reward,
                average_reward=reward,
                context_json=context or {},
            )
            self.session.add(row)
        self.session.commit()

    def get_adjustments(self, event_type: str, context_key: str | None = None) -> list[dict]:
        stmt = select(LearnedPreferenceTable).where(
            LearnedPreferenceTable.event_type == event_type
        )
        if context_key:
            stmt = stmt.where(LearnedPreferenceTable.context_key == context_key)
        rows = self.session.execute(stmt).scalars().all()
        return [
            {c.name: getattr(r, c.name) for c in LearnedPreferenceTable.__table__.columns}
            for r in rows
        ]


# ---------------------------------------------------------------------------
# Cache Repository
# ---------------------------------------------------------------------------
class CacheRepository:
    def __init__(self, session: Session | None = None):
        self._session = session

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = get_session()
        return self._session

    def get(self, provider: str, resource_type: str, resource_id: str) -> CacheEntry | None:
        row = self.session.execute(
            select(APICacheTable).where(
                and_(
                    APICacheTable.provider == provider,
                    APICacheTable.resource_type == resource_type,
                    APICacheTable.resource_id == resource_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        entry = CacheEntry(
            cache_id=row.cache_id,
            provider=row.provider,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            data=row.data or {},
            cache_version=row.cache_version or 1,
            source_url=row.source_url,
            status_code=row.status_code,
            created_at=row.created_at,
            last_updated=row.last_updated,
            expires_at=row.expires_at,
            ttl_seconds=row.ttl_seconds,
            hit_count=row.hit_count or 0,
            last_accessed=row.last_accessed,
        )
        # Check expiry
        if entry.is_expired():
            return None
        # Touch
        row.hit_count = (row.hit_count or 0) + 1
        row.last_accessed = _utc_now()
        self.session.commit()
        return entry

    def save(self, entry: CacheEntry) -> None:
        existing = self.session.execute(
            select(APICacheTable).where(
                and_(
                    APICacheTable.provider == entry.provider,
                    APICacheTable.resource_type == entry.resource_type,
                    APICacheTable.resource_id == entry.resource_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            existing.data = entry.data
            existing.cache_version = entry.cache_version
            existing.last_updated = _utc_now()
            existing.expires_at = entry.expires_at
            existing.ttl_seconds = entry.ttl_seconds
            existing.status_code = entry.status_code
            existing.source_url = entry.source_url
        else:
            row = APICacheTable(**entry.model_dump())
            self.session.add(row)
        self.session.commit()

    def delete_expired(self) -> int:
        result = self.session.execute(
            delete(APICacheTable).where(
                and_(
                    APICacheTable.expires_at.isnot(None),
                    APICacheTable.expires_at < _utc_now(),
                )
            )
        )
        self.session.commit()
        return result.rowcount

    def stats(self) -> dict:
        total = self.session.execute(select(func.count(APICacheTable.cache_id))).scalar() or 0
        providers = self.session.execute(
            select(APICacheTable.provider, func.count(APICacheTable.cache_id)).group_by(
                APICacheTable.provider
            )
        ).all()
        return {
            "total_entries": total,
            "providers": {p: c for p, c in providers},
        }


# ---------------------------------------------------------------------------
# Request Repository
# ---------------------------------------------------------------------------
class RequestRepository:
    def __init__(self, session: Session | None = None):
        self._session = session

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = get_session()
        return self._session

    def save(self, request_data: dict) -> None:
        existing = self.session.execute(
            select(RequestTable).where(RequestTable.request_id == request_data["request_id"])
        ).scalar_one_or_none()
        if existing:
            for key, value in request_data.items():
                if key != "request_id":
                    setattr(existing, key, value)
        else:
            row = RequestTable(**request_data)
            self.session.add(row)
        self.session.commit()

    def get(self, request_id: str) -> dict | None:
        row = self.session.execute(
            select(RequestTable).where(RequestTable.request_id == request_id)
        ).scalar_one_or_none()
        if row is None:
            return None
        return {c.name: getattr(row, c.name) for c in RequestTable.__table__.columns}

    def get_pending(self, event_id: str) -> list[dict]:
        rows = self.session.execute(
            select(RequestTable).where(
                and_(
                    RequestTable.event_id == event_id,
                    RequestTable.status.in_(["RECEIVED", "VALIDATING", "ANALYZING", "DECISION", "QUEUED", "DEFERRED", "BRIDGING"]),
                )
            ).order_by(RequestTable.created_at)
        ).scalars().all()
        return [
            {c.name: getattr(r, c.name) for c in RequestTable.__table__.columns}
            for r in rows
        ]
