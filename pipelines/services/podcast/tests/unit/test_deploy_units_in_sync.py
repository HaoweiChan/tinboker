"""The scheduled ingest runs the content pipeline in-process, so a pipeline flag set
only on podcast-api.service never reaches the episodes it is meant to change."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
KEYS = ("PIPELINE_LLM_MODEL", "SOCIAL_COPY_WRITER_MODEL", "EXTRACTOR_MODEL", "THREADS_NATIVE_POLLS_ENABLED")


def _env(text: str) -> dict[str, str]:
    return dict(re.findall(r"^\s*Environment=(\w+)=(\S+)", text, re.M))


def test_ingest_unit_carries_the_api_units_pipeline_flags():
    api = _env((ROOT / ".github/workflows/pipelines-deploy.yml").read_text())
    ingest = _env((ROOT / "pipelines/services/podcast/deploy/tinboker-podcast-ingest.service").read_text())
    assert {k: ingest.get(k) for k in KEYS} == {k: api[k] for k in KEYS}
