"""P6: the GSM settings source is env-first and skips Secret Manager entirely
when the environment already supplies every migrated secret."""

import pytest

from src import config_loader
from src.config import Settings as _Settings
from src.config_loader import GCPSecretManagerSource, _GSM_FIELDS


@pytest.fixture(autouse=True)
def _explode_on_gsm(monkeypatch):
    """Any client construction fails loudly unless a test opts in."""
    def boom():
        raise AssertionError("Secret Manager client constructed unexpectedly")
    monkeypatch.setattr(config_loader, "_gsm_client", boom)


def test_no_gsm_client_when_env_supplies_every_secret(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "some-project")
    source = GCPSecretManagerSource(_Settings, resolved=_GSM_FIELDS)

    assert source() == {}


def test_resolution_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "some-project")
    source = GCPSecretManagerSource(_Settings, resolved=[f.upper() for f in _GSM_FIELDS])

    assert source() == {}


def test_gsm_serves_only_the_unresolved_fields(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "some-project")
    requested = []

    class _FakeClient:
        def access_secret_version(self, request):
            requested.append(request["name"].split("/secrets/")[1].split("/")[0])
            return type("R", (), {"payload": type("P", (), {"data": b"value"})})()

    monkeypatch.setattr(config_loader, "_gsm_client", _FakeClient)
    resolved = set(_GSM_FIELDS) - {"jwt_secret_key"}
    source = GCPSecretManagerSource(_Settings, resolved=resolved)

    assert source() == {"jwt_secret_key": "value"}
    assert requested == ["JWT_SECRET_KEY"]


def test_no_gsm_client_without_project_id(monkeypatch):
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    source = GCPSecretManagerSource(_Settings, resolved=())

    assert source() == {}
