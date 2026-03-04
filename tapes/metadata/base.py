from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class SearchResult:
    tmdb_id: int
    title: str
    year: int | None
    media_type: str       # "movie" | "tv"
    confidence: float
    director: str | None = None
    genre: str | None = None
    show: str | None = None
    season: int | None = None
    episode: int | None = None
    episode_title: str | None = None


class MetadataSource(ABC):
    @abstractmethod
    def search(self, title: str, year: int | None, media_type: str) -> list[SearchResult]:
        ...

    @abstractmethod
    def get_by_id(self, tmdb_id: int, media_type: str) -> SearchResult | None:
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Return False if the source cannot be reached or is not configured."""
        ...
