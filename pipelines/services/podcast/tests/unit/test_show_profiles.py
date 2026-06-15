"""Show-profile resolution: default fallback + per-show policy merge."""
from src.podcast.content_builder.profiles import load_profile

_POLICY_KEYS = {"sponsor", "intro", "outro", "chitchat", "analysis", "guest", "qa", "unknown"}


def test_unknown_show_falls_back_to_default():
    prof = load_profile("Some Podcast That Has No Profile")
    assert prof["structure_hint"] == ""
    assert _POLICY_KEYS.issubset(prof["policy"].keys())
    assert prof["policy"]["sponsor"] == "drop"
    assert prof["policy"]["analysis"] == "keep"
    assert prof["policy"]["qa"] == "substantive_only"


def test_none_source_returns_default():
    assert load_profile(None)["policy"] == load_profile("nonexistent")["policy"]


def test_gooaye_has_structure_hint_and_inherits_default_policy():
    prof = load_profile("Gooaye 股癌")
    assert prof["structure_hint"]  # non-empty prior
    assert "Q&A" in prof["structure_hint"] or "業配" in prof["structure_hint"]
    # Gooaye overrides nothing in policy -> equals the default policy.
    assert prof["policy"] == load_profile(None)["policy"]


def test_policy_is_a_fresh_dict_not_shared():
    """Mutating one resolved policy must not leak into the cached default."""
    a = load_profile("Gooaye 股癌")
    a["policy"]["analysis"] = "drop"
    assert load_profile("Gooaye 股癌")["policy"]["analysis"] == "keep"
