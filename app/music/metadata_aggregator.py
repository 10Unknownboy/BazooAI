from __future__ import annotations
import logging
from typing import List, Dict
from app.music.metadata_adapter import MusicMetadataProvider
from app.models.song import Song

logger = logging.getLogger(__name__)

class MetadataAggregator:
    """Metadata aggregator (spec §7)."""
    
    def __init__(self, providers: List[MusicMetadataProvider]):
        self.providers = providers

    def _generate_dedup_key(self, title: str, artist: str) -> str:
        return f"{title.strip().lower()}::{artist.strip().lower()}"

    async def search_and_enrich(self, query: str) -> List[Dict]:
        """Search across all providers and merge results."""
        merged_results = {}
        
        for provider in self.providers:
            try:
                results = await provider.search_song(query)
                for res in results:
                    key = self._generate_dedup_key(res["title"], res["artist"])
                    if key not in merged_results:
                        merged_results[key] = res
                    else:
                        # Merge strategy: take longer duration if available, keep first provider's ID
                        if res.get("duration", 0) > merged_results[key].get("duration", 0):
                            merged_results[key]["duration"] = res["duration"]
            except Exception as e:
                logger.error(f"Error searching provider {provider.provider_name}: {e}")
                
        return list(merged_results.values())

    async def enrich_song(self, song_id: str, provider_id: str) -> Dict:
        """Fetch missing metadata from available providers."""
        enriched_data = {}
        for provider in self.providers:
            try:
                meta = await provider.get_metadata(provider_id)
                if meta:
                    enriched_data.update({k: v for k, v in meta.items() if v is not None})
            except Exception as e:
                logger.error(f"Error enriching metadata from {provider.provider_name}: {e}")
        return enriched_data
