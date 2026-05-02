"""Tests for modules/cache.py"""
import time

import pytest

import config
import modules.cache as cache_mod


@pytest.fixture(autouse=True)
def tmp_cache_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test_cache.db")
    monkeypatch.setattr(config, "CACHE_DB", db_path)
    monkeypatch.setattr(cache_mod, "CACHE_DB", db_path)
    yield db_path


SAMPLE_DATA = [
    {"code": "001", "name": "Producto A", "price": "10.00"},
    {"code": "002", "name": "Producto B", "price": "20.00"},
    {"code": "003", "name": "Widget C", "price": "5.00"},
]


class TestCacheCRUD:
    def test_list_empty(self):
        assert cache_mod.list_lookups() == []

    def test_set_and_get(self):
        cache_mod.set_lookup("productos", SAMPLE_DATA)
        result = cache_mod.get_lookup("productos")
        assert result == SAMPLE_DATA

    def test_get_nonexistent(self):
        assert cache_mod.get_lookup("ghost") is None

    def test_list_returns_metadata(self):
        cache_mod.set_lookup("items", SAMPLE_DATA, source_url="http://example.com/items.json")
        listings = cache_mod.list_lookups()
        assert len(listings) == 1
        entry = listings[0]
        assert entry["name"] == "items"
        assert entry["count"] == 3
        assert entry["source_url"] == "http://example.com/items.json"
        assert entry["updated_at"] > 0

    def test_delete_existing(self):
        cache_mod.set_lookup("todelete", SAMPLE_DATA)
        assert cache_mod.delete_lookup("todelete") is True
        assert cache_mod.get_lookup("todelete") is None

    def test_delete_nonexistent(self):
        assert cache_mod.delete_lookup("ghost") is False

    def test_replace_on_second_set(self):
        cache_mod.set_lookup("rep", [{"v": 1}])
        cache_mod.set_lookup("rep", [{"v": 2}, {"v": 3}])
        assert len(cache_mod.get_lookup("rep")) == 2

    def test_source_url_preserved(self):
        url = "https://api.example.com/data.json"
        cache_mod.set_lookup("src", [{"a": 1}], source_url=url)
        listings = cache_mod.list_lookups()
        assert listings[0]["source_url"] == url

    def test_list_sorted_by_name(self):
        cache_mod.set_lookup("zzz", [])
        cache_mod.set_lookup("aaa", [])
        names = [lk["name"] for lk in cache_mod.list_lookups()]
        assert names == ["aaa", "zzz"]

    def test_non_list_data(self):
        """Should also accept a plain dict."""
        obj = {"key": "value"}
        cache_mod.set_lookup("dict_lookup", obj)
        assert cache_mod.get_lookup("dict_lookup") == obj


class TestSearchLookup:
    def setup_method(self):
        cache_mod.set_lookup("productos", SAMPLE_DATA)

    def test_search_by_name(self):
        results = cache_mod.search_lookup("productos", "Producto")
        assert len(results) == 2

    def test_search_case_insensitive(self):
        results = cache_mod.search_lookup("productos", "producto a")
        assert len(results) == 1
        assert results[0]["code"] == "001"

    def test_search_by_specific_field(self):
        results = cache_mod.search_lookup("productos", "001", fields=["code"])
        assert len(results) == 1

    def test_search_no_match(self):
        results = cache_mod.search_lookup("productos", "xyz_not_found")
        assert results == []

    def test_search_nonexistent_lookup(self):
        results = cache_mod.search_lookup("ghost", "anything")
        assert results == []

    def test_search_empty_query_returns_all_up_to_50(self):
        big = [{"code": str(i), "name": f"Item {i}"} for i in range(60)]
        cache_mod.set_lookup("big", big)
        results = cache_mod.search_lookup("big", "")
        # Empty query matches everything but cap at 50
        assert len(results) == 50

    def test_search_limit_50(self):
        big = [{"name": "match"} for _ in range(100)]
        cache_mod.set_lookup("bigmatch", big)
        results = cache_mod.search_lookup("bigmatch", "match")
        assert len(results) == 50


class TestRefreshLookup:
    def test_refresh_uses_requests(self, monkeypatch):
        """refresh_lookup should call requests.get and store the result."""
        import requests

        class FakeResp:
            def raise_for_status(self): pass
            def json(self): return [{"id": 1}]

        monkeypatch.setattr(requests, "get", lambda url, timeout: FakeResp())
        data = cache_mod.refresh_lookup("remote", "http://example.com/data.json")
        assert data == [{"id": 1}]
        assert cache_mod.get_lookup("remote") == [{"id": 1}]

    def test_refresh_raises_on_http_error(self, monkeypatch):
        import requests

        class FakeResp:
            def raise_for_status(self): raise requests.HTTPError("404")
            def json(self): return []

        monkeypatch.setattr(requests, "get", lambda url, timeout: FakeResp())
        with pytest.raises(requests.HTTPError):
            cache_mod.refresh_lookup("remote", "http://example.com/404")
