from __future__ import annotations
import logging
import hashlib
import os

try:
    import librosa
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False

logger = logging.getLogger(__name__)

class FeatureExtractor:
    """Structured feature extraction using librosa if available."""
    
    def compute_file_hash(self, file_path: str) -> str:
        """Compute SHA-256 hash of a file."""
        if not os.path.exists(file_path):
            return ""
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def extract_features(self, file_path: str) -> dict:
        """Extract raw features using librosa."""
        if not LIBROSA_AVAILABLE:
            logger.warning("librosa not available. Feature extraction disabled.")
            return {}
            
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return {}
            
        try:
            y, sr = librosa.load(file_path, sr=22050, duration=30.0) # analyze first 30s
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
            S = np.abs(librosa.stft(y))
            chroma = librosa.feature.chroma_stft(S=S, sr=sr)
            
            # Simple key estimation from chroma
            chroma_mean = np.mean(chroma, axis=1)
            keys = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
            estimated_key = keys[np.argmax(chroma_mean)]
            
            rms = librosa.feature.rms(y=y)
            zcr = librosa.feature.zero_crossing_rate(y)
            spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
            
            return {
                "bpm": float(tempo[0]) if isinstance(tempo, np.ndarray) else float(tempo),
                "key": estimated_key,
                "rms_mean": float(np.mean(rms)),
                "zcr_mean": float(np.mean(zcr)),
                "spectral_centroid_mean": float(np.mean(spectral_centroid)),
                "chroma_mean": chroma_mean.tolist()
            }
        except Exception as e:
            logger.error(f"Feature extraction failed for {file_path}: {e}")
            return {}

    def estimate_energy(self, features: dict) -> float:
        """Estimate energy (0-1) from raw features."""
        if not features:
            return 0.0
        # Heuristic based on RMS (loudness)
        rms = features.get("rms_mean", 0.0)
        return min(1.0, rms * 10.0)

    def estimate_danceability(self, features: dict) -> float:
        """Estimate danceability (0-1)."""
        if not features:
            return 0.0
        # Heuristic based on tempo suitability for dancing (e.g. 100-130 BPM is high danceability)
        bpm = features.get("bpm", 0.0)
        if 90 <= bpm <= 140:
            return 0.8
        elif 60 <= bpm < 90 or 140 < bpm <= 170:
            return 0.5
        return 0.2

    def estimate_valence(self, features: dict) -> float:
        """Estimate valence (0-1) (musical positiveness)."""
        if not features:
            return 0.0
        # Very rough heuristic: higher spectral centroid often correlates with brighter sounds
        sc = features.get("spectral_centroid_mean", 0.0)
        return min(1.0, max(0.0, sc / 4000.0))

import numpy as np # Ensure numpy is available for the extractor if librosa is used
