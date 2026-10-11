"""Follow-up to beads-974: provider-level category/uncategorized exclusion
(providers.import_exclude_categories / import_exclude_uncategorized) and the
global language-exclusion rule (config.get_import_language_exclusion) used to
only mark an excluded item auto_archive=True -- it was still fully imported
and stored, just hidden from review queues (vod_db.bulk_set_review_excluded's
"still fully browsable/playable/categorizable" archive). User direction
(2026-09-10, referencing Dispatcharr's VOD-group "unchecked = not imported"
setting): excluded content should never be stored at all, mirroring how a
real exclusion is meant to work -- "I don't want this content in my library",
not "store it but hide it".

_should_auto_archive is renamed _should_auto_archive (same logic,
name now matches its actual role: a caller-side skip decision, not a
post-import archive flag) and is used by every importer (XC/vod_importer.py,
Plex, Emby) to filter items out of movie_items/series_items BEFORE calling
bulk_import_movies/bulk_import_series, instead of tagging them for archive
after the fact.

2026-10-11 follow-up: Import Language Exclusion and Enabled Playback Languages
are independent controls. This import-time gate reads the explicit
exclude_prefixes list; playback eligibility is enforced separately for stored
sources. exclude_non_latin and category exclusion remain part of this same
future-ingestion gate."""

import vod_importer


def test_excluded_category_returns_true():
    assert vod_importer._should_auto_archive(
        "Some Movie", "Foreign Films", ["Foreign Films"], False, {"exclude_prefixes": [], "exclude_non_latin": False},
    ) is True


def test_non_excluded_category_returns_false():
    assert vod_importer._should_auto_archive(
        "Some Movie", "Action Movies", ["Foreign Films"], False, {"exclude_prefixes": [], "exclude_non_latin": False},
    ) is False


def test_uncategorized_excluded_when_flag_set():
    assert vod_importer._should_auto_archive(
        "Some Movie", None, [], True, {"exclude_prefixes": [], "exclude_non_latin": False},
    ) is True


def test_uncategorized_not_excluded_when_flag_unset():
    assert vod_importer._should_auto_archive(
        "Some Movie", None, [], False, {"exclude_prefixes": [], "exclude_non_latin": False},
    ) is False


def test_explicit_import_exclusion_wins_even_when_playback_is_enabled():
    assert vod_importer._should_auto_archive(
        "GR - Some Movie", None, [], False,
        {"exclude_prefixes": ["GR"], "enabled_languages": ["EN", "GR"], "exclude_non_latin": False},
    ) is True


def test_language_not_import_excluded_is_allowed_even_when_playback_is_disabled():
    assert vod_importer._should_auto_archive(
        "GR - Some Movie", None, [], False,
        {"exclude_prefixes": [], "enabled_languages": ["EN"], "exclude_non_latin": False},
    ) is False


def test_untagged_name_is_excluded_when_en_is_explicitly_import_excluded():
    assert vod_importer._should_auto_archive(
        "Some Movie", None, [], False, {"exclude_prefixes": ["EN"], "exclude_non_latin": False},
    ) is True


def test_untagged_name_is_allowed_when_en_is_not_import_excluded():
    assert vod_importer._should_auto_archive(
        "Some Movie", None, [], False, {"exclude_prefixes": ["GR"], "exclude_non_latin": False},
    ) is False


def test_any_recognized_code_can_be_explicitly_import_excluded():
    assert vod_importer._should_auto_archive(
        "IR - Some Movie", None, [], False, {"exclude_prefixes": ["ir"], "exclude_non_latin": False},
    ) is True


def test_current_lang_settings_uses_import_policy_not_playback_policy(monkeypatch):
    monkeypatch.setattr(
        vod_importer.config,
        "get_import_language_exclusion",
        lambda: {"exclude_prefixes": [" es ", "gr"], "exclude_non_latin": True},
    )
    monkeypatch.setattr(vod_importer.config, "get_enabled_languages", lambda: ["EN", "ES"])

    assert vod_importer._current_lang_settings() == {
        "exclude_prefixes": ["ES", "GR"],
        "exclude_non_latin": True,
    }
