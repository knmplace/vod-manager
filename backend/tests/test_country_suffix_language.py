import vod_db
import vod_importer


def test_country_suffixes_are_classified_for_language_filter():
    assert vod_db._source_language("#BringBackAlice (PL)") == "PL"
    assert vod_db._source_language("1899 (2022) (DE)") == "DE"
    assert vod_db._source_language("Alba (2021) (ES)") == "ES"
    assert vod_db._source_language("A show (2024) (US)") == "EN"


def test_country_suffix_language_codes_respect_explicit_import_exclusions():
    lang = {"exclude_prefixes": ["PL", "DE"], "exclude_non_latin": False}
    assert vod_importer._should_auto_archive(
        "#BringBackAlice (PL)", lang=lang, raw_name="#BringBackAlice (PL)"
    )
    assert vod_importer._should_auto_archive(
        "1899 (2022) (DE)", lang=lang, raw_name="1899 (2022) (DE)"
    )
    assert not vod_importer._should_auto_archive(
        "Alba (2021) (ES)", lang=lang, raw_name="Alba (2021) (ES)"
    )


def test_gb_and_uk_prefix_tags_are_treated_as_english():
    # KNM: 2026-10-27 -- British titles play as EN; the GB/UK tag is display-only.
    assert vod_db._source_language("GB| Line of Duty") == "EN"
    assert vod_db._source_language("UK| Line of Duty") == "EN"
    assert vod_db._source_language("Line of Duty", "Series British [GB]") == "EN"
    assert vod_db._source_language("FR| Lupin") == "FR"
