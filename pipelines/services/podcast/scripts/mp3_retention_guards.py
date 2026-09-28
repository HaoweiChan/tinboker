"""Install dormant MP3 tombstone guards in both Postgres databases.

This migration creates no tombstones and deletes no data. A future retirement
transaction must lock every guarded table in its database with SHARE ROW
EXCLUSIVE, insert the normalized key, and clear all matching references before
committing. The lock orders writers against the tombstone's first visibility.

Run only as a database migration with both database URLs configured. The
retention pruner remains preview-only until its separate staged protocol lands.
"""

from __future__ import annotations

import argparse
import os
import sys
from urllib.parse import urlsplit

import psycopg
from shared.db import libpq_url
from src.service.gcs_storage_service import public_base

COMMON_SQL = r"""
CREATE SCHEMA IF NOT EXISTS mp3_retention;
CREATE TABLE IF NOT EXISTS mp3_retention.config (
    id integer PRIMARY KEY CHECK (id = 1),
    public_scheme text NOT NULL,
    public_authority text NOT NULL,
    public_path text NOT NULL
);
CREATE TABLE IF NOT EXISTS mp3_retention.tombstones (
    media_key text PRIMARY KEY,
    -- Retirement intent; the later two-database clear commit starts cache grace.
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE OR REPLACE FUNCTION mp3_retention.media_key(input_url text)
RETURNS text LANGUAGE plpgsql VOLATILE
SET search_path = pg_catalog, mp3_retention AS $function$
DECLARE
    clean text;
    match text[];
    authority_match text[];
    port_number integer;
    scheme text;
    authority text;
    raw_path text;
    decoded text;
    bucket text;
    blob text;
    base_scheme text;
    base_authority text;
    base_path text;
    bytes bytea := decode('', 'hex');
    pair text;
    i integer := 1;
    segments text[];
    local_origin boolean := false;
BEGIN
    IF input_url IS NULL OR btrim(input_url) = '' THEN
        RETURN NULL;
    END IF;
    IF position(chr(92) in input_url) > 0 OR input_url ~ '[[:cntrl:]]' THEN
        RAISE EXCEPTION 'Malformed media URL';
    END IF;
    clean := split_part(split_part(btrim(input_url), '#', 1), '?', 1);
    IF left(clean, 2) = '//' THEN
        clean := 'https:' || clean;
    END IF;
    SELECT public_scheme, public_authority, public_path
      INTO base_scheme, base_authority, base_path
      FROM mp3_retention.config WHERE id = 1;
    IF base_scheme IS NULL THEN
        RAISE EXCEPTION 'MP3 retention configuration is missing';
    END IF;

    IF clean ~* '^gs://' THEN
        match := regexp_match(clean, '^gs://([^/]+)/(.+)$', 'i');
        IF match IS NULL THEN
            RAISE EXCEPTION 'Malformed media URL';
        END IF;
        bucket := match[1];
        raw_path := match[2];
    ELSIF clean ~* '^https?://' THEN
        match := regexp_match(clean, '^(https?)://([^/]+)(/.*)$', 'i');
        IF match IS NULL THEN
            RETURN NULL;
        END IF;
        scheme := lower(match[1]);
        IF position('%' in match[2]) > 0 THEN
            RAISE EXCEPTION 'Malformed media URL';
        END IF;
        authority := regexp_replace(lower(match[2]), '^.*@', '');
        IF right(authority, 1) = '.' THEN
            authority := left(authority, length(authority) - 1);
        ELSE
            authority_match := regexp_match(authority, '^(.+)[.](:[0-9]+)$');
            IF authority_match IS NOT NULL THEN
                authority := authority_match[1] || authority_match[2];
            END IF;
        END IF;
        authority_match := regexp_match(authority, '^([^:]+):([0-9]+)$');
        IF authority_match IS NOT NULL THEN
            BEGIN
                port_number := authority_match[2]::integer;
            EXCEPTION WHEN numeric_value_out_of_range THEN
                RAISE EXCEPTION 'Malformed media URL';
            END;
            authority := authority_match[1] || ':' || port_number::text;
        ELSIF position(':' in authority) > 0 AND
              split_part(authority, ':', 1) = split_part(base_authority, ':', 1) THEN
            RAISE EXCEPTION 'Malformed media URL';
        END IF;
        IF scheme = 'https' AND authority IN ('storage.googleapis.com', 'storage.googleapis.com:443') THEN
            raw_path := substring(match[3] from 2);
            match := regexp_match(raw_path, '^([^/]+)/(.+)$');
            IF match IS NULL THEN
                RAISE EXCEPTION 'Malformed media URL';
            END IF;
            bucket := match[1];
            raw_path := match[2];
        ELSIF authority = base_authority OR
              (scheme = 'https' AND authority = base_authority || ':443') OR
              (scheme = 'http' AND authority = base_authority || ':80') THEN
            local_origin := true;
            IF left(match[3], length(base_path) + 1) <> base_path || '/' THEN
                RAISE EXCEPTION 'Malformed media URL';
            END IF;
            raw_path := substring(match[3] from length(base_path) + 2);
            match := regexp_match(raw_path, '^([^/]+)/(.+)$');
            IF match IS NULL THEN
                RAISE EXCEPTION 'Malformed media URL';
            END IF;
            bucket := match[1];
            raw_path := match[2];
        ELSE
            RETURN NULL;
        END IF;
    ELSE
        RETURN NULL;
    END IF;

    -- Decode the entire bucket/blob path bytewise; percent-escaped slash and
    -- mixed-case hex must map to the same tombstone as the ordinary spelling.
    raw_path := bucket || '/' || raw_path;
    WHILE i <= length(raw_path) LOOP
        IF substr(raw_path, i, 1) = '%' THEN
            pair := substr(raw_path, i + 1, 2);
            IF pair !~ '^[0-9A-Fa-f]{2}$' THEN
                RAISE EXCEPTION 'Malformed media URL';
            END IF;
            IF lower(pair) = '00' THEN
                RAISE EXCEPTION 'Malformed media URL';
            END IF;
            bytes := bytes || decode(pair, 'hex');
            i := i + 3;
        ELSE
            bytes := bytes || convert_to(substr(raw_path, i, 1), 'UTF8');
            i := i + 1;
        END IF;
    END LOOP;
    BEGIN
        decoded := convert_from(bytes, 'UTF8');
    EXCEPTION WHEN character_not_in_repertoire OR untranslatable_character THEN
        RAISE EXCEPTION 'Malformed media URL';
    END;
    IF position(chr(92) in decoded) > 0 OR decoded ~ '[[:cntrl:]]' THEN
        RAISE EXCEPTION 'Malformed media URL';
    END IF;
    segments := string_to_array(decoded, '/');
    IF array_position(segments, '') IS NOT NULL OR
       array_position(segments, '.') IS NOT NULL OR
       array_position(segments, '..') IS NOT NULL THEN
        RAISE EXCEPTION 'Malformed media URL';
    END IF;
    bucket := segments[1];
    blob := substring(decoded from length(bucket) + 2);
    IF bucket NOT IN ('graphfolio-articles', 'podcast-data-web') THEN
        IF local_origin THEN
            RAISE EXCEPTION 'Malformed media URL';
        END IF;
        RETURN NULL;
    END IF;
    IF blob !~ '(^|/)mp3/[^/]+/[^/]+[.]mp3$' THEN
        RAISE EXCEPTION 'Malformed media URL';
    END IF;
    RETURN decoded;
END
$function$;

CREATE OR REPLACE FUNCTION mp3_retention.guard_reference()
RETURNS trigger LANGUAGE plpgsql VOLATILE
SET search_path = pg_catalog, mp3_retention AS $function$
DECLARE
    urls text[];
    url text;
    key text;
BEGIN
    IF TG_TABLE_SCHEMA = 'firestore_mirror' AND TG_TABLE_NAME = 'episodes' THEN
        IF TG_OP = 'UPDATE' THEN
            IF NEW.doc->>'mp3_url' IS NOT DISTINCT FROM OLD.doc->>'mp3_url' AND
               NEW.doc->>'mp3_public_url' IS NOT DISTINCT FROM OLD.doc->>'mp3_public_url' THEN
                RETURN NEW;
            END IF;
        END IF;
        urls := ARRAY[NEW.doc->>'mp3_url', NEW.doc->>'mp3_public_url'];
    ELSIF TG_TABLE_SCHEMA = 'public' AND TG_TABLE_NAME = 'episodes' THEN
        IF TG_OP = 'UPDATE' THEN
            IF NEW.mp3_url IS NOT DISTINCT FROM OLD.mp3_url THEN
                RETURN NEW;
            END IF;
        END IF;
        urls := ARRAY[NEW.mp3_url];
    ELSIF TG_TABLE_SCHEMA = 'public' AND TG_TABLE_NAME = 'wiki_pages' THEN
        IF TG_OP = 'UPDATE' THEN
            IF NEW.frontmatter #>> '{source_urls,mp3}' IS NOT DISTINCT FROM
               OLD.frontmatter #>> '{source_urls,mp3}' THEN
                RETURN NEW;
            END IF;
        END IF;
        urls := ARRAY[NEW.frontmatter #>> '{source_urls,mp3}'];
    ELSE
        RAISE EXCEPTION 'Unexpected MP3 guard table';
    END IF;
    FOREACH url IN ARRAY urls LOOP
        key := mp3_retention.media_key(url);
        IF key IS NOT NULL AND EXISTS (
            SELECT 1 FROM mp3_retention.tombstones WHERE media_key = key
        ) THEN
            RAISE EXCEPTION 'Retired MP3 media reference';
        END IF;
    END LOOP;
    RETURN NEW;
END
$function$;

CREATE OR REPLACE FUNCTION mp3_retention.prevent_tombstone_removal()
RETURNS trigger LANGUAGE plpgsql
SET search_path = pg_catalog, mp3_retention AS $function$
BEGIN
    RAISE EXCEPTION 'MP3 tombstones are permanent';
END
$function$;
DROP TRIGGER IF EXISTS prevent_removal ON mp3_retention.tombstones;
CREATE TRIGGER prevent_removal BEFORE UPDATE OR DELETE OR TRUNCATE ON mp3_retention.tombstones
FOR EACH STATEMENT EXECUTE FUNCTION mp3_retention.prevent_tombstone_removal();
REVOKE UPDATE, DELETE, TRUNCATE ON mp3_retention.tombstones FROM PUBLIC;
"""

