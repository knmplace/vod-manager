"""archive_new_categories: a newly discovered category must stay excluded on
later imports, not only the run that first sees it. known_import_categories is
updated in that same run, so without persisting the category the next import
no longer treats it as new and imports its content as active."""

import asyncio

import vod_importer


def _fake_client(categories, streams):
    class FakeClient:
        def __init__(self, _provider):
            pass

        async def get_vod_categories(self):
            return [{"category_id": cid, "category_name": name} for cid, name in categories.items()]

        async def get_series_categories(self):
            return []

        async def get_vod_streams(self):
            return list(streams)

        async def get_series(self):
            return []

    return FakeClient


def _patch(monkeypatch, client_cls):
    monkeypatch.setattr(vod_importer, "XCProviderClient", client_cls)
    monkeypatch.setattr(vod_importer.vod_db, "get_active_rules_for_field", lambda *_: [])
    monkeypatch.setattr(vod_importer, "schedule_post_import_enrichment", lambda: False)


def test_new_category_stays_excluded_on_second_import(db, monkeypatch):
    provider_id = db.upsert_provider("Provider A", "http://a.invalid", "u", "p", provider_type="xc")
    db.set_provider_archive_new_categories(provider_id, True)

    _patch(monkeypatch, _fake_client({"1": "Movies"}, [
        {"stream_id": "m1", "name": "Known Movie (2020)", "category_id": "1"},
    ]))
    asyncio.run(vod_importer.import_provider_catalog(provider_id))
    assert db.get_movie_by_name_year("Known Movie", 2020) is not None

    _patch(monkeypatch, _fake_client({"1": "Movies", "2": "Brand New"}, [
        {"stream_id": "m1", "name": "Known Movie (2020)", "category_id": "1"},
        {"stream_id": "m2", "name": "Fresh Movie (2021)", "category_id": "2"},
    ]))
    asyncio.run(vod_importer.import_provider_catalog(provider_id))
    assert db.get_movie_by_name_year("Fresh Movie", 2021) is None

    asyncio.run(vod_importer.import_provider_catalog(provider_id))
    assert db.get_movie_by_name_year("Fresh Movie", 2021) is None
    assert "Brand New" in db.get_provider(provider_id)["import_exclude_categories"]


def test_first_import_does_not_exclude_every_category(db, monkeypatch):
    provider_id = db.upsert_provider("Provider A", "http://a.invalid", "u", "p", provider_type="xc")
    db.set_provider_archive_new_categories(provider_id, True)

    _patch(monkeypatch, _fake_client({"1": "Movies"}, [
        {"stream_id": "m1", "name": "Known Movie (2020)", "category_id": "1"},
    ]))
    asyncio.run(vod_importer.import_provider_catalog(provider_id))

    assert db.get_movie_by_name_year("Known Movie", 2020) is not None
    assert not db.get_provider(provider_id)["import_exclude_categories"]
