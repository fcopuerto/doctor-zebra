"""Tests for modules/printer.py"""
import pytest
from modules.printer import extract_variables, render_template


class TestRenderTemplate:
    def test_single_variable(self):
        assert render_template("^FD{nombre}^FS", {"nombre": "Alice"}) == "^FDAlice^FS"

    def test_multiple_variables(self):
        result = render_template("{a}-{b}", {"a": "X", "b": "Y"})
        assert result == "X-Y"

    def test_unknown_variable_left_unchanged(self):
        result = render_template("{known}-{unknown}", {"known": "ok"})
        assert result == "ok-{unknown}"

    def test_numeric_value(self):
        result = render_template("{n}", {"n": 42})
        assert result == "42"

    def test_empty_data(self):
        tmpl = "^FD{var}^FS"
        assert render_template(tmpl, {}) == tmpl

    def test_empty_template(self):
        assert render_template("", {"a": "1"}) == ""

    def test_repeated_variable(self):
        result = render_template("{x} and {x}", {"x": "Z"})
        assert result == "Z and Z"

    def test_no_variables(self):
        result = render_template("^XA^XZ", {"a": "b"})
        assert result == "^XA^XZ"

    def test_special_zpl_characters(self):
        result = render_template("^FO40,30^A0N,28,28^FD{nombre}^FS", {"nombre": "Test"})
        assert result == "^FO40,30^A0N,28,28^FDTest^FS"


class TestExtractVariables:
    def test_single_variable(self):
        assert extract_variables("{nombre}") == ["nombre"]

    def test_multiple_variables_sorted(self):
        assert extract_variables("{zebra}-{alpha}") == ["alpha", "zebra"]

    def test_duplicate_variables_deduplicated(self):
        assert extract_variables("{x} {x} {x}") == ["x"]

    def test_no_variables(self):
        assert extract_variables("^XA^XZ") == []

    def test_empty_string(self):
        assert extract_variables("") == []

    def test_zpl_template(self):
        zpl = "^FD{nombre}^FS^FD{codigo}^FS^FD{nombre}^FS"
        assert extract_variables(zpl) == ["codigo", "nombre"]

    def test_underscore_in_name(self):
        assert extract_variables("{my_var}") == ["my_var"]

    def test_mixed_case(self):
        assert extract_variables("{ABC}{def}") == ["ABC", "def"]
