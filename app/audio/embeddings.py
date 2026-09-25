from __future__ import annotations
import logging
import numpy as np
from typing import List, Tuple
from app.models.song import AudioFeatures

logger = logging.getLogger(__name__)

class EmbeddingManager:
    """Audio embedding generation and similarity."""
    
    def generate_embedding(self, audio_features: AudioFeatures) -> list[float]:
        """Concatenates normalized audio features into a vector."""
        if audio_features.analysis_status != "COMPLETE":
            return []
            
        vector = np.array([
            audio_features.bpm / 200.0,  # Normalize assuming max ~200 BPM
            audio_features.energy,
            audio_features.danceability,
            audio_features.valence
        ], dtype=float)
        
        # L2 Normalization
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm
            
        return vector.tolist()

    def cosine_similarity(self, embedding1: list[float], embedding2: list[float]) -> float:
        """Calculate cosine similarity between two embeddings."""
        if not embedding1 or not embedding2 or len(embedding1) != len(embedding2):
            return 0.0
            
        v1 = np.array(embedding1)
        v2 = np.array(embedding2)
        
        dot_product = np.dot(v1, v2)
        norm_v1 = np.linalg.norm(v1)
        norm_v2 = np.linalg.norm(v2)
        
        if norm_v1 == 0 or norm_v2 == 0:
            return 0.0
            
        return float(dot_product / (norm_v1 * norm_v2))

    def find_similar(self, target_embedding: list[float], candidates: List[Tuple[str, list[float]]], top_k: int = 10) -> List[Tuple[str, float]]:
        """Find most similar items in candidates based on embeddings."""
        if not target_embedding:
            return []
            
        similarities = []
        for song_id, cand_emb in candidates:
            sim = self.cosine_similarity(target_embedding, cand_emb)
            similarities.append((song_id, sim))
            
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:top_k]
