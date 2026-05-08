#!/usr/bin/env python3
"""Quick integration test for the LangGraph content pipeline."""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.secrets_bootstrap import bootstrap
bootstrap()

from content_builder import run_pipeline

test_sentences = [
    {"text": "大家好，歡迎收聽今天的財經節目", "start": 0, "end": 3000},
    {"text": "今天我們要來討論台積電最新的財報", "start": 3000, "end": 6000},
    {"text": "台積電第一季營收達到了兩千五百億台幣", "start": 6000, "end": 10000},
    {"text": "比去年同期成長了百分之三十五", "start": 10000, "end": 13000},
    {"text": "主要是受到AI晶片需求的帶動", "start": 13000, "end": 16000},
    {"text": "特別是CoWoS先進封裝的產能持續擴張", "start": 16000, "end": 20000},
    {"text": "目前台積電的本益比大約在二十五倍左右", "start": 20000, "end": 24000},
    {"text": "我個人認為以目前的成長速度來看還是偏低的", "start": 24000, "end": 28000},
    {"text": "接下來看看輝達的狀況", "start": 28000, "end": 31000},
    {"text": "輝達最新的H200晶片供不應求", "start": 31000, "end": 35000},
    {"text": "各大雲端廠商都在搶購", "start": 35000, "end": 38000},
    {"text": "我覺得輝達短期內還是會繼續走強", "start": 38000, "end": 42000},
    {"text": "但要注意AMD的MI300X也在搶市場", "start": 42000, "end": 46000},
    {"text": "最後提醒大家注意聯準會下週的利率決議", "start": 46000, "end": 50000},
    {"text": "目前市場預期維持不變，但要注意措辭的變化", "start": 50000, "end": 54000},
]

transcript = " ".join(s["text"] for s in test_sentences)

print("Running LangGraph content pipeline...")
print(f"  Transcript: {len(transcript)} chars, {len(test_sentences)} sentences")
print()
start = time.time()

result = run_pipeline(
    transcript=transcript,
    sentences=test_sentences,
    source="測試財經節目",
    episode_title="台積電與輝達 AI 晶片分析",
)

elapsed = time.time() - start
print(f"\nPipeline completed in {elapsed:.1f}s")
print("=" * 60)

md = result.get("markdown_report", "")
print(f"\n[markdown_report] ({len(md)} chars)")
print(md[:1000])
if len(md) > 1000:
    print(f"... ({len(md) - 1000} more chars)")

em = result.get("events_markdown", "")
print(f"\n[events_markdown] ({len(em)} chars)")
print(em[:500])

tr = result.get("ticker_recommendations")
print(f"\n[ticker_recommendations]")
if tr and isinstance(tr, dict):
    recs = tr.get("ticker_recommendations", [])
    print(f"  {len(recs)} tickers:")
    for r in recs:
        ticker = r.get("ticker", "?")
        sentiment = r.get("sentiment", "?")
        score = r.get("sentiment_score", 0)
        thesis = str(r.get("bluf_thesis", ""))[:80]
        print(f"    {ticker}: {sentiment} ({score}) - {thesis}")
else:
    print("  (none or invalid format)")

mm = result.get("marp_markdown", "")
print(f"\n[marp_markdown] ({len(mm)} chars)")
print(mm[:300] if mm else "(empty)")

tm = result.get("ticker_marp_markdown", "")
print(f"\n[ticker_marp_markdown] ({len(tm)} chars)")

print("\n" + "=" * 60)
print("ALL CHECKS PASSED" if md and em else "SOME OUTPUTS MISSING")
