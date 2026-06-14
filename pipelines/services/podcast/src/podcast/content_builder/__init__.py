"""Content-Builder: LangGraph pipeline for financial podcast analysis."""

from .observability import configure as _configure_tracing
from .state import PipelineState

_configure_tracing()

__all__ = ["build_graph", "run_pipeline", "PipelineState"]


def __getattr__(name: str):
    if name in {"build_graph", "run_pipeline"}:
        from .graph import build_graph, run_pipeline

        return {"build_graph": build_graph, "run_pipeline": run_pipeline}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
