"""Phase 12 — the service core: the JSON seam every front door (CLI, API, UI) sits on."""

from src.service.analyze import AnalysisResult, advise

__all__ = ["AnalysisResult", "advise"]
