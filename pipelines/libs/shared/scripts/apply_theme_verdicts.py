#!/usr/bin/env python3
"""Turn reviewed theme membership into an admin taxonomy draft payload.

Reads one merged verdict file per theme —
``{definition, members: [{ticker, name, reason, source}], dropped: [...]}`` — and emits
the body for ``POST /api/admin/taxonomy/bulk``. That endpoint is the only supported
write path: it stores a draft plus a diff, and a second call publishes it. Nothing here
touches Postgres, and publishing needs an admin JWT a script cannot mint.

The payload is partial on purpose (``full: false``): each sector carries only the fields
we actually reviewed, so display names, icons, colours, aliases, tiers, redirects and
every industry roll-up keep whatever the live table already holds. ``description`` is
written only for themes that had none — an existing description is somebody's copy and
is not overwritten by a generated definition. ``description_override`` is the deliberate
exception: a reviewer who found the stored description itself wrong (it is what the
membership was judged against, so a wrong one poisons the whole theme) can replace it,
and every override is printed for a human to see.

A verdict marked ``"status": "insufficient"`` (a theme the reviewer could not fill) or
``"untouched"`` (an exposure this pass deliberately did not review) is left out of the
payload entirely, so its live rows stay exactly as they are and a human decides what
should happen to it. Every other theme that comes
back thinner than ``--min-members`` aborts the run — that is the unexpected case, and
shipping a one-member sector page is worse than shipping nothing.

    python apply_theme_verdicts.py --merged verdicts/merged --taxonomy live.jsonl \
        --out draft_payload.json

Then, with an admin token:
    curl -X POST .../api/admin/taxonomy/bulk -H 'Authorization: Bearer <admin jwt>' \
        -H 'Content-Type: application/json' --data @draft_payload.json
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys

RATIONALE = (
    "Theme membership re-reviewed against the official TPEx industry value chain "
    "(ic.tpex.org.tw): every company already in a theme and every candidate drawn from "
    "the segments that theme occupies was judged on one standard — a concrete, factual "
    "product or business link to the theme, stated in the member's reason. Members "
    "confirmed from the value-chain pool are marked source=ictpex; members kept from the "
    "previous table that sit outside those segments are marked source=curated; the rest "
    "were removed. Themes that had no description gained one written for this review."
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--merged", required=True, help="directory of merged verdict JSON files")
    ap.add_argument("--taxonomy", required=True, help="live taxonomy JSONL (one exposure per line)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--actor", default=None,
                    help="omit (default) to publish as the admin whose token is used. The API "
                         "accepts only bot:reasons-fill / bot:import as bot actors, and a bot "
                         "actor's writes are SKIPPED on any field an admin already owns")
    ap.add_argument("--entry", default="ictpex-membership-review")
    ap.add_argument("--rationale", default=RATIONALE)
    ap.add_argument("--min-members", type=int, default=3,
                    help="abort if a theme would end up thinner than this (0 disables)")
    ap.add_argument("--redirects", default=None,
                    help="JSON file of {from_exposure_id: to_exposure_id}. A redirect DELETES the "
                         "source exposure and points its URL at the target; this API has no partial "
                         "way to undo one, so it is not covered by a members-and-descriptions rollback")
    ap.add_argument("--max-fanout", type=int, default=5,
                    help="abort if one company would sit in more themes than this (0 disables)")
    args = ap.parse_args()

    live = {}
    for line in open(args.taxonomy, encoding="utf-8"):
        row = json.loads(line)
        live[row["exposure_id"]] = row

    sectors, thin, unknown, skipped_status = [], [], [], []
    filled, overridden = [], []
    added = kept = dropped = 0
    for fname in sorted(os.listdir(args.merged)):
        if not fname.endswith(".json"):
            continue
        v = json.load(open(os.path.join(args.merged, fname), encoding="utf-8"))
        eid = v["exposure_id"]
        row = live.get(eid)
        if row is None or row.get("redirect_to") or row.get("exposure_type") not in ("theme", "industry"):
            unknown.append(eid)
            continue
        if v.get("status") in ("insufficient", "untouched"):
            skipped_status.append((eid, v.get("status"), len(v.get("members") or [])))
            continue

        before = {m["ticker"]: m for m in (row.get("members") or [])}
        members = []
        for m in v["members"]:
            prev = before.get(m["ticker"], {})
            member = {"ticker": m["ticker"], "name": m["name"], "market": "TW",
                      "source": m["source"], "reason": m["reason"]}
            if prev.get("name_en"):
                member["name_en"] = prev["name_en"]
            members.append(member)
            kept += m["ticker"] in before
            added += m["ticker"] not in before
        dropped += len(before) - sum(1 for m in members if m["ticker"] in before)

        if args.min_members and len(members) < args.min_members:
            thin.append((eid, len(members)))

        sector = {"exposure_id": eid, "members": members}
        if (v.get("description_override") or "").strip():
            sector["description"] = v["description_override"]
            overridden.append(eid)
        elif not (row.get("description") or "").strip() and v.get("definition"):
            sector["description"] = v["definition"]
            filled.append(eid)
        sectors.append(sector)

    if unknown:
        sys.exit(f"unknown / non-theme / redirected exposure ids in verdicts: {unknown}")
    if thin:
        sys.exit("themes below --min-members (raise the floor deliberately or re-review): "
                 + ", ".join(f"{e}={n}" for e, n in thin))
    for eid, status, n in skipped_status:
        print(f"SKIPPED {eid}: marked {status} ({n} member(s)) — live rows untouched")

    # A company in too many themes makes every one of those pages say less. The review
    # caps this, but a hand-swapped verdict file can breach it, so the check runs here too.
    # Industries are excluded: they roll their child themes up, so every theme member sits
    # in its parent industry by construction and counting both would flag the whole market.
    if args.max_fanout:
        fanout = collections.Counter(
            m["ticker"] for s in sectors if live[s["exposure_id"]].get("exposure_type") == "theme"
            for m in s["members"]
        )
        over = [(t, n) for t, n in fanout.most_common() if n > args.max_fanout]
        if over:
            sys.exit("companies over --max-fanout: " + ", ".join(f"{t} in {n} themes" for t, n in over))

    redirects = {}
    if args.redirects:
        redirects = json.load(open(args.redirects, encoding="utf-8"))
        for src, dst in redirects.items():
            row = live.get(src)
            if row is None:
                sys.exit(f"redirect source not in the taxonomy: {src}")
            if dst not in live:
                sys.exit(f"redirect target not in the taxonomy: {dst} (from {src})")
            if row.get("members"):
                sys.exit(f"refusing to redirect {src}: it still has {len(row['members'])} members — "
                         f"move or drop them first, a redirect discards the row")
            print(f"REDIRECT {src} -> {dst}: the source exposure is removed and its URL folded in; "
                  f"this cannot be undone by the rollback payload")

    payload = {"sectors": sectors, "redirects": redirects, "full": False,
               "entry": args.entry, "rationale": args.rationale}
    if args.actor:
        payload["actor"] = args.actor
    json.dump(payload, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for eid in overridden:
        print(f"DESCRIPTION REPLACED {eid}: the stored description was judged wrong — "
              f"read the new one before publishing")
    by_type = collections.Counter(live[s["exposure_id"]]["exposure_type"] for s in sectors)
    print(f"exposures {len(sectors)} ({by_type.get('theme', 0)} themes, {by_type.get('industry', 0)} industries)  members {sum(len(s['members']) for s in sectors)} "
          f"(kept {kept}, added {added}, dropped {dropped})  "
          f"descriptions filled {len(filled)}, replaced {len(overridden)}")
    print(f"wrote {args.out} — review the diff returned by /api/admin/taxonomy/bulk before publishing")


if __name__ == "__main__":
    main()
