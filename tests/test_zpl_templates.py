"""Tests for modules/zpl_templates.py"""
import pytest

import config
import modules.zpl_templates as tmpl_mod


SAMPLE_ZPL = "^XA\n^FO40,30^A0N,28,28^FD{nombre}^FS\n^FO40,65^BY2^BCN,80,Y,N,N^FD{codigo}^FS\n^XZ\n"


@pytest.fixture(autouse=True)
def tmp_templates_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TEMPLATES_DIR", str(tmp_path))
    monkeypatch.setattr(tmpl_mod, "TEMPLATES_DIR", str(tmp_path))
    yield tmp_path


class TestTemplateCRUD:
    def test_list_empty(self):
        assert tmpl_mod.list_templates() == []

    def test_save_and_list(self):
        tmpl_mod.save_template("t1", SAMPLE_ZPL)
        assert tmpl_mod.list_templates() == ["t1"]

    def test_get_existing(self):
        tmpl_mod.save_template("t2", SAMPLE_ZPL)
        assert tmpl_mod.get_template("t2") == SAMPLE_ZPL

    def test_get_nonexistent(self):
        assert tmpl_mod.get_template("ghost") is None

    def test_delete_existing(self):
        tmpl_mod.save_template("del_me", SAMPLE_ZPL)
        assert tmpl_mod.delete_template("del_me") is True
        assert tmpl_mod.get_template("del_me") is None

    def test_delete_nonexistent(self):
        assert tmpl_mod.delete_template("ghost") is False

    def test_list_sorted(self):
        for name in ("zz", "aa", "mm"):
            tmpl_mod.save_template(name, "^XA^XZ")
        assert tmpl_mod.list_templates() == ["aa", "mm", "zz"]

    def test_unsafe_name_raises(self):
        with pytest.raises(ValueError):
            tmpl_mod.save_template("../../etc/passwd", "evil")

    def test_save_overwrites(self):
        tmpl_mod.save_template("overwrite", "old content")
        tmpl_mod.save_template("overwrite", "new content")
        assert tmpl_mod.get_template("overwrite") == "new content"


class TestExtractVariablesIntegration:
    def test_variables_from_saved_template(self):
        tmpl_mod.save_template("vars", SAMPLE_ZPL)
        content = tmpl_mod.get_template("vars")
        from modules.printer import extract_variables
        assert extract_variables(content) == ["codigo", "nombre"]
