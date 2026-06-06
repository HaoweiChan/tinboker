"""Smoke tests: verify key imports and class instantiation before restructuring.

These tests serve as a regression guard for the monorepo refactor.
They only check import-level concerns -- no external services needed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_pipeline_config_instantiates():
    from src.pipeline import PipelineConfig
    cfg = PipelineConfig(
        config_file=Path("podcasts_tw.json"),
        podcast_name="Test",
        podcast_link="https://example.com",
    )
    assert cfg.podcast_name == "Test"


def test_episode_processor_importable():
    from src.pipeline import EpisodeProcessor
    assert callable(EpisodeProcessor)


def test_service_container_importable():
    from src.pipeline import ServiceContainer
    sc = ServiceContainer()
    assert sc.firebase_service is None


def test_episode_data_importable():
    from src.pipeline import EpisodeData
    assert callable(EpisodeData)


def test_content_builder_importable():
    from src.podcast.content_builder import PipelineState, build_graph, run_pipeline
    assert callable(build_graph)
    assert callable(run_pipeline)
    assert PipelineState is not None


def test_wiki_builder_importable():
    from shared.wiki_builder import get_repository, ingest_episode
    assert callable(ingest_episode)
    assert callable(get_repository)


def test_wiki_router_importable():
    from src.routers import wiki
    assert wiki.router is not None
    assert callable(wiki.get_repo)


def test_orchestrator_run_pipeline_callable():
    from src.podcast.orchestrator import run_pipeline
    assert callable(run_pipeline)


def test_gcs_storage_service_importable():
    from src.service.gcs_storage_service import GCSStorageService
    assert callable(GCSStorageService)


def test_models_importable():
    from src.models.podcast_models import Sentence
    s = Sentence(index=0, content="test", start=0, end=100)
    assert s.content == "test"
