"""The SQLAlchemy-vs-libpq URL boundary."""

from shared.db import libpq_url


def test_the_sqlalchemy_dialect_suffix_is_dropped():
    """psycopg.connect on the stored form fails with
    `missing "=" after "postgresql+psycopg://…"`. That broke the hourly trending timer 72
    times in 72 hours and made every podcast in the ingest error out — while the ingest
    still exited 0."""
    assert libpq_url("postgresql+psycopg://u:p@h:5433/d") == "postgresql://u:p@h:5433/d"


def test_a_plain_url_is_untouched():
    assert libpq_url("postgresql://u:p@h/d") == "postgresql://u:p@h/d"


def test_credentials_and_query_survive_intact():
    """Only the scheme is rewritten — a password with url-encoded punctuation must not be
    mangled on the way through."""
    url = "postgresql+psycopg://user:A%40b%23c%24d@127.0.0.1:5433/db?sslmode=disable"
    assert libpq_url(url) == "postgresql://user:A%40b%23c%24d@127.0.0.1:5433/db?sslmode=disable"


def test_empty_and_malformed_input_pass_through():
    """The caller's own "is it set?" check should report a missing URL, not this."""
    assert libpq_url(None) is None
    assert libpq_url("") == ""
    assert libpq_url("not-a-url") == "not-a-url"
