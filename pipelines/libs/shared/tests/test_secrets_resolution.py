"""P6: prove the env-first resolution order and that GSM stays a last resort."""

import logging

import pytest
from shared import secrets


@pytest.fixture(autouse=True)
def _reset():
    secrets.reset()
    yield
    secrets.reset()


def _no_gsm(monkeypatch):
    """Any GSM client construction is a test failure."""
    def boom():
        raise AssertionError("GSM client constructed despite a populated environment")
    monkeypatch.setattr(secrets, "_gsm_client", boom)


def test_env_vars_win_and_gsm_is_never_constructed(monkeypatch, caplog):
    _no_gsm(monkeypatch)
    monkeypatch.setenv("REQUIRED_ONE", "from-env")
    monkeypatch.setenv("OPTIONAL_ONE", "from-env")

    with caplog.at_level(logging.INFO, logger=secrets.__name__):
        secrets.bootstrap(gsm_vars=("REQUIRED_ONE",), optional_vars=("OPTIONAL_ONE",))

    assert "secrets: REQUIRED_ONE source=env" in caplog.text


def test_env_file_fills_gaps_before_gsm(monkeypatch, tmp_path, caplog):
    _no_gsm(monkeypatch)
    monkeypatch.delenv("FROM_FILE_ONLY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("# comment\nFROM_FILE_ONLY=file-value\n", encoding="utf-8")

    with caplog.at_level(logging.INFO, logger=secrets.__name__):
        secrets.bootstrap(gsm_vars=("FROM_FILE_ONLY",), optional_vars=(), env_path=env_file)

    import os
    assert os.environ["FROM_FILE_ONLY"] == "file-value"
    assert "secrets: FROM_FILE_ONLY source=env-file" in caplog.text
    monkeypatch.delenv("FROM_FILE_ONLY", raising=False)


def test_gsm_is_the_fallback_when_nothing_else_supplies_it(monkeypatch, caplog):
    monkeypatch.delenv("ONLY_IN_GSM", raising=False)
    # Point the env-file search at a directory with no .env so a developer's real
    # file cannot satisfy the lookup.
    monkeypatch.setattr(secrets, "_ENV_FILE_CANDIDATES", ())

    class _FakeClient:
        def access_secret_version(self, name):
            assert name.endswith("/secrets/ONLY_IN_GSM/versions/latest")
            return type("R", (), {"payload": type("P", (), {"data": b"gsm-value"})})()

    monkeypatch.setattr(secrets, "_gsm_client", _FakeClient)

    with caplog.at_level(logging.INFO, logger=secrets.__name__):
        secrets.bootstrap(gsm_vars=("ONLY_IN_GSM",), optional_vars=())

    import os
    assert os.environ["ONLY_IN_GSM"] == "gsm-value"
    assert "source=gsm" in caplog.text
    monkeypatch.delenv("ONLY_IN_GSM", raising=False)
