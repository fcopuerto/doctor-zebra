"""Regression test for the print-form template fallback.

A history row pointing at a since-deleted template used to make the
print form render zero specs, silently degrading every field (including
lookup fields, which lost their picker) to plain text. ``_pick_template``
now falls back to the first available template instead.
"""

import unittest

from zebra.routes.labels import _pick_template


class PickTemplateTests(unittest.TestCase):
    TEMPLATES = ["ETIQUETA_PEQUENA.zpl", "OTRA.zpl"]

    def _exists(self, existing):
        return lambda name: name in existing

    def test_requested_template_still_exists(self):
        self.assertEqual(
            _pick_template(
                "ETIQUETA_PEQUENA.zpl", self.TEMPLATES,
                self._exists(self.TEMPLATES),
            ),
            "ETIQUETA_PEQUENA.zpl",
        )

    def test_requested_template_deleted_falls_back_to_first(self):
        # The bug: stale history pointed at a template that no longer
        # exists -> must fall back, not return an unresolved name.
        self.assertEqual(
            _pick_template(
                "ETIQUETA_GRANDE.zpl", self.TEMPLATES,
                self._exists(self.TEMPLATES),
            ),
            "ETIQUETA_PEQUENA.zpl",
        )

    def test_no_template_requested_falls_back_to_first(self):
        self.assertEqual(
            _pick_template("", self.TEMPLATES, self._exists(self.TEMPLATES)),
            "ETIQUETA_PEQUENA.zpl",
        )

    def test_deleted_template_and_no_templates_returns_empty(self):
        self.assertEqual(
            _pick_template("GONE.zpl", [], self._exists([])), ""
        )

    def test_nothing_requested_and_no_templates_returns_empty(self):
        self.assertEqual(_pick_template("", [], self._exists([])), "")


if __name__ == "__main__":
    unittest.main()
