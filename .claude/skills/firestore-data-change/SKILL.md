---
name: firestore-data-change
description: Use when the user wants to add, modify, or read Firestore data, change a field on episodes/tickers/ticker_insights/trending_tickers, or coordinate a cross-repo data-contract change with the tinboker-agents team.
---

Read `docs/workflows/firestore-data-change.md` and follow the procedure. The canonical schema and ownership matrix is in `docs/firestore-contract.md` — consult it before proposing any change. Enforce the "no new Firestore-direct read paths" rule and route new reads through the existing API or the planned HTTP API rather than introducing a new direct-read shim.
