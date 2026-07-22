import unittest
from unittest.mock import MagicMock, call, patch

from server.bilinovel.Editer import (
    CHAPTER_PENDING_RESTORE_POLLS,
    CHAPTER_STABLE_POLLS,
    Editer,
    IncompleteChapterContentError,
)


class TestChapterContent(unittest.TestCase):
    def test_get_page_text_supports_mobile_content_container(self):
        editer = Editer.__new__(Editer)
        editer.img_url_map = {}
        content = '<div id="acontent"><p>First.</p><p>Second.</p></div>'

        self.assertEqual(editer.get_page_text(content), '<p>First.</p><p>Second.</p>')

    def test_get_page_text_removes_advertisement_containers(self):
        editer = Editer.__new__(Editer)
        editer.img_url_map = {}
        content = """
            <div id="acontent">
              <p>Before.</p>
              <div class="ad-container"><iframe src="https://ads.example"></iframe></div>
              <ins class="adsbygoogle">Advertisement</ins>
              <p>After.</p>
            </div>
        """

        text = editer.get_page_text(content)

        self.assertEqual(text, '<p>Before.</p>\n<p>After.</p>\n')
        self.assertNotIn("Advertisement", text)
        self.assertNotIn("iframe", text)

    def test_get_page_text_keeps_the_first_inline_image(self):
        editer = Editer.__new__(Editer)
        editer.img_url_map = {}
        content = (
            '<div id="acontent"><p>Before.</p>'
            '<img src="https://img3.readpai.com/illustration.jpg"/>'
            '<p>After.</p></div>'
        )

        text = editer.get_page_text(content)

        self.assertIn('src="../Images/00.jpg"', text)
        self.assertIn("Before.", text)
        self.assertIn("After.", text)

    def test_waits_for_paragraph_reordering_to_settle(self):
        editer = Editer.__new__(Editer)
        editer.tab = MagicMock()
        editer.tab.run_js.side_effect = [
            "false|100|3|before|false",
            "false|100|3|before|false",
            "false|100|3|after|false",
            *("false|100|3|after|false" for _ in range(CHAPTER_STABLE_POLLS)),
        ]

        with patch("server.bilinovel.Editer.time.sleep"), patch(
            "server.bilinovel.Editer.time.monotonic", return_value=0
        ):
            editer._wait_for_complete_chapter("https://example.test/chapter")

        # The same length/count with a changed fingerprint must reset the
        # stability window; otherwise deferred chapterlog reordering races us.
        self.assertEqual(editer.tab.run_js.call_count, CHAPTER_STABLE_POLLS + 3)

    def test_restore_pending_chapter_order_returns_browser_result(self):
        editer = Editer.__new__(Editer)
        editer.tab = MagicMock()
        editer.tab.run_js.return_value = True

        self.assertTrue(editer._restore_pending_chapter_order())
        script = editer.tab.run_js.call_args.args[0]
        self.assertIn("return (() =>", script)
        self.assertIn("chapterid", script)

    def test_restores_pending_chapter_without_waiting_for_full_timeout(self):
        editer = Editer.__new__(Editer)
        editer.tab = MagicMock()
        editer.tab.run_js.side_effect = [
            *("false|100|30|shuffled|true" for _ in range(CHAPTER_PENDING_RESTORE_POLLS)),
            True,
        ]

        with patch("server.bilinovel.Editer.time.sleep"), patch(
            "server.bilinovel.Editer.time.monotonic", return_value=0
        ):
            editer._wait_for_complete_chapter("https://example.test/chapter")

        self.assertEqual(
            editer.tab.run_js.call_count, CHAPTER_PENDING_RESTORE_POLLS + 1
        )

    def test_get_chap_text_trims_continuation_page_boundaries(self):
        editer = Editer.__new__(Editer)
        editer.url_head = "https://www.linovelib.com"
        editer.reader_url_head = "https://tw.linovelib.com"
        editer.img_url_map = {}
        editer.get_html = MagicMock(
            side_effect=[
                '<div id="acontent"><br/><br/><p>First.</p><br/></div>'
                '<a href="/novel/28/5167_2.html"></a>',
                '<div id="acontent"><br/><p>Second.</p><br/><br/></div>',
            ]
        )

        text, _ = editer.get_chap_text(
            "https://www.linovelib.com/novel/28/5167.html", "Chapter 1"
        )

        self.assertEqual(text, '<p>First.</p>\n<p>Second.</p>')

    def test_get_page_text_rejects_pages_without_chapter_content(self):
        editer = Editer.__new__(Editer)
        editer.img_url_map = {}

        with self.assertRaisesRegex(ValueError, "text content container"):
            editer.get_page_text('<html><body>Access denied</body></html>')

    def test_get_chap_text_rejects_incomplete_source_content(self):
        editer = Editer.__new__(Editer)
        editer.url_head = "https://www.linovelib.com"
        editer.reader_url_head = "https://tw.linovelib.com"
        editer.get_html = MagicMock(
            return_value='<div id="TextContent"><p>内容加载失败</p></div>'
        )

        with self.assertRaises(IncompleteChapterContentError):
            editer.get_chap_text(
                "https://www.linovelib.com/novel/28/5167.html", "Chapter 1"
            )

        self.assertEqual(
            editer.get_html.call_args_list,
            [
                call(
                    "https://tw.linovelib.com/novel/28/5167.html",
                    is_gbk=False,
                    is_main_text=True,
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()
