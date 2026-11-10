"""PH (Philippines/Tagalog) provider prefix. "PH - Slam Dunk Tagalog Dubbed" was
read as untagged (-> EN) because PH was not a known dash/colon prefix code, so
it passed both the import-exclusion gate (even with PH excluded) and the EN
playback allowlist. Found live 2026-11-09.
"""

import vod_db
import vod_importer


def test_ph_dash_prefix_detected():
    assert vod_db._name_prefix_code("PH - Slam Dunk Tagalog Dubbed") == "PH"


def test_ph_colon_prefix_detected():
    assert vod_db._name_prefix_code("PH: Some Title") == "PH"


def test_ph_source_language_is_ph_not_en():
    assert vod_db._source_language("PH - Slam Dunk Tagalog Dubbed") == "PH"


def test_ph_prefix_is_stripped_for_display():
    assert vod_db._strip_one_lang_prefix("PH - Slam Dunk Tagalog Dubbed") == "Slam Dunk Tagalog Dubbed"


def test_ph_excluded_at_import_when_in_exclusion_list():
    lang = {"exclude_prefixes": {"PH"}, "exclude_non_latin": False, "known_language_codes": {"EN", "PH"}}
    assert vod_importer._should_auto_archive(
        "Slam Dunk Tagalog Dubbed", raw_name="PH - Slam Dunk Tagalog Dubbed", lang=lang,
    ) is True


def test_ph_not_excluded_when_not_in_exclusion_list():
    lang = {"exclude_prefixes": set(), "exclude_non_latin": False, "known_language_codes": {"EN", "PH"}}
    assert vod_importer._should_auto_archive(
        "Slam Dunk Tagalog Dubbed", raw_name="PH - Slam Dunk Tagalog Dubbed", lang=lang,
    ) is False
