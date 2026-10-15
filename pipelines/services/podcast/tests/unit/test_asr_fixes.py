"""Fixed ASR homophones are corrected in every transcript field, Simplified input included."""

from src.service.speech_to_text import convert_json_to_traditional_chinese


def test_show_name_homophone_is_fixed_in_text_and_sentences():
    out = convert_json_to_traditional_chinese(
        {
            "text": "歡迎收聽漫報",
            "sentences": [{"content": "这里是漫报的节目", "start": 0.0}],
        }
    )

    assert out["text"] == "歡迎收聽曼報"
    assert out["sentences"][0]["content"] == "這裡是曼報的節目"
    assert out["sentences"][0]["start"] == 0.0
