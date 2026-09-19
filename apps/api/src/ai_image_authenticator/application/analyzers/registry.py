"""Open/Closed registry — new analyzers register here without rewriting fusion."""

from __future__ import annotations

from ai_image_authenticator.domain.ports import Analyzer


class AnalyzerRegistry:
    def __init__(self) -> None:
        self._analyzers: list[Analyzer] = []
        self._by_id: dict[str, Analyzer] = {}

    def register(self, analyzer: Analyzer) -> None:
        if analyzer.id in self._by_id:
            raise ValueError(f"Analyzer already registered: {analyzer.id}")
        self._analyzers.append(analyzer)
        self._by_id[analyzer.id] = analyzer

    def all(self) -> list[Analyzer]:
        return list(self._analyzers)

    def get(self, analyzer_id: str) -> Analyzer | None:
        return self._by_id.get(analyzer_id)

    def ids(self) -> list[str]:
        return [a.id for a in self._analyzers]