MIRROR_SQL = """
DROP TRIGGER IF EXISTS guard_mp3_reference ON firestore_mirror.episodes;
CREATE TRIGGER guard_mp3_reference BEFORE INSERT OR UPDATE ON firestore_mirror.episodes
FOR EACH ROW EXECUTE FUNCTION mp3_retention.guard_reference();
"""

WIKI_SQL = """
DROP TRIGGER IF EXISTS guard_mp3_reference ON public.episodes;
CREATE TRIGGER guard_mp3_reference BEFORE INSERT OR UPDATE ON public.episodes
FOR EACH ROW EXECUTE FUNCTION mp3_retention.guard_reference();
DROP TRIGGER IF EXISTS guard_mp3_reference ON public.wiki_pages;
CREATE TRIGGER guard_mp3_reference BEFORE INSERT OR UPDATE ON public.wiki_pages
FOR EACH ROW EXECUTE FUNCTION mp3_retention.guard_reference();
"""


def _public_origin() -> tuple[str, str, str]:
    parsed = urlsplit(public_base())
    if parsed.scheme not in ("http", "https") or not parsed.hostname or not parsed.path:
        raise ValueError("MEDIA_PUBLIC_BASE must contain an HTTP origin and path")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("MEDIA_PUBLIC_BASE must not contain credentials or a query")
    authority = parsed.hostname.lower().rstrip(".")
    if parsed.port and parsed.port != (443 if parsed.scheme == "https" else 80):
        authority += f":{parsed.port}"
    return parsed.scheme, authority, parsed.path.rstrip("/")


