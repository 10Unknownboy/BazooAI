from __future__ import annotations
import logging
from typing import Optional
from app.models.song import AudioFeatures
from app.database.repositories import AudioFeaturesRepository
from app.event.event_bus import get_event_bus, BusEvent
from app.audio.feature_extractor import FeatureExtractor
from app.audio.embeddings import EmbeddingManager

logger = logging.getLogger(__name__)

class AudioAnalyzer:
    """Audio analysis service (spec §8, 24)."""
    
    ANALYZER_VERSION = '1.0.0'
    
    def __init__(self, repository: AudioFeaturesRepository, feature_extractor: FeatureExtractor, embedding_manager: EmbeddingManager):
        self.repository = repository
        self.extractor = feature_extractor
        self.embedding_manager = embedding_manager
        self.event_bus = get_event_bus()

    def analyze(self, file_path: str, song_id: str, force: bool = False) -> AudioFeatures:
        """Analyze an audio file and extract features."""
        file_hash = self.extractor.compute_file_hash(file_path)
        
        if not force:
            existing = self.repository.get(song_id)
            if existing and existing.analyzer_version == self.ANALYZER_VERSION and existing.file_hash == file_hash:
                logger.info(f"Using cached audio analysis for {song_id}")
                return existing
                
        logger.info(f"Analyzing audio for {song_id} from {file_path}")
        raw_features = self.extractor.extract_features(file_path)
        
        if not raw_features:
            logger.warning(f"Feature extraction failed or unavailable for {song_id}")
            features = AudioFeatures(
                song_id=song_id,
                file_hash=file_hash,
                analyzer_version=self.ANALYZER_VERSION,
                analysis_version=1,
                bpm=0.0,
                key="Unknown",
                energy=0.0,
                danceability=0.0,
                valence=0.0,
                embedding=[],
                analysis_status="NOT_AVAILABLE"
            )
            self.repository.save(features)
            return features

        features = AudioFeatures(
            song_id=song_id,
            file_hash=file_hash,
            analyzer_version=self.ANALYZER_VERSION,
            analysis_version=1,
            bpm=raw_features.get("bpm", 0.0),
            key=raw_features.get("key", "Unknown"),
            energy=self.extractor.estimate_energy(raw_features),
            danceability=self.extractor.estimate_danceability(raw_features),
            valence=self.extractor.estimate_valence(raw_features),
            embedding=[],
            analysis_status="COMPLETE"
        )
        
        # Generate embedding
        features.embedding = self.embedding_manager.generate_embedding(features)
        
        self.repository.save(features)
        self.event_bus.publish(BusEvent(event_type="AUDIO_ANALYSIS_COMPLETE", data={"song_id": song_id}))
        return features
