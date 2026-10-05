-- Read-only export: five reference episodes plus the seven latest Gooaye episodes.
-- Run with psql -X -At; split the returned object's arrays into local JSON files.
WITH gooaye AS (
    SELECT episode_id, podcast_name, episode_number,
           doc->>'summary_public_url' AS summary_public_url,
           COALESCE(
               CASE WHEN doc->>'released_at_ms' ~ '^[0-9]+$'
                    THEN to_timestamp((doc->>'released_at_ms')::numeric / 1000) END,
               CASE WHEN doc->>'spotify_release_date' ~ '^\d{4}-\d{2}-\d{2}'
                    THEN (doc->>'spotify_release_date')::timestamptz END,
               created_time::timestamptz
           ) AS released_at
    FROM firestore_mirror.episodes
    WHERE podcast_name LIKE 'Gooaye%'
), latest AS (
    SELECT episode_id FROM gooaye
    ORDER BY released_at DESC NULLS LAST, episode_id LIMIT 7
), selected AS (
    SELECT * FROM gooaye
    WHERE episode_id IN (SELECT episode_id FROM latest)
       OR episode_id IN (
           'Gooaye_3c41570df0533037', 'Gooaye_78a3c8f461067d9f',
           'Gooaye_a1edbf86414f238c', 'Gooaye_c59207fee1b27808',
           'Gooaye_b73bc79724e12139'
       )
)
SELECT jsonb_build_object(
    'episodes', (SELECT jsonb_agg(to_jsonb(s) ORDER BY released_at, episode_id)
                 FROM selected s),
    'taxonomy', (SELECT jsonb_agg(jsonb_build_object(
        'slug', slug, 'display_zh', display_zh, 'kind', kind,
        'exposure_id', exposure_id, 'exposure_type', exposure_type,
        'aliases', aliases, 'members', members
    ) ORDER BY exposure_id, slug) FROM tag_registry WHERE exposure_type = 'theme')
);
