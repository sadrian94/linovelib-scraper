import unittest
from unittest.mock import MagicMock

from backend.bilinovel.Editer import Editer


class TestChapterContent(unittest.TestCase):
    def test_get_page_text_supports_mobile_content_container(self):
        editer = Editer.__new__(Editer)
        editer.img_url_map = {}
        content = '<div id="acontent"><p>First.</p><p>Second.</p></div>'

        self.assertEqual(editer.get_page_text(content), '<p>First.</p><p>Second.</p>')

    def test_get_page_text_rejects_pages_without_chapter_content(self):
        editer = Editer.__new__(Editer)
        editer.img_url_map = {}

        with self.assertRaisesRegex(ValueError, "text content container"):
            editer.get_page_text('<html><body>Access denied</body></html>')

    def test_materialize_reading_order_uses_rendered_positions(self):
        editer = Editer.__new__(Editer)
        editer.tab = MagicMock()

        editer._materialize_reading_order()

        script = editer.tab.run_js.call_args.args[0]
        self.assertIn("getBoundingClientRect", script)
        self.assertIn("window.getComputedStyle", script)
        self.assertIn("content.appendChild(paragraph.node)", script)


if __name__ == "__main__":
    unittest.main()
