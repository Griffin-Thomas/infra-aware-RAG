"""Data models for search results."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SearchResult:
    """A single search result from hybrid search."""

    id: str
    score: float
    content: str
    doc_type: str
    metadata: dict[str, Any] = field(default_factory=dict)
    highlights: list[str] | None = None

    def __str__(self) -> str:
        """String representation."""
        preview = self.content[:100] + "..." if len(self.content) > 100 else self.content
        return f"SearchResult(id={self.id}, score={self.score:.3f}, type={self.doc_type}): {preview}"


@dataclass
class HybridSearchResults:
    """Results from a hybrid search query."""

    results: list[SearchResult] = field(default_factory=list)
    total_count: int = 0
    facets: dict[str, list[dict[str, Any]]] | None = None

    def __str__(self) -> str:
        """String representation."""
        return f"HybridSearchResults(count={len(self.results)}, total={self.total_count})"

    def __len__(self) -> int:
        """Number of results."""
        return len(self.results)

    def __iter__(self):
        """Iterate over results."""
        return iter(self.results)

    def __getitem__(self, index):
        """Get result by index."""
        return self.results[index]
