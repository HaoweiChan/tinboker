"""The timer should report useful partial ingestion as a successful run."""

from unittest.mock import Mock

import pytest
from news import cli, orchestrator
from news.orchestrator import RunSummary


@pytest.mark.parametrize(
    ("ingested", "failed", "skipped", "expected"),
    [(45, 5, 60, 0), (45, 0, 60, 0), (0, 5, 60, 1), (0, 0, 60, 0)],
)
def test_exit_status_depends_on_ingested_articles(monkeypatch, ingested, failed, skipped, expected):
    run = Mock(return_value=RunSummary(ingested=ingested, failed=failed, skipped=skipped))
    monkeypatch.setattr(orchestrator, "run", run)

    assert cli.main(["--no-bootstrap"]) == expected
    run.assert_called_once_with(feeds_path=None, limit=None)


def test_crashed_run_propagates_failure(monkeypatch):
    monkeypatch.setattr(orchestrator, "run", Mock(side_effect=RuntimeError("ingest crashed")))

    with pytest.raises(RuntimeError, match="ingest crashed"):
        cli.main(["--no-bootstrap"])