def install(conn: psycopg.Connection, *, wiki: bool, origin: tuple[str, str, str]) -> None:
    """Install one database atomically; the two databases are installed separately."""
    with conn.transaction(), conn.cursor() as cur:
        tables = ("public.episodes", "public.wiki_pages") if wiki else ("firestore_mirror.episodes",)
        cur.execute(
            "LOCK TABLE public.episodes, public.wiki_pages IN SHARE ROW EXCLUSIVE MODE"
            if wiki else
            "LOCK TABLE firestore_mirror.episodes IN SHARE ROW EXCLUSIVE MODE"
        )
        # SECURITY INVOKER functions read the ledger as their owner. The live
        # writer role and installer must therefore be the same table-owning role.
        for table in tables:
            owner = cur.execute(
                "SELECT current_user = pg_get_userbyid(relowner) "
                "FROM pg_class WHERE oid = %s::regclass",
                (table,),
            ).fetchone()
            if not owner or owner[0] is not True:
                raise RuntimeError("MP3 guard installer must own each guarded table")
        cur.execute(COMMON_SQL)
        cur.execute(
            "LOCK TABLE mp3_retention.config, mp3_retention.tombstones "
            "IN SHARE ROW EXCLUSIVE MODE"
        )
        existing = cur.execute(
            "SELECT public_scheme, public_authority, public_path "
            "FROM mp3_retention.config WHERE id = 1"
        ).fetchone()
        if existing and tuple(existing) != origin and cur.execute(
            "SELECT 1 FROM mp3_retention.tombstones LIMIT 1"
        ).fetchone():
            raise RuntimeError("Cannot change media origin after retirement has begun")
        cur.execute(
            "INSERT INTO mp3_retention.config "
            "(id, public_scheme, public_authority, public_path) VALUES (1, %s, %s, %s) "
            "ON CONFLICT (id) DO UPDATE SET public_scheme = EXCLUDED.public_scheme, "
            "public_authority = EXCLUDED.public_authority, public_path = EXCLUDED.public_path",
            origin,
        )
        cur.execute(WIKI_SQL if wiki else MIRROR_SQL)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true", help="install schema and triggers")
    args = parser.parse_args()
    if not args.install:
        parser.error("pass --install to apply this non-deleting migration")
    from src.secrets_bootstrap import bootstrap

    bootstrap()
    episode_url = os.getenv("EPISODE_DATABASE_URL")
    wiki_url = os.getenv("WIKI_DATABASE_URL")
    if not episode_url or not wiki_url:
        parser.error("EPISODE_DATABASE_URL and WIKI_DATABASE_URL are required")
    try:
        origin = _public_origin()
        with psycopg.connect(libpq_url(episode_url)) as conn:
            install(conn, wiki=False, origin=origin)
        with psycopg.connect(libpq_url(wiki_url)) as conn:
            install(conn, wiki=True, origin=origin)
    except Exception:
        # Driver errors may embed credential-bearing DSNs.
        print("MP3 guard installation failed; inspect database configuration", file=sys.stderr)
        raise SystemExit(1) from None
    print("MP3 tombstone guards installed; no tombstones or media files changed")


if __name__ == "__main__":
    main()
