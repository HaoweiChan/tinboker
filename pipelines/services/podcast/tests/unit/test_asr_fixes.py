"""Per-show ASR fixes rewrite that show's mishearings and leave every other show alone."""

from src.service.speech_to_text import apply_show_asr_fixes


def test_show_name_and_host_are_fixed_for_their_own_show():
    text = "我是燕麗 歡迎收看超前部署"
    assert apply_show_asr_fixes("鈔錢部署｜盧燕俐", text) == "我是燕俐 歡迎收看鈔錢部署"
    assert apply_show_asr_fixes("曼報", "歡迎收聽漫報") == "歡迎收聽曼報"


def test_the_same_phrase_is_untouched_on_another_show():
    # 超前部署 is an ordinary idiom everywhere else.
    assert apply_show_asr_fixes("Gooaye 股癌", "法人已經超前部署") == "法人已經超前部署"
