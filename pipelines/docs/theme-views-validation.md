# Offline theme views validation

This prototype extracts up to three stance-bearing themes from each stored summary.
It is not connected to ingestion or publishing. Only local output files are written;
episode and taxonomy inputs are read-only exports. Generated artifacts stay outside Git.

## Export the sample

From the repository root, run the following in an environment with read-only SSH access.
The SQL selects the five reference episodes and the seven latest Gooaye episodes,
deduplicates overlapping IDs, and exports theme taxonomy names and aliases. It does not
silently substitute older episodes when a summary is missing. Check that the export has
all five reference IDs and twelve distinct episodes before spending any LLM calls.

```sh
export THEME_VIEWS_OUT=/private/tmp/claude-501/-Users-willy-Documents-tinboker--claude-worktrees-tinboker-recent-costs-2e56cc/8cd8c60f-aae0-42f7-bbd9-ede30d2300ec/scratchpad/theme_views
mkdir -p "$THEME_VIEWS_OUT"
ssh root@152.53.136.182 'U=$(docker exec tinboker-postgres printenv POSTGRES_USER); docker exec -i tinboker-postgres psql -X -U "$U" -d podcast_db -At -v ON_ERROR_STOP=1' \
  < pipelines/docs/theme-views-sample.sql > "$THEME_VIEWS_OUT/sample.json"
python3 - <<'PY'
import json
import os
from pathlib import Path

out = Path(os.environ['THEME_VIEWS_OUT'])
sample = json.loads((out / 'sample.json').read_text())
episodes = sample['episodes']
assert len(episodes) == len({row['episode_id'] for row in episodes}) == 12
assert all(row['summary_public_url'] for row in episodes)
assert {
    'Gooaye_3c41570df0533037', 'Gooaye_78a3c8f461067d9f',
    'Gooaye_a1edbf86414f238c', 'Gooaye_c59207fee1b27808',
    'Gooaye_b73bc79724e12139',
} <= {row['episode_id'] for row in episodes}
for key in ('episodes', 'taxonomy'):
    (out / f'{key}.json').write_text(
        json.dumps(sample[key], ensure_ascii=False, indent=2) + '\n'
    )
print(f'Exported {len(episodes)} episodes and {len(sample["taxonomy"])} theme rows')
PY
```

## Extract and review

Load the OpenRouter key into the process environment only; never enable shell tracing,
print the environment, or save the key. The script uses the existing podcast client
and model configuration. The run is capped at twelve unique episodes, with no paid
retry for an episode whose response failed validation. Cached raw responses allow
revalidation without another paid call; client initialization still requires the
configured environment and credentials.

```sh
export OPENROUTER_API_KEY="$(gcloud secrets versions access latest --secret=OPENROUTER_API_KEY --project=gen-lang-client-0901363254)"
cd pipelines
uv run --python 3.12 --package tinboker-podcast python -m podcast.theme_views_validation \
  --episodes-json "$THEME_VIEWS_OUT/episodes.json" \
  --taxonomy-json "$THEME_VIEWS_OUT/taxonomy.json" \
  --out "$THEME_VIEWS_OUT" \
  $(python3 -c 'import json,os; from pathlib import Path; print(" ".join(r["episode_id"] for r in json.loads((Path(os.environ["THEME_VIEWS_OUT"])/"episodes.json").read_text())))')
unset OPENROUTER_API_KEY
```

Alternatively, select from an export with `--podcast "Gooaye 股癌" --limit 7`.
Local `summary_markdown` or `summary_path` inputs avoid summary downloads.
Compare `theme_views_review.md` with its chapter headings and saved summaries.
Taxonomy IDs are assigned in code using normalized exact display-name/alias matches;
unknown or ambiguous labels stay null and are reported. Unregistered anchored tickers
retain a null market rather than an invented market.

The manual quality checks are EP640 bullish MLCC with 國巨 (2327), EP650 bullish
CPU / Agentic AI plus the aluminium-driven passive-components view, EP627 the
capacitor/inductor price-hike view, and EP646 no bullish passive-components view.
Passing mentions of consumer goods, smartphones, and autos must not become themes.
These are evaluation criteria, not extraction overrides.

## Network-free checks

```sh
cd pipelines
uv run --python 3.12 --package tinboker-podcast pytest services/podcast/tests/unit/test_theme_views_validation.py
uvx ruff check services/podcast/src/podcast/theme_views_validation.py services/podcast/tests/unit/test_theme_views_validation.py
```

If the worktree environment lacks pytest, the verified local fallback is:

```sh
UV_CACHE_DIR=/private/tmp/tinboker-theme-views-uv-cache \
UV_PROJECT_ENVIRONMENT=/Users/willy/Documents/tinboker/pipelines/.venv \
PYTHONPATH=services/podcast/src:libs/shared/src \
uv run --offline --no-sync --package tinboker-podcast python -m pytest \
  services/podcast/tests/unit/test_theme_views_validation.py -q
```

The SELECT export has not been verified against the live database in the restricted
development session. No live extraction quality or cost result is implied by the
network-free test results.
