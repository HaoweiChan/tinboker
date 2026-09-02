"""Guards on the proper-noun pass: what it accepts, and what it must not touch."""

from src.podcast.content_builder.name_normalizer import (
    MAX_CORRECTIONS,
    apply_corrections,
    collect_entities,
    vet_corrections,
)

CORPUS = "新興電子遭搜索，投信眼中的機油生。Walsh 放鷹。新興市場資金流出。"


def test_accepts_equal_length_homophone_swaps():
    got = vet_corrections(
        [
            {"wrong": "新興", "right": "欣興"},
            {"wrong": "機油生", "right": "績優生"},
            {"wrong": "Walsh", "right": "Warsh"},
        ],
        CORPUS,
    )
    assert got == {"新興": "欣興", "機油生": "績優生", "Walsh": "Warsh"}


def test_rejects_rewrites_and_inventions():
    got = vet_corrections(
        [
            {"wrong": "新興", "right": "欣興電子"},        # length change = a rewrite
            {"wrong": "台積電", "right": "台機電"},        # never appears in the corpus
            {"wrong": "南電", "right": ""},                # deletion
            {"wrong": "機油生", "right": "機油生"},         # no-op
            {"wrong": "#tag:AI", "right": "#tag:Al"},      # markup, not a name
            "新興",                                        # malformed row
        ],
        CORPUS,
    )
    assert got == {}


def test_caps_the_map():
    pool = "天地玄黃宇宙洪荒日月盈昃辰宿列張寒來暑往秋收冬藏閏餘成歲律呂調陽雲騰致雨"
    proposals = [{"wrong": pool[i] + "興", "right": pool[i] + "業"} for i in range(30)]
    corpus = "".join(p["wrong"] for p in proposals)
    assert len(vet_corrections(proposals, corpus)) == MAX_CORRECTIONS


def test_applies_to_nested_prose_but_not_identifiers():
    cards = [
        {
            "kind": "theme",
            "title": "新興搜索案",
            "bullets": ["新興盤中跌停", "Walsh 放鷹"],
            "image_url": "https://cdn/新興/0.png",
            "start_time_ms": 1200,
        }
    ]
    out = apply_corrections(cards, {"新興": "欣興", "Walsh": "Warsh"})
    assert out[0]["title"] == "欣興搜索案"
    assert out[0]["bullets"] == ["欣興盤中跌停", "Warsh 放鷹"]
    assert out[0]["image_url"] == "https://cdn/新興/0.png"  # identifier left intact
    assert out[0]["start_time_ms"] == 1200


def test_empty_map_is_a_no_op():
    payload = {"post": "新興", "comments": [{"text": "新興"}]}
    assert apply_corrections(payload, {}) == payload


def test_entities_dedupe_and_keep_order():
    assert collect_entities(
        episode_title="鷹派Warsh，戳破AI泡沫？",
        source="財女珍妮",
        ticker_names=["欣興", "", "欣興", "輝達"],
    ) == ["財女珍妮", "鷹派Warsh，戳破AI泡沫？", "欣興", "輝達"]
