"""Integration tests for the Flask app routes."""
import json

import pytest

import config


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    """Redirect all data dirs to temp paths so tests are fully isolated."""
    profiles_dir = tmp_path / "profiles"
    templates_dir = tmp_path / "zpl_templates"
    profiles_dir.mkdir()
    templates_dir.mkdir()
    db_path = str(tmp_path / "cache.db")

    monkeypatch.setattr(config, "PROFILES_DIR", str(profiles_dir))
    monkeypatch.setattr(config, "TEMPLATES_DIR", str(templates_dir))
    monkeypatch.setattr(config, "CACHE_DB", db_path)

    import modules.profiles as pm
    import modules.zpl_templates as tm
    import modules.cache as cm
    monkeypatch.setattr(pm, "PROFILES_DIR", str(profiles_dir))
    monkeypatch.setattr(tm, "TEMPLATES_DIR", str(templates_dir))
    monkeypatch.setattr(cm, "CACHE_DB", db_path)

    yield


@pytest.fixture
def client(isolated_data):
    from app import app
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# Index / print
# ---------------------------------------------------------------------------

class TestIndex:
    def test_index_no_profiles(self, client):
        rv = client.get("/")
        assert rv.status_code == 200
        assert b"No hay perfiles" in rv.data

    def test_index_with_profile(self, client):
        import modules.profiles as pm
        import modules.zpl_templates as tm
        tm.save_template("t1", "^XA^FD{nombre}^FS^XZ")
        pm.save_profile("p1", {
            "name": "P1", "printer": {"host": "1.2.3.4", "port": 9100},
            "template": "t1", "fields": []
        })
        rv = client.get("/?profile=p1")
        assert rv.status_code == 200
        assert b"p1" in rv.data

    def test_print_missing_profile(self, client):
        rv = client.post("/print", data={"profile": "ghost", "copies": "1"})
        assert rv.status_code == 302  # redirects

    def test_print_missing_template(self, client):
        import modules.profiles as pm
        pm.save_profile("p2", {
            "name": "P2", "printer": {"host": "1.2.3.4", "port": 9100},
            "template": "nonexistent", "fields": []
        })
        rv = client.post("/print", data={"profile": "p2", "copies": "1"})
        assert rv.status_code == 302


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

class TestProfileRoutes:
    def test_list_empty(self, client):
        rv = client.get("/profiles")
        assert rv.status_code == 200

    def test_create_profile(self, client):
        import modules.zpl_templates as tm
        tm.save_template("tt", "^XA^XZ")
        rv = client.post("/profiles/new", data={
            "name": "mypro",
            "display_name": "My Profile",
            "printer_host": "192.168.1.1",
            "printer_port": "9100",
            "template": "tt",
            "fields_json": "[]",
        })
        assert rv.status_code == 302
        import modules.profiles as pm
        assert pm.get_profile("mypro") is not None

    def test_delete_profile(self, client):
        import modules.profiles as pm
        pm.save_profile("delme", {"name": "x", "printer": {"host": "h", "port": 9100},
                                   "template": "", "fields": []})
        rv = client.post("/profiles/delme/delete")
        assert rv.status_code == 302
        assert pm.get_profile("delme") is None


# ---------------------------------------------------------------------------
# ZPL Templates
# ---------------------------------------------------------------------------

class TestTemplateRoutes:
    def test_list_empty(self, client):
        rv = client.get("/templates")
        assert rv.status_code == 200

    def test_create_template(self, client):
        rv = client.post("/templates/new", data={
            "name": "my_tmpl",
            "content": "^XA^FD{var}^FS^XZ",
        })
        assert rv.status_code == 302
        import modules.zpl_templates as tm
        assert tm.get_template("my_tmpl") is not None

    def test_delete_template(self, client):
        import modules.zpl_templates as tm
        tm.save_template("del_tmpl", "^XA^XZ")
        rv = client.post("/templates/del_tmpl/delete")
        assert rv.status_code == 302
        assert tm.get_template("del_tmpl") is None


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

class TestCacheRoutes:
    def test_list_empty(self, client):
        rv = client.get("/cache")
        assert rv.status_code == 200

    def test_create_lookup(self, client):
        rv = client.post("/cache/new", data={
            "action": "save",
            "name": "my_lookup",
            "source_url": "",
            "data_json": '[{"code":"001","name":"A"}]',
        })
        assert rv.status_code == 302
        import modules.cache as cm
        assert cm.get_lookup("my_lookup") is not None

    def test_delete_lookup(self, client):
        import modules.cache as cm
        cm.set_lookup("del_lk", [{"x": 1}])
        rv = client.post("/cache/del_lk/delete")
        assert rv.status_code == 302
        assert cm.get_lookup("del_lk") is None


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

class TestAPI:
    def test_lookup_search(self, client):
        import modules.cache as cm
        cm.set_lookup("prods", [
            {"code": "001", "name": "Alpha"},
            {"code": "002", "name": "Beta"},
        ])
        rv = client.get("/api/lookup/prods/search?q=Alpha")
        assert rv.status_code == 200
        data = json.loads(rv.data)
        assert len(data) == 1
        assert data[0]["code"] == "001"

    def test_template_variables(self, client):
        import modules.zpl_templates as tm
        tm.save_template("api_t", "^FD{foo}^FS^FD{bar}^FS")
        rv = client.get("/api/templates/api_t/variables")
        assert rv.status_code == 200
        assert json.loads(rv.data) == ["bar", "foo"]
