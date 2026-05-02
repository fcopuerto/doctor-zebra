"""Tests for modules/profiles.py"""
import json
import os

import pytest

import config


@pytest.fixture(autouse=True)
def tmp_profiles_dir(tmp_path, monkeypatch):
    """Redirect PROFILES_DIR to a temp directory for each test."""
    monkeypatch.setattr(config, "PROFILES_DIR", str(tmp_path))
    # Also patch the module-level variable inside profiles.py
    import modules.profiles as prof_mod
    monkeypatch.setattr(prof_mod, "PROFILES_DIR", str(tmp_path), raising=False)
    # Re-assign the constant used by _path()
    original_profiles_dir = prof_mod.profiles.__module__ if hasattr(prof_mod, '__module__') else None
    yield tmp_path


@pytest.fixture
def sample_profile():
    return {
        "name": "Test Profile",
        "printer": {"host": "10.0.0.1", "port": 9100},
        "template": "test_tmpl",
        "fields": [],
    }


# ---- We need to reload modules with patched config ----
# Easier: use the module functions directly but override the path helper.

import modules.profiles as profiles_mod


class TestProfileCRUD:
    def test_list_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(profiles_mod, "PROFILES_DIR", str(tmp_path))
        assert profiles_mod.list_profiles() == []

    def test_save_and_list(self, tmp_path, monkeypatch, sample_profile):
        monkeypatch.setattr(profiles_mod, "PROFILES_DIR", str(tmp_path))
        profiles_mod.save_profile("test", sample_profile)
        assert profiles_mod.list_profiles() == ["test"]

    def test_get_existing(self, tmp_path, monkeypatch, sample_profile):
        monkeypatch.setattr(profiles_mod, "PROFILES_DIR", str(tmp_path))
        profiles_mod.save_profile("myprofile", sample_profile)
        loaded = profiles_mod.get_profile("myprofile")
        assert loaded["printer"]["host"] == "10.0.0.1"

    def test_get_nonexistent(self, tmp_path, monkeypatch):
        monkeypatch.setattr(profiles_mod, "PROFILES_DIR", str(tmp_path))
        assert profiles_mod.get_profile("ghost") is None

    def test_delete_existing(self, tmp_path, monkeypatch, sample_profile):
        monkeypatch.setattr(profiles_mod, "PROFILES_DIR", str(tmp_path))
        profiles_mod.save_profile("todelete", sample_profile)
        assert profiles_mod.delete_profile("todelete") is True
        assert profiles_mod.get_profile("todelete") is None

    def test_delete_nonexistent(self, tmp_path, monkeypatch):
        monkeypatch.setattr(profiles_mod, "PROFILES_DIR", str(tmp_path))
        assert profiles_mod.delete_profile("ghost") is False

    def test_list_sorted(self, tmp_path, monkeypatch, sample_profile):
        monkeypatch.setattr(profiles_mod, "PROFILES_DIR", str(tmp_path))
        for name in ("z_profile", "a_profile", "m_profile"):
            profiles_mod.save_profile(name, sample_profile)
        assert profiles_mod.list_profiles() == ["a_profile", "m_profile", "z_profile"]

    def test_unsafe_name_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(profiles_mod, "PROFILES_DIR", str(tmp_path))
        with pytest.raises(ValueError):
            profiles_mod.save_profile("../evil", {})

    def test_unsafe_name_with_slash_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(profiles_mod, "PROFILES_DIR", str(tmp_path))
        with pytest.raises(ValueError):
            profiles_mod.get_profile("foo/bar")

    def test_json_roundtrip(self, tmp_path, monkeypatch, sample_profile):
        monkeypatch.setattr(profiles_mod, "PROFILES_DIR", str(tmp_path))
        profiles_mod.save_profile("rt", sample_profile)
        loaded = profiles_mod.get_profile("rt")
        assert loaded == sample_profile
