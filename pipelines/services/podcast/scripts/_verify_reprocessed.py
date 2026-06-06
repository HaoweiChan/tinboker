"""Verify the 55 reprocessed episodes are now real, format-compliant summaries."""
from __future__ import annotations

import os
import re
import statistics

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud import storage

DB_ID = os.getenv("FIRESTORE_DATABASE_ID", "graphfolio-db")
PLACEHOLDER_SIGS = ("This is a placeholder summary", "Placeholder content", "This is placeholder content")

IDS = [
    "TheDisciplinedInvestor_7cc77d87faf82fdb", "ExchangesatGoldmanSachs_0b732b473d8c1f75",
    "CNBCsFastMoney_87a8165573b4ac78", "MotleyFoolMoney_8b99ebb8b7f6486f",
    "TheLongView_c60cc9ac78af61fe", "CNBCsFastMoney_9409f2797ca7f47d",
    "MotleyFoolMoney_0fe082673348cdfe", "CNBCsFastMoney_4b2b1f853da6895d",
    "BloombergMastersinBusinessPodc_2f0f826c395baceb", "InsidetheStrategyRoom_7445ae9897ceef44",
    "BloombergMastersinBusinessPodc_67210436f8a70afa", "CapitalAllocators_3629e81ffe89a948",
    "MotleyFoolMoney_f88e55adc67f53c6", "TheDisciplinedInvestor_ce7b6b9cff2e814f",
    "CNBCsFastMoney_4bb6c7e20a3074e5", "ExchangesatGoldmanSachs_5a3c066971fa21a6",
    "TheLongView_82375162a4e5dd36", "f595f5ab_df9d2e650ddebb2d",
    "e55a9f33_3ae991448b8477b8", "Gooaye_e3ed7c7216be0fe3",
    "MotleyFoolMoney_a2fd15b8f12ef59f", "MotleyFoolMoney_ac448377a9b8bc33",
    "547e2c56_8ae1a40c036960ae", "547e2c56_0d49081b7221ee8e",
    "547e2c56_b060e02a9756f9aa", "87a8b530_67463afba943c242",
    "87a8b530_865d05127a30207b", "Gooaye_735bc5f21b4fef8f",
    "547e2c56_1e367a74c6188af1", "547e2c56_4cc32959d8b9bc1c",
    "547e2c56_53bd316c8eedce02", "547e2c56_cd30ca6f60cbf46e",
    "87a8b530_bbf6c27dc6891e1b", "Gooaye_189fc28b1d9ac672",
    "Gooaye_b5ad26d35ab7fe8b", "547e2c56_28f55b19580b21e6",
    "547e2c56_6facf9e28ad7bde6", "547e2c56_adabad87a7d26a37",
    "547e2c56_c91e15588e7f9517", "547e2c56_03966ac0edb46ccc",
    "547e2c56_7f4d9f3061398bc5", "Gooaye_6f16978258c795bf",
    "547e2c56_12e2ac77b2edd631", "547e2c56_2a077260497a90fa",
    "Gooaye_f36a057134691ff0", "547e2c56_91be8225942b308d",
    "547e2c56_e94b42700e9006ad", "Gooaye_1969c2e3f0407a3e",
    "547e2c56_24636b40e9ba3f09", "547e2c56_73135ab21be5e46e",
    "87a8b530_c588d6a5bce96495", "87a8b530_ba4557e2f6254af1",
    "87a8b530_e0f6e0299c5a49a2", "Gooaye_710a596d04da6f15",
    "TheTechMAPodcast_0dc73f3fd7a90143",
]

cred = credentials.Certificate(os.environ["GOOGLE_APPLICATION_CREDENTIALS"])
try:
    firebase_admin.initialize_app(cred)
except ValueError:
    pass
db = firestore.client(database_id=DB_ID)
gcs = storage.Client()


def fetch(gs):
    b, _, k = gs[5:].partition("/")
    return gcs.bucket(b).blob(k).download_as_text()


bad = []
chars_list = []
double_h = []
for eid in IDS:
    d = db.collection("episodes").document(eid).get().to_dict() or {}
    gs = d.get("summary_url")
    md = fetch(gs) if gs else ""
    is_ph = any(s in md[:600] for s in PLACEHOLDER_SIGS)
    chars = len(md.strip())
    dbl = len(re.findall(r"(?m)^## ## ", md))
    h2 = len(re.findall(r"(?m)^## ", md))
    tk = len(re.findall(r"#ticker:", md))
    tg = len(re.findall(r"#tag:", md))
    concl = "## 結論" in md
    chars_list.append(chars)
    if dbl:
        double_h.append((eid, dbl))
    ok = (not is_ph) and chars >= 1000 and h2 >= 2
    if not ok:
        bad.append((eid, "PLACEHOLDER" if is_ph else f"thin chars={chars} h2={h2}"))

print(f"Verified {len(IDS)} reprocessed episodes")
print(f"  still placeholder/thin : {len(bad)}")
print(f"  with double-## heading : {len(double_h)}")
print(f"  char count  min/median/max : {min(chars_list)}/{int(statistics.median(chars_list))}/{max(chars_list)}")
if bad:
    print("  PROBLEM episodes:")
    for eid, why in bad:
        print(f"    {eid}: {why}")
if double_h:
    print("  DOUBLE-## episodes:")
    for eid, n in double_h:
        print(f"    {eid}: {n}")
if not bad and not double_h:
    print("ALL CLEAN ✓ — real, format-compliant, no double-headings")
