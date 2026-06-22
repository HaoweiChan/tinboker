# Curated alias seed — alternate symbols that should resolve to a canonical ticker.
#
# Auto-name paths (FinMind/Massive) only fill names, never aliases, so most rows show
# an empty alias column. This seeds the *meaningful* multi-symbol cases (share classes,
# old/ADR symbols) onto existing rows on boot; per-row exchange-suffix forms like
# "2330.TW" are intentionally omitted because the batch resolver already strips suffixes.
#
# Derived from the canonical registry (pipelines/.../data/tickers.json). Applied only
# to rows that carry no aliases yet, so admin-curated aliases (e.g. SPCX -> "SpaceX")
# are never clobbered. Extend freely.
#
# (ticker, market, aliases)
ALIAS_SEED: list[tuple[str, str, list[str]]] = [
    ("GOOGL", "US", ["GOOG"]),                                  # Alphabet class A/C
    ("BRK", "US", ["BRK.A", "BRK.B", "BRK-A", "BRK-B", "BRKA", "BRKB"]),  # Berkshire
    ("ARM", "US", ["ARM.US"]),                                  # Arm Holdings ADR
]
