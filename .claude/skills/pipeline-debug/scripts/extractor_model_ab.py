"""Extractor-role-only A/B across OpenRouter models.

Replicates exactly what nodes/extractor.py sends for ONE chunk: the same
prompt yaml, temperature 0.1, max_tokens 8192, reasoning disabled, and the
first _CHUNK_SIZE sentences re-indexed 0-based (what _extract_chunked does).

No Firestore, no writes, no downstream roles — the point is to isolate the one
role that actually eats the transcript.
"""
import json, os, re, sys, time, urllib.request, urllib.error

CHUNK_SIZE = 800          # nodes/extractor.py _CHUNK_SIZE
MAX_TOKENS = 8192         # llm.py _MAX_TOKENS_MAP["extractor"]
TEMPERATURE = 0.1         # llm.py _TEMPERATURE_MAP["extractor"]
VOCAB = {"sponsor", "intro", "outro", "chitchat", "analysis", "guest", "qa", "unknown"}

MODELS = [
    "deepseek/deepseek-v4-pro",          # incumbent / baseline
    "deepseek/deepseek-v4-flash-0731",
    "qwen/qwen3.7-flash",
    "inclusionai/ling-3.0-flash",
    "z-ai/glm-4.7-flash",
]

PROMPTS = sys.argv[1]
TRANSCRIPT = sys.argv[2]
TITLE = sys.argv[3]
SOURCE = sys.argv[4]
OUT = sys.argv[5]

import yaml
p = yaml.safe_load(open(PROMPTS, encoding="utf-8"))
raw = json.load(open(TRANSCRIPT, encoding="utf-8"))["sentences"][:CHUNK_SIZE]
# _extract_chunked re-indexes each chunk to local 0-based positions
sentences = [{**s, "index": i} for i, s in enumerate(raw)]

user = p["user"].format(
    source=SOURCE,
    episode_title=TITLE,
    structure_hint="（無特定結構提示，依實際內容判斷）",
    sentences=json.dumps(sentences, ensure_ascii=False),
)
MESSAGES = [{"role": "system", "content": p["system"]}, {"role": "user", "content": user}]

# Simplified-only glyphs that would signal the model drifted out of Traditional
# Chinese. Deliberately excludes 台/群/才 — both scripts use those in TW (the skill
# warns the opencc diff is noisy), so these are unambiguous cases only.
SIMPLIFIED = set("这个国说时会对现发经产业务额买卖资讯际势规运动开关闭电脑网络币价")

PRICES = {}  # filled from the models API


def price(mid):
    if mid in PRICES:
        return PRICES[mid]
    return (0.0, 0.0)


def sanitize(t):
    t = t.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*\n?", "", t)
        t = re.sub(r"\n?```\s*$", "", t)
    return t


def call(model, disable_reasoning=True):
    body = {
        "model": model,
        "messages": MESSAGES,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS if disable_reasoning else MAX_TOKENS * 2,
    }
    if disable_reasoning:
        body["reasoning"] = {"enabled": False}
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"],
            "Content-Type": "application/json",
            "HTTP-Referer": "https://tinboker.com",
            "X-Title": "TinBoker extractor A/B",
        },
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=600) as r:
        payload = json.load(r)
    return payload, time.time() - t0


def score(model):
    row = {"model": model}
    try:
        payload, secs = call(model)
    except urllib.error.HTTPError as e:
        err = e.read().decode()[:300]
        if re.search(r"reasoning is mandatory", err, re.I):
            try:
                payload, secs = call(model, disable_reasoning=False)
                row["note"] = "reasoning forced on (2x max_tokens)"
            except Exception as e2:
                return {**row, "error": f"{type(e2).__name__}: {str(e2)[:160]}"}
        else:
            return {**row, "error": f"HTTP {e.code}: {err[:160]}"}
    except Exception as e:
        return {**row, "error": f"{type(e).__name__}: {str(e)[:160]}"}

    row["runtime_s"] = round(secs, 1)
    u = payload.get("usage") or {}
    pt, ct = u.get("prompt_tokens", 0), u.get("completion_tokens", 0)
    row["prompt_tokens"], row["completion_tokens"] = pt, ct
    pp, cp = price(model)
    row["chunk_cost_usd"] = round(pt / 1e6 * pp + ct / 1e6 * cp, 5)
    row["finish_reason"] = (payload["choices"][0].get("finish_reason") if payload.get("choices") else None)

    text = sanitize(payload["choices"][0]["message"]["content"] or "")
    row["reply_chars"] = len(text)
    try:
        data = json.loads(text)
    except Exception as e:
        row["json_ok"] = False
        row["json_error"] = str(e)[:120]
        row["raw_tail"] = text[-160:]
        return row
    row["json_ok"] = True

    events = data if isinstance(data, list) else (data.get("events") or data.get("topics") or [])
    if not isinstance(events, list):
        row["json_ok"] = False
        row["json_error"] = f"unexpected shape: {list(data)[:6]}"
        return row
    row["n_events"] = len(events)

    covered, bad_range, bad_type, topics = set(), 0, [], []
    for ev in events:
        if not isinstance(ev, dict):
            bad_range += 1
            continue
        s, e = ev.get("start_index"), ev.get("end_index")
        if isinstance(s, int) and isinstance(e, int) and 0 <= s <= e < CHUNK_SIZE:
            covered.update(range(s, e + 1))
        else:
            bad_range += 1
        st = ev.get("segment_type")
        if st not in VOCAB:
            bad_type.append(st)
        t = ev.get("section_topic") or ""
        topics.append(t)

    row["coverage_pct"] = round(len(covered) / CHUNK_SIZE * 100, 1)
    row["uncovered_sentences"] = CHUNK_SIZE - len(covered)
    row["bad_index_ranges"] = bad_range
    row["off_vocab_segment_types"] = sorted({str(x) for x in bad_type})
    joined = "".join(topics)
    row["simplified_chars"] = sorted(set(joined) & SIMPLIFIED)
    row["types_used"] = sorted({ev.get("segment_type") for ev in events if isinstance(ev, dict)}, key=str)
    row["sample_topics"] = topics[:6]
    return row


def main():
    # pull real prices so chunk_cost_usd is not guesswork
    try:
        with urllib.request.urlopen("https://openrouter.ai/api/v1/models", timeout=60) as r:
            for m in json.load(r)["data"]:
                pr = m.get("pricing") or {}
                try:
                    PRICES[m["id"]] = (float(pr.get("prompt", 0)) * 1e6, float(pr.get("completion", 0)) * 1e6)
                except (TypeError, ValueError):
                    pass
    except Exception as e:
        print(f"[warn] price fetch failed ({e}); costs will read 0", file=sys.stderr)

    results = []
    for m in MODELS:
        print(f"→ {m} …", file=sys.stderr, flush=True)
        r = score(m)
        results.append(r)
        print(f"   {json.dumps({k: v for k, v in r.items() if k != 'sample_topics'}, ensure_ascii=False)[:220]}",
              file=sys.stderr, flush=True)
        json.dump(results, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nwrote {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
