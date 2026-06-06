"""News ingest pipeline — fetch → dedup → extract → enrich → resolve → write.

Steps live in :mod:`news.pipeline.steps`, mirroring
``services/podcast/src/pipeline/steps/``. :func:`news.orchestrator.run` drives
them end to end for every feed in ``feeds.json``.
"""
