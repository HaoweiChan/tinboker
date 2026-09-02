"""The proper-noun hint we hand Whisper before it transcribes.

Whisper has no idea that the two syllables it just heard are 欣興 (3037) and not the
ordinary word 新興, or that the Fed chair is Warsh and not Walsh — and it never will,
because nothing in the audio distinguishes them. Its ``prompt`` field exists for
exactly this: prior context that biases the decoder toward a known vocabulary.

Two sources, one list:

* **trending tickers** — what our own shows have been talking about for the last 30
  days, refreshed hourly platform-side. Self-maintaining and always current, which is
  the half nobody would keep up by hand.
* **:data:`RECURRING_TERMS`** — the names the ticker table structurally cannot supply:
  people, institutions, and the finance idioms the ASR keeps flattening into
  homophones. Short by design; edit it when a new name starts recurring.

The budget is the whole design constraint, and there are two of them. Groq rejects a
request whose prompt exceeds 896 UTF-8 bytes (measured against the live API — its 400
says "characters" but counts bytes, so ~290 CJK characters). Whisper itself then keeps
only the last ~224 tokens of whatever it is given, because the prompt models *preceding
speech* — so if anything is dropped it is dropped from the front. Hence the ordering
below: trending tickers lead, :data:`RECURRING_TERMS` trail, and truncation eats the
long tail of tickers rather than the name of the Fed chair.

So this is a hint about what is *likely*, never a dictionary — episodes will still
mention things that are not on the list, and the downstream correction pass
(``content_builder.name_normalizer``) is what catches those.

**Off by default** (``STT_VOCAB_PROMPT=1`` to enable), because measuring it on real
audio from three shows showed it pays for its wins with losses:

===================  ====================  ======================================
clip                 un-prompted           with a 14-term prompt
===================  ====================  ======================================
EP1173 @00:52        星星電子 (wrong)       欣興電子 (right)
EP1172 @17:44        新興…機油生 (wrong)    欣興 (right) …激優生 (still wrong)
EP1173 @16:48        掉單 (right)          吊單 (**newly wrong**), 建策→建設
EP1173 @11:40        164 chars of speech   12 chars of hallucinated song credit
===================  ====================  ======================================

The last row is why :meth:`GroqService._transcribe_call` exists. The third is why this
is opt-in: biasing the decoder toward a word list drags neighbouring ordinary words
toward those names too, and nothing downstream can tell that 吊單 was once correct.
The name_normalizer pass fixes the same reported errors without touching the audio path.
"""

from __future__ import annotations

import os
from functools import lru_cache

from shared.platform_client import fetch_trending_tickers
from shared.tickers import lookup_ticker, prime_tickers

# Sized to Whisper's ~224-token prompt window rather than Groq's 896-byte request cap:
# staying near the window means nothing is silently truncated. CJK runs close to one
# token per character in Whisper's multilingual tokenizer.
MAX_PROMPT_CHARS = 200

# Groq's request validator, in UTF-8 bytes. Never the binding constraint at the char
# budget above (200 CJK chars ≈ 600 bytes) — this is the guard that keeps a future edit
# to RECURRING_TERMS from turning every transcription into a 400.
MAX_PROMPT_BYTES = 896

# Long labels ("Space Exploration Technologies") buy one name for the price of ten.
# Anything past this is dropped in favour of more short names.
_MAX_TERM_CHARS = 6

# How many trending rows to consider. Most get dropped by the budget; asking for more
# than we can use costs nothing and keeps the short-name filter well fed.
_TRENDING_LIMIT = 120

# ponytail: a module constant, not per-show config. These are people and idioms every
# TW macro show says, so one list serves all of them; a per-show file would be a second
# mechanism maintained no better than this one. Add a name when you see it mistranscribed.
RECURRING_TERMS: tuple[str, ...] = (
    # Fed / Treasury / policy figures — the ASR's most expensive misses, since a wrong
    # name reads as not knowing who runs the central bank.
    "華許", "貝森特", "鮑爾", "川普", "黃仁勳", "聯準會", "財政部",
    # Finance idioms the ASR flattens into homophones (機油生←績優生 shipped on a card).
    "績優生", "本益比", "毛利率", "殖利率", "法說會", "台股", "美債",
)


def _short(term: str) -> bool:
    return bool(term) and len(term) <= _MAX_TERM_CHARS


def _trending_names() -> list[str]:
    """zh-TW display names for the currently-trending tickers, most-mentioned first."""
    rows = fetch_trending_tickers(days=30, limit=_TRENDING_LIMIT) or []
    symbols = [str(r.get("ticker") or "").strip() for r in rows]
    symbols = [s for s in symbols if s]
    if not symbols:
        return []
    prime_tickers(symbols)
    names = []
    for symbol in symbols:
        info = lookup_ticker(symbol)
        name = info.name if info and info.name else symbol
        if _short(name):
            names.append(name)
    return names


def compose(terms: list[str], *, budget: int = MAX_PROMPT_CHARS) -> str:
    """Join ``terms`` into a 、-separated list, de-duplicated, stopping at ``budget``."""
    out: list[str] = []
    used = 0
    for term in terms:
        term = (term or "").strip()
        if not term or term in out:
            continue
        cost = len(term) + (1 if out else 0)  # the joining 、
        if used + cost > budget:
            continue  # keep scanning — a shorter later term may still fit
        out.append(term)
        used += cost
    return "、".join(out)


def _fit_bytes(prompt: str, limit: int = MAX_PROMPT_BYTES) -> str:
    """Drop leading terms until the prompt fits ``limit`` UTF-8 bytes.

    Leading, not trailing: the tail is the part Whisper keeps and the part we care about.
    """
    terms = prompt.split("、")
    while terms and len("、".join(terms).encode("utf-8")) > limit:
        terms.pop(0)
    return "、".join(terms)


def enabled() -> bool:
    """Whether to send a vocabulary hint at all. Off unless ``STT_VOCAB_PROMPT`` is set."""
    return os.getenv("STT_VOCAB_PROMPT", "").strip().lower() in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def build_stt_prompt() -> str:
    """The Whisper prompt for this run — trending tickers, then the recurring names.

    Cached for the process: one platform round trip per run, not per episode. Returns
    ``""`` when disabled or when the platform is unreachable, which the caller passes
    through as "no prompt" rather than sending an empty string.
    """
    if not enabled():
        return ""
    # Reserve the recurring names first so the budget can never squeeze them out, then
    # spend what is left on trending tickers — but emit the tickers *first*, so that if
    # Whisper truncates, it truncates them and not the names.
    tail = compose(list(RECURRING_TERMS))
    head = compose(_trending_names(), budget=MAX_PROMPT_CHARS - len(tail) - 1)
    prompt = _fit_bytes("、".join(p for p in (head, tail) if p))
    if prompt:
        print(f"  ✎ STT vocabulary hint: {len(prompt)} chars, {prompt.count('、') + 1} terms")
    return prompt
